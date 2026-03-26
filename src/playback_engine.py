import threading
import time
import numpy as np
import sounddevice as sd
import soundfile as sf
from pathlib import Path
from datetime import datetime

from .audio_library import Fragment


SAMPLE_RATE = 44100
CHANNELS = 2
CROSSFADE_DURATION = 2.0  # seconds


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
        np.clip(mixed, -1.0, 1.0, out=mixed)
        outdata[:] = mixed
        # Capture for recording
        if self._recording:
            with self._rec_lock:
                self._rec_buffers.append(mixed.copy())

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
