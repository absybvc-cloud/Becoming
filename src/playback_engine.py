import threading
import time
import numpy as np
import sounddevice as sd
import soundfile as sf
from pathlib import Path
from datetime import datetime
from scipy.signal import butter, sosfilt

from .audio_library import Fragment


SAMPLE_RATE = 44100
CHANNELS = 2
CROSSFADE_DURATION = 2.0  # seconds


# ---------------------------------------------------------------------------
# DSP helpers
# ---------------------------------------------------------------------------

def _design_lowpass(cutoff_norm: float) -> np.ndarray:
    """Design 2nd-order Butterworth lowpass. cutoff_norm in (0, 1)."""
    freq = max(0.01, min(0.99, cutoff_norm))
    return butter(2, freq, btype='low', output='sos')


def _design_highpass(cutoff_norm: float) -> np.ndarray:
    """Design 2nd-order Butterworth highpass. cutoff_norm in (0, 1)."""
    freq = max(0.01, min(0.99, cutoff_norm))
    return butter(2, freq, btype='high', output='sos')


def _tanh_distortion(audio: np.ndarray, drive: float) -> np.ndarray:
    """Soft-clip distortion via tanh waveshaping. drive 0-1."""
    if drive < 0.01:
        return audio
    gain = 1.0 + drive * 10.0  # 1x to 11x overdrive
    return np.tanh(audio * gain) / np.tanh(gain)


def _stereo_spread(audio: np.ndarray, amount: float) -> np.ndarray:
    """Mid/side stereo width. amount: 0=mono, 0.5=normal, 1=wide."""
    if audio.shape[1] < 2:
        return audio
    mid = (audio[:, 0] + audio[:, 1]) * 0.5
    side = (audio[:, 0] - audio[:, 1]) * 0.5
    width = amount * 2.0  # 0=mono center, 1=normal, 2=wide
    out = np.empty_like(audio)
    out[:, 0] = mid + side * width
    out[:, 1] = mid - side * width
    return out


class PlayingFragment:
    def __init__(self, fragment: Fragment, audio: np.ndarray, gain: float = 1.0, loop: bool = False):
        self.fragment = fragment
        self.audio = audio          # shape: (samples, channels)
        self.gain = gain
        self.loop = loop
        self.position = 0
        self.active = True
        self.fade_out = False
        self.fade_samples_remaining = 0

    def read(self, n_frames: int) -> np.ndarray:
        out = np.zeros((n_frames, CHANNELS), dtype=np.float32)
        written = 0

        while written < n_frames and self.active:
            available = len(self.audio) - self.position
            need = n_frames - written

            chunk_len = min(available, need)
            chunk = self.audio[self.position:self.position + chunk_len]
            out[written:written + chunk_len] = chunk
            self.position += chunk_len
            written += chunk_len

            if self.position >= len(self.audio):
                if self.loop:
                    self.position = 0
                else:
                    self.active = False
                    break

        # apply gain
        out *= self.gain

        # apply fade out if requested
        if self.fade_out and self.fade_samples_remaining > 0:
            fade_len = min(n_frames, self.fade_samples_remaining)
            start = self.fade_samples_remaining
            end = start - fade_len
            envelope = np.linspace(start, end, fade_len) / (CROSSFADE_DURATION * SAMPLE_RATE)
            envelope = np.clip(envelope, 0, 1).reshape(-1, 1)
            out[:fade_len] *= envelope
            self.fade_samples_remaining -= fade_len
            if self.fade_samples_remaining <= 0:
                self.active = False

        return out


class PlaybackEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.playing: dict[str, PlayingFragment] = {}
        self.stream = None
        # Recording state
        self._recording = False
        self._rec_buffers: list[np.ndarray] = []
        self._rec_lock = threading.Lock()
        # DSP state
        self._master_gain = 1.0
        self._lowpass = 1.0     # 0-1 normalized cutoff (1 = wide open)
        self._highpass = 0.0    # 0-1 normalized cutoff (0 = off)
        self._reverb = 0.0      # 0-1 wet amount
        self._distortion = 0.0  # 0-1 drive
        self._stereo_spread = 0.5  # 0=mono, 0.5=normal, 1=wide
        self._pan = 0.5         # 0=full left, 0.5=center, 1=full right
        self._tremolo_rate = 0.0   # Hz (0 = off)
        self._tremolo_depth = 0.0  # 0-1
        self._tremolo_phase = 0.0  # internal LFO phase
        self._bitcrush = 0.0    # 0-1 (0 = off, 1 = heavy crush)
        self._noise_floor = 0.0 # 0-1 noise level
        self._fade_time = 0.5   # 0-1 mapped to 0.1-4.0s crossfade
        self._reverb_size = 0.5 # 0-1 mapped to 20ms-500ms
        self._reverb_feedback = 0.5  # 0-1 mapped to 0.0-0.95
        # Filter state (scipy sosfilt_zi)
        self._lp_sos = None
        self._lp_zi = None
        self._hp_sos = None
        self._hp_zi = None
        # Reverb delay buffer (simple comb feedback)
        self._reverb_buf = np.zeros((int(SAMPLE_RATE * 0.08), CHANNELS), dtype=np.float32)
        self._reverb_pos = 0

    def start(self):
        self.stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=1024,
            callback=self._callback,
        )
        self.stream.start()
        print("[playback] engine started")

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
        print("[playback] engine stopped")

    def _callback(self, outdata: np.ndarray, frames: int, time_info, status):
        mixed = np.zeros((frames, CHANNELS), dtype=np.float32)
        with self.lock:
            dead = []
            for fid, pf in self.playing.items():
                mixed += pf.read(frames)
                if not pf.active:
                    dead.append(fid)
            for fid in dead:
                del self.playing[fid]

        # --- DSP chain ---

        # Lowpass filter
        if self._lowpass < 0.99 and self._lp_sos is not None:
            try:
                mixed, self._lp_zi = sosfilt(self._lp_sos, mixed, axis=0, zi=self._lp_zi)
                mixed = mixed.astype(np.float32)
            except Exception:
                pass

        # Highpass filter
        if self._highpass > 0.01 and self._hp_sos is not None:
            try:
                mixed, self._hp_zi = sosfilt(self._hp_sos, mixed, axis=0, zi=self._hp_zi)
                mixed = mixed.astype(np.float32)
            except Exception:
                pass

        # Distortion
        if self._distortion > 0.01:
            mixed = _tanh_distortion(mixed, self._distortion)

        # Reverb (simple comb delay)
        if self._reverb > 0.01:
            buf = self._reverb_buf
            pos = self._reverb_pos
            buf_len = len(buf)
            wet = self._reverb * 0.5  # scale down to avoid runaway
            fb = 0.05 + self._reverb_feedback * 0.90  # 0.05–0.95
            for i in range(frames):
                delayed = buf[pos]
                out_sample = mixed[i] + delayed * wet
                buf[pos] = mixed[i] + delayed * fb
                mixed[i] = out_sample
                pos = (pos + 1) % buf_len
            self._reverb_pos = pos

        # Bitcrush
        if self._bitcrush > 0.01:
            levels = max(2, int(2 ** (16 * (1.0 - self._bitcrush))))
            mixed = np.round(mixed * levels) / levels

        # Tremolo (amplitude LFO)
        if self._tremolo_depth > 0.01 and self._tremolo_rate > 0.01:
            rate = 0.5 + self._tremolo_rate * 19.5  # 0.5–20 Hz
            depth = self._tremolo_depth
            t = np.arange(frames) / SAMPLE_RATE
            lfo = (1.0 - depth * 0.5) + (depth * 0.5) * np.sin(
                2.0 * np.pi * rate * t + self._tremolo_phase
            )
            self._tremolo_phase += 2.0 * np.pi * rate * frames / SAMPLE_RATE
            self._tremolo_phase %= 2.0 * np.pi
            mixed *= lfo.reshape(-1, 1).astype(np.float32)

        # Stereo spread
        if abs(self._stereo_spread - 0.5) > 0.02:
            mixed = _stereo_spread(mixed, self._stereo_spread)

        # Pan
        if abs(self._pan - 0.5) > 0.02 and mixed.shape[1] >= 2:
            l_gain = np.sqrt(1.0 - self._pan)
            r_gain = np.sqrt(self._pan)
            mixed[:, 0] *= l_gain
            mixed[:, 1] *= r_gain

        # Noise floor
        if self._noise_floor > 0.001:
            noise = self._noise_floor * 0.05 * np.random.randn(frames, CHANNELS).astype(np.float32)
            mixed += noise

        # Master gain
        if abs(self._master_gain - 1.0) > 0.001:
            mixed *= self._master_gain

        np.clip(mixed, -1.0, 1.0, out=mixed)
        outdata[:] = mixed
        # Capture for recording
        if self._recording:
            with self._rec_lock:
                self._rec_buffers.append(mixed.copy())

    # --- DSP setters (thread-safe via atomic float assignment) ---

    def set_master_gain(self, value: float):
        self._master_gain = max(0.0, min(2.0, value))

    def set_filter(self, lowpass: float, highpass: float):
        """Set filter cutoffs. lowpass/highpass are 0-1 normalized."""
        lp = max(0.01, min(0.99, lowpass))
        hp = max(0.0, min(0.99, highpass))
        if abs(lp - self._lowpass) > 0.005:
            self._lowpass = lp
            if lp < 0.99:
                self._lp_sos = _design_lowpass(lp)
                from scipy.signal import sosfilt_zi
                self._lp_zi = np.stack([sosfilt_zi(self._lp_sos)] * CHANNELS, axis=-1)
            else:
                self._lp_sos = None
                self._lp_zi = None
        if abs(hp - self._highpass) > 0.005:
            self._highpass = hp
            if hp > 0.01:
                self._hp_sos = _design_highpass(hp)
                from scipy.signal import sosfilt_zi
                self._hp_zi = np.stack([sosfilt_zi(self._hp_sos)] * CHANNELS, axis=-1)
            else:
                self._hp_sos = None
                self._hp_zi = None

    def set_reverb(self, amount: float):
        self._reverb = max(0.0, min(1.0, amount))

    def set_distortion(self, amount: float):
        self._distortion = max(0.0, min(1.0, amount))

    def set_stereo_spread(self, amount: float):
        self._stereo_spread = max(0.0, min(1.0, amount))

    def set_pan(self, value: float):
        self._pan = max(0.0, min(1.0, value))

    def set_tremolo(self, rate: float, depth: float):
        self._tremolo_rate = max(0.0, min(1.0, rate))
        self._tremolo_depth = max(0.0, min(1.0, depth))

    def set_bitcrush(self, amount: float):
        self._bitcrush = max(0.0, min(1.0, amount))

    def set_noise_floor(self, amount: float):
        self._noise_floor = max(0.0, min(1.0, amount))

    def set_fade_time(self, amount: float):
        """Set crossfade duration. amount 0-1 maps to 0.1-4.0 seconds."""
        global CROSSFADE_DURATION
        self._fade_time = max(0.0, min(1.0, amount))
        CROSSFADE_DURATION = 0.1 + self._fade_time * 3.9

    def set_reverb_size(self, amount: float):
        """Resize reverb buffer. amount 0-1 maps to 20ms-500ms."""
        self._reverb_size = max(0.0, min(1.0, amount))
        new_len = int(SAMPLE_RATE * (0.02 + self._reverb_size * 0.48))
        if new_len != len(self._reverb_buf):
            self._reverb_buf = np.zeros((new_len, CHANNELS), dtype=np.float32)
            self._reverb_pos = 0

    def set_reverb_feedback(self, amount: float):
        self._reverb_feedback = max(0.0, min(1.0, amount))

    def _load_audio(self, fragment: Fragment) -> np.ndarray:
        data, sr = sf.read(fragment.file_path, dtype="float32", always_2d=True)
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] > 2:
            data = data[:, :2]
        if sr != SAMPLE_RATE:
            import librosa
            data = librosa.resample(data.T, orig_sr=sr, target_sr=SAMPLE_RATE).T
        return data

    def play(self, fragment: Fragment, gain: float = 1.0) -> bool:
        try:
            audio = self._load_audio(fragment)
        except Exception as e:
            print(f"[playback] failed to load {fragment.id}: {e}")
            return False
        pf = PlayingFragment(fragment, audio, gain=gain, loop=fragment.loopable)
        with self.lock:
            self.playing[fragment.id] = pf
        print(f"[playback] playing {fragment.id} (loop={fragment.loopable})")
        return True

    def stop_fragment(self, fragment_id: str, crossfade: bool = True):
        with self.lock:
            pf = self.playing.get(fragment_id)
            if not pf:
                return
            if crossfade:
                pf.fade_out = True
                pf.fade_samples_remaining = int(CROSSFADE_DURATION * SAMPLE_RATE)
            else:
                pf.active = False
        print(f"[playback] stopping {fragment_id} (crossfade={crossfade})")

    def set_gain(self, fragment_id: str, gain: float):
        """Update gain for a playing fragment (used by layer fade system)."""
        with self.lock:
            pf = self.playing.get(fragment_id)
            if pf:
                pf.gain = gain

    def crossfade(self, fragment_out: str, fragment_in: Fragment, gain: float = 1.0):
        self.stop_fragment(fragment_out, crossfade=True)
        self.play(fragment_in, gain=gain)

    def active_ids(self) -> list[str]:
        with self.lock:
            return list(self.playing.keys())

    def is_playing(self, fragment_id: str) -> bool:
        with self.lock:
            return fragment_id in self.playing

    # ── Recording ────────────────────────────────────────────────────

    def start_recording(self):
        """Begin capturing the mixed audio output."""
        with self._rec_lock:
            self._rec_buffers.clear()
            self._recording = True
        print("[playback] recording started")

    def stop_recording(self) -> np.ndarray | None:
        """Stop recording and return concatenated audio (or None if empty)."""
        with self._rec_lock:
            self._recording = False
            if not self._rec_buffers:
                return None
            audio = np.concatenate(self._rec_buffers, axis=0)
            self._rec_buffers.clear()
        print(f"[playback] recording stopped ({len(audio) / SAMPLE_RATE:.1f}s)")
        return audio

    @staticmethod
    def save_recording(audio: np.ndarray, path: str | Path):
        """Write recorded audio to a WAV file."""
        sf.write(str(path), audio, SAMPLE_RATE, subtype="PCM_24")
        print(f"[playback] saved recording to {path}")
