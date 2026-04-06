"""
Real-Time Interaction System — Camera + Gesture Control + Live Audio Slicing

Transforms human presence (face + hands) into continuous control signals
that modulate both the audio backend and behavior layers of Becoming.

Architecture:
  Camera → MediaPipe FaceLandmarker + HandLandmarker (Tasks API) →
  Feature Extraction → Mapping → Exponential Smoothing →
  Shared ControlState → Engine (behavior + audio DSP)

  Sound Card → Ring Buffer → Onset Detection → Slice to WAV →
  Normalize → Analyze → Auto-tag → Stage into Active Pool
"""

import hashlib
import threading
import time
import math
import wave
import numpy as np
from collections import deque
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

try:
    import cv2
    import mediapipe as mp
    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False

try:
    import sounddevice as sd
    _HAS_SOUNDDEVICE = True
except ImportError:
    sd = None
    _HAS_SOUNDDEVICE = False


# ---------------------------------------------------------------------------
# Shared control state
# ---------------------------------------------------------------------------

class ControlState:
    """Thread-safe container for interaction-derived control values."""

    def __init__(self):
        self._lock = threading.Lock()
        self._active_sources: set[str] = set()
        self.audio = {
            "master_gain": 1.0,
            "lowpass": 1.0,
            "highpass": 0.0,
            "reverb": 0.0,
            "distortion": 0.0,
            "stereo_spread": 0.5,
        }
        self.behavior = {
            "strain": 0.3,
            "saturation": 0.5,
            "heat": 0.0,
            "time_scale": 1.0,
        }
        self.features = {
            "mouth_openness": 0.0,
            "eye_openness": 0.0,
            "head_tilt": 0.0,
            "hand_detected": False,
            "hand_x": 0.5,
            "hand_y": 0.5,
            "hand_velocity": 0.0,
            "hand_distance": 0.0,
            "audio_amplitude": 0.0,
            "audio_spectral_centroid": 0.0,
            "audio_noise_level": 0.0,
            "audio_onset_density": 0.0,
        }
        self.active = False  # True while camera is running

    def set_source_active(self, source: str, is_active: bool):
        with self._lock:
            if is_active:
                self._active_sources.add(source)
            else:
                self._active_sources.discard(source)
            self.active = bool(self._active_sources)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "audio": dict(self.audio),
                "behavior": dict(self.behavior),
                "features": {k: v for k, v in self.features.items()},
                "active": self.active,
            }

    def update_audio(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if k in self.audio:
                    self.audio[k] = float(np.clip(v, 0.0, 1.0))

    def update_behavior(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if k in self.behavior:
                    self.behavior[k] = float(np.clip(v, 0.0, 1.0))

    def update_features(self, features: dict):
        with self._lock:
            for k, v in features.items():
                if k in self.features:
                    self.features[k] = v


# ---------------------------------------------------------------------------
# Feature extraction helpers
# ---------------------------------------------------------------------------

def _lip_distance(landmarks) -> float:
    """Vertical mouth openness from upper/lower lip landmarks."""
    upper = landmarks[13]  # upper lip
    lower = landmarks[14]  # lower lip
    return abs(upper.y - lower.y)


def _eye_openness(landmarks) -> float:
    """Average eye openness from upper/lower eyelid landmarks."""
    # Left eye: 159 (upper), 145 (lower)
    # Right eye: 386 (upper), 374 (lower)
    left = abs(landmarks[159].y - landmarks[145].y)
    right = abs(landmarks[386].y - landmarks[374].y)
    return (left + right) / 2.0


def _head_tilt(landmarks) -> float:
    """Head roll from nose bridge to chin angle. Returns -1..1."""
    nose = landmarks[1]
    chin = landmarks[152]
    dx = chin.x - nose.x
    dy = chin.y - nose.y
    angle = math.atan2(dx, dy)  # radians, 0 = upright
    return float(np.clip(angle / (math.pi / 4), -1.0, 1.0))


def _hand_features(landmarks, prev_pos, dt) -> dict:
    """Extract hand position, velocity, and finger spread distance.
    
    landmarks: list of NormalizedLandmark from HandLandmarkerResult.
    """
    wrist = landmarks[0]

    hx, hy = wrist.x, wrist.y
    # Distance between thumb tip and pinky tip as "spread"
    thumb = landmarks[4]
    pinky = landmarks[20]
    dist = math.hypot(thumb.x - pinky.x, thumb.y - pinky.y)

    velocity = 0.0
    if prev_pos is not None and dt > 0:
        velocity = math.hypot(hx - prev_pos[0], hy - prev_pos[1]) / dt

    return {
        "hand_x": float(np.clip(hx, 0, 1)),
        "hand_y": float(np.clip(hy, 0, 1)),
        "hand_velocity": float(min(velocity, 5.0) / 5.0),  # normalize to 0-1
        "hand_distance": float(np.clip(dist * 3.0, 0, 1)),  # scale spread
    }


# ---------------------------------------------------------------------------
# Exponential smoother
# ---------------------------------------------------------------------------

class Smoother:
    """Per-key exponential smoothing."""

    def __init__(self, alpha: float = 0.15):
        self.alpha = alpha
        self._values: dict[str, float] = {}

    def smooth(self, key: str, raw: float) -> float:
        if key not in self._values:
            self._values[key] = raw
            return raw
        prev = self._values[key]
        smoothed = self.alpha * raw + (1.0 - self.alpha) * prev
        self._values[key] = smoothed
        return smoothed


# ---------------------------------------------------------------------------
# Mapping: features → audio control  (configurable per-input targets)
# ---------------------------------------------------------------------------

# Available audio targets a camera input can be mapped to
AUDIO_TARGETS = [
    "(none)", "lowpass", "highpass", "reverb",
    "distortion", "stereo_spread", "master_gain",
    "pan", "tremolo_rate", "tremolo_depth",
    "bitcrush", "noise_floor", "fade_time",
    "reverb_size", "reverb_feedback",
]

# Default mapping: input name → audio target
DEFAULT_CAMERA_MAPPING: dict[str, str] = {
    "mouth":         "distortion",
    "eyes":          "tremolo_rate",
    "head_tilt":     "pan",
    "hand_x":        "lowpass",
    "hand_y":        "highpass",
    "hand_spread":   "reverb_feedback",
    "hand_velocity": "noise_floor",
}


def normalize_input(name: str, features: dict) -> float:
    """Convert a named camera input to a normalised 0-1 activation value.

    Coefficients calibrated from real capture data (2026-03-30).
    Raw ranges measured:
        mouth_openness  0.001 – 0.107
        eye_openness    0.005 – 0.021
        head_tilt      -0.32  – -0.04  (user's neutral ≈ -0.25)
        hand_x          0.07  – 0.50
        hand_y          0.50  – 0.96
        hand_distance   0.00  – 1.00
        hand_velocity   0.00  – 0.085
    """
    if name == "mouth":
        # idle ~0.001, max ~0.107 → map 0.005–0.10 to 0–1
        raw = features.get("mouth_openness", 0.0)
        return min(1.0, max(0.0, raw - 0.005) / 0.095)
    if name == "eyes":
        # idle ~0.005, max ~0.021 → map 0.007–0.021 to 0–1
        raw = features.get("eye_openness", 0.0)
        return min(1.0, max(0.0, raw - 0.007) / 0.014)
    if name == "head_tilt":
        # range -0.32 to -0.04, neutral ~-0.25 → map -0.32...-0.04 to 0–1
        raw = features.get("head_tilt", 0.0)
        return min(1.0, max(0.0, (raw + 0.32) / 0.28))
    if name == "hand_x":
        # range 0.07–0.93 (mirrored camera) → map to 0–1
        raw = features.get("hand_x", 0.5)
        return min(1.0, max(0.0, (raw - 0.07) / 0.86))
    if name == "hand_y":
        # range 0.05–0.96, inverted (hand up = high value)
        raw = features.get("hand_y", 0.5)
        return min(1.0, max(0.0, (0.96 - raw) / 0.91))
    if name == "hand_spread":
        # 0–1 direct, cap at 0.85 to keep headroom
        raw = features.get("hand_distance", 0.0)
        return min(1.0, raw * 0.85)
    if name == "hand_velocity":
        # max ~0.085 → map 0–0.085 to 0–1
        raw = features.get("hand_velocity", 0.0)
        return min(1.0, raw / 0.085)
    return 0.0


def map_features_to_audio(features: dict, mapping: dict) -> dict:
    """
    Map extracted features to an audio-DSP control dict.

    *mapping*: ``{input_name: audio_target}`` chosen by the user in
    the visualiser combo-boxes (e.g. ``{"mouth": "lowpass"}``).  Camera
    never touches behaviour params (strain / saturation / heat / time_scale)
    — those are CC-only.

    Hand inputs are silently skipped when no hand is detected.
    """
    _INVERT_TARGETS = {"master_gain", "lowpass", "fade_time"}
    audio: dict[str, float] = {}
    for input_name, target in mapping.items():
        if not target or target == "(none)":
            continue
        if input_name.startswith("hand_") and not features.get("hand_detected"):
            continue
        val = float(np.clip(normalize_input(input_name, features), 0.0, 1.0))
        if target in _INVERT_TARGETS:
            val = 1.0 - val
        audio[target] = val
    return audio


# ---------------------------------------------------------------------------
# Perception loop (runs in background thread)
# ---------------------------------------------------------------------------

class InteractionEngine:
    """
    Camera perception thread that continuously reads frames,
    extracts face + hand features, and updates a ControlState.
    """

    def __init__(self, control_state: ControlState, camera_index: int = 0):
        if not _HAS_DEPS:
            raise RuntimeError("mediapipe and opencv-python are required for interaction")

        self.control = control_state
        self.camera_index = camera_index
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._smoother = Smoother(alpha=0.15)
        self._frame_lock = threading.Lock()
        self._last_frame: np.ndarray | None = None  # BGR, annotated

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="interact")
        self._thread.start()
        print("[interact] started camera perception")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self.control.set_source_active("camera", False)
        with self._frame_lock:
            self._last_frame = None
        print("[interact] stopped")

    def grab_frame(self) -> np.ndarray | None:
        """Return the latest annotated BGR frame (or None)."""
        with self._frame_lock:
            return self._last_frame.copy() if self._last_frame is not None else None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self):
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            print("[interact] ERROR: cannot open camera")
            self.control.set_source_active("camera", False)
            return

        # Lower resolution for speed
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # --- MediaPipe Tasks API ---
        vision = mp.tasks.vision
        BaseOptions = mp.tasks.BaseOptions

        face_model = _ROOT / "assets" / "models" / "face_landmarker.task"
        hand_model = _ROOT / "assets" / "models" / "hand_landmarker.task"

        if not face_model.exists() or not hand_model.exists():
            print(f"[interact] ERROR: model files missing — need {face_model} and {hand_model}")
            cap.release()
            self.control.set_source_active("camera", False)
            return

        face_landmarker = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(face_model)),
                running_mode=vision.RunningMode.VIDEO,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        )
        hand_landmarker = vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(hand_model)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        )

        draw = vision.drawing_utils.draw_landmarks
        draw_styles = vision.drawing_styles
        face_connections = vision.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION
        hand_connections = vision.HandLandmarksConnections.HAND_CONNECTIONS

        self.control.set_source_active("camera", True)
        prev_hand_pos = None
        prev_time = time.monotonic()
        frame_ts = 0  # millisecond timestamp for VIDEO mode

        try:
            while not self._stop.is_set():
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue

                # Mirror the frame for a natural selfie-view
                frame = cv2.flip(frame, 1)

                now = time.monotonic()
                dt = now - prev_time
                prev_time = now
                frame_ts += int(dt * 1000) if dt > 0 else 33

                # Convert BGR→RGB for MediaPipe
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

                features = {
                    "mouth_openness": 0.0,
                    "eye_openness": 0.0,
                    "head_tilt": 0.0,
                    "hand_detected": False,
                    "hand_x": 0.5,
                    "hand_y": 0.5,
                    "hand_velocity": 0.0,
                    "hand_distance": 0.0,
                }

                # Face landmarks
                face_result = face_landmarker.detect_for_video(mp_image, frame_ts)
                if face_result.face_landmarks:
                    lm = face_result.face_landmarks[0]  # list of NormalizedLandmark
                    features["mouth_openness"] = _lip_distance(lm)
                    features["eye_openness"] = _eye_openness(lm)
                    features["head_tilt"] = _head_tilt(lm)

                # Hand landmarks
                hand_result = hand_landmarker.detect_for_video(mp_image, frame_ts)
                if hand_result.hand_landmarks:
                    hlm = hand_result.hand_landmarks[0]  # list of NormalizedLandmark
                    hf = _hand_features(hlm, prev_hand_pos, dt)
                    features.update(hf)
                    features["hand_detected"] = True
                    prev_hand_pos = (hf["hand_x"], hf["hand_y"])
                else:
                    prev_hand_pos = None

                # Draw landmarks on frame for preview
                annotated = frame.copy()
                if face_result.face_landmarks:
                    draw(annotated, face_result.face_landmarks[0],
                         face_connections,
                         connection_drawing_spec=draw_styles
                             .get_default_face_mesh_tesselation_style())
                if hand_result.hand_landmarks:
                    draw(annotated, hand_result.hand_landmarks[0],
                         hand_connections,
                         draw_styles.get_default_hand_landmarks_style(),
                         draw_styles.get_default_hand_connections_style())
                with self._frame_lock:
                    self._last_frame = annotated

                # Smooth all features
                smoothed = {}
                for k, v in features.items():
                    if isinstance(v, (int, float)) and k != "hand_detected":
                        smoothed[k] = self._smoother.smooth(k, v)
                    else:
                        smoothed[k] = v

                # Store smoothed features (mapping is done in the GUI tick)
                self.control.update_features(smoothed)

                # Target ~30 FPS
                elapsed = time.monotonic() - now
                sleep_time = max(0, (1.0 / 30.0) - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        finally:
            face_landmarker.close()
            hand_landmarker.close()
            cap.release()
            self.control.set_source_active("camera", False)


# ---------------------------------------------------------------------------
# External audio input (sound card) → behavior control
# ---------------------------------------------------------------------------

class ExternalAudioInputEngine:
    """
    Real-time audio-input engine that reads from a sound card and maps
    extracted features into behavior controls.
    """

    def __init__(
        self,
        control_state: ControlState,
        device_hint: str = "ZOOM U-22 Driver",
        samplerate: int = 44100,
        channels: int = 2,
        blocksize: int = 1024,
        smoothing: float = 0.2,
        monitor_enabled: bool = True,
        monitor_gain: float = 0.8,
    ):
        if not _HAS_SOUNDDEVICE:
            raise RuntimeError("sounddevice is required for external audio input")

        self.control = control_state
        self.device_hint = device_hint
        self.samplerate = int(samplerate)
        self.channels = int(channels)
        self.blocksize = int(blocksize)
        self._stream = None
        self._lock = threading.Lock()
        self._smoother = Smoother(alpha=float(np.clip(smoothing, 0.01, 1.0)))
        self.monitor_enabled = bool(monitor_enabled)
        self.monitor_gain = float(np.clip(monitor_gain, 0.0, 1.5))
        self._energy_hist: deque[float] = deque(maxlen=120)
        self._onset_hist: deque[float] = deque(maxlen=120)
        self._prev_energy = 0.0
        self._device_index = None
        self._use_duplex = False
        self._live_slicer: LiveSlicer | None = None
        self.slicer_log_fn = None  # set by GUI to route logs

    @property
    def running(self) -> bool:
        return self._stream is not None

    def _resolve_input_device(self) -> int | None:
        devices = sd.query_devices()
        hint = (self.device_hint or "").strip().lower()

        # Prefer exact substring matches among input-capable devices.
        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) <= 0:
                continue
            name = str(dev.get("name", ""))
            if hint and hint in name.lower():
                return idx

        # Fallback to default input device if no match by hint.
        default_in = sd.default.device[0]
        if isinstance(default_in, int) and default_in >= 0:
            return default_in

        # Final fallback: first input-capable device.
        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                return idx

        return None

    def start(self):
        if self.running:
            return

        dev_idx = self._resolve_input_device()
        if dev_idx is None:
            raise RuntimeError("no input audio device available")

        dev = sd.query_devices(dev_idx)
        max_in = int(dev.get("max_input_channels", 0) or 0)
        use_channels = max(1, min(self.channels, max_in))

        # Prefer duplex stream so mic input is audible immediately.
        self._use_duplex = False
        if self.monitor_enabled:
            try:
                out_idx = sd.default.device[1]
                out_max = 0
                if isinstance(out_idx, int) and out_idx >= 0:
                    out_dev = sd.query_devices(out_idx)
                    out_max = int(out_dev.get("max_output_channels", 0) or 0)
                use_out = 2 if out_max >= 2 else (1 if out_max >= 1 else 0)
                if use_out > 0:
                    self._stream = sd.Stream(
                        device=(dev_idx, out_idx),
                        channels=(use_channels, use_out),
                        samplerate=self.samplerate,
                        blocksize=self.blocksize,
                        dtype="float32",
                        callback=self._duplex_callback,
                    )
                    self._use_duplex = True
            except Exception:
                self._stream = None

        if self._stream is None:
            self._stream = sd.InputStream(
                device=dev_idx,
                channels=use_channels,
                samplerate=self.samplerate,
                blocksize=self.blocksize,
                callback=self._audio_callback,
            )

        self._stream.start()
        self._device_index = dev_idx
        self.control.set_source_active("mic", True)
        monitor_mode = "duplex-monitor" if self._use_duplex else "analysis-only"
        print(f"[audio-in] started on input device: {dev.get('name', dev_idx)} ({monitor_mode})")

    def stop(self):
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        with self._lock:
            self._energy_hist.clear()
            self._onset_hist.clear()
            self._prev_energy = 0.0
        self._use_duplex = False
        self.control.set_source_active("mic", False)
        # Also stop live slicer if running
        if self._live_slicer is not None and self._live_slicer.enabled:
            self._live_slicer.stop()
        print("[audio-in] stopped")

    def set_slicing(self, enabled: bool):
        """Enable or disable live slicing of mic audio into the library."""
        if enabled:
            if self._live_slicer is None:
                self._live_slicer = LiveSlicer(samplerate=self.samplerate, log_fn=self.slicer_log_fn)
            if not self._live_slicer.enabled:
                self._live_slicer.start()
                print("[audio-in] live slicing ON")
        else:
            if self._live_slicer is not None and self._live_slicer.enabled:
                self._live_slicer.stop()
                print("[audio-in] live slicing OFF")

    @property
    def slicing_active(self) -> bool:
        return self._live_slicer is not None and self._live_slicer.enabled

    def _process_audio_block(self, mono: np.ndarray):
        if mono.size == 0:
            return

        rms = float(np.sqrt(np.mean(np.square(mono)) + 1e-12))
        amplitude = float(np.clip(rms * 8.0, 0.0, 1.0))

        spectrum = np.abs(np.fft.rfft(mono)) + 1e-12
        freqs = np.fft.rfftfreq(mono.size, d=1.0 / self.samplerate)
        centroid_hz = float(np.sum(freqs * spectrum) / np.sum(spectrum))
        nyquist = self.samplerate * 0.5
        spectral_centroid = float(np.clip(centroid_hz / max(nyquist, 1.0), 0.0, 1.0))

        hf_mask = freqs >= 2000.0
        hf = float(np.sum(spectrum[hf_mask])) if np.any(hf_mask) else 0.0
        total = float(np.sum(spectrum))
        noise_level = float(np.clip(hf / max(total, 1e-9), 0.0, 1.0))

        with self._lock:
            self._energy_hist.append(rms)
            rise = max(0.0, rms - self._prev_energy)
            onset = 1.0 if rise > 0.02 else 0.0
            self._onset_hist.append(onset)
            self._prev_energy = rms
            onset_density = float(np.mean(self._onset_hist)) if self._onset_hist else 0.0

        amp_s = float(np.clip(self._smoother.smooth("audio_amplitude", amplitude), 0.0, 1.0))
        sc_s = float(np.clip(self._smoother.smooth("audio_spectral_centroid", spectral_centroid), 0.0, 1.0))
        nl_s = float(np.clip(self._smoother.smooth("audio_noise_level", noise_level), 0.0, 1.0))
        od_s = float(np.clip(self._smoother.smooth("audio_onset_density", onset_density), 0.0, 1.0))

        self.control.update_features({
            "audio_amplitude": amp_s,
            "audio_spectral_centroid": sc_s,
            "audio_noise_level": nl_s,
            "audio_onset_density": od_s,
        })

        self.control.update_behavior(
            heat=amp_s,
            strain=nl_s,
            saturation=sc_s,
        )
        self.control.update_audio(
            reverb=amp_s,
            distortion=nl_s,
        )

        # Feed the live slicer (if active)
        if self._live_slicer is not None and self._live_slicer.enabled:
            self._live_slicer.feed(mono)

    def _audio_callback(self, indata, frames, time_info, status):
        # Keep callback lightweight and non-blocking.
        if status:
            return

        if indata is None or frames <= 0:
            return

        x = np.asarray(indata, dtype=np.float32)
        if x.ndim == 2:
            mono = np.mean(x, axis=1)
        else:
            mono = x
        self._process_audio_block(mono)

    def _duplex_callback(self, indata, outdata, frames, time_info, status):
        if status:
            outdata.fill(0.0)
            return

        if indata is None or frames <= 0:
            outdata.fill(0.0)
            return

        x = np.asarray(indata, dtype=np.float32)
        if x.ndim == 1:
            x = x.reshape(-1, 1)
        mono = np.mean(x, axis=1)
        self._process_audio_block(mono)

        # Direct monitor: pass input to output with gain and hard clip safety.
        y = np.clip(x * self.monitor_gain, -1.0, 1.0)
        out_ch = outdata.shape[1] if outdata.ndim == 2 else 1
        in_ch = y.shape[1] if y.ndim == 2 else 1

        if out_ch == in_ch:
            outdata[:] = y
        elif out_ch == 1 and in_ch > 1:
            outdata[:, 0] = np.mean(y, axis=1)
        elif out_ch > 1 and in_ch == 1:
            outdata[:] = np.repeat(y, out_ch, axis=1)
        else:
            # Fallback: fill common channels, zero the rest.
            outdata.fill(0.0)
            common = min(out_ch, in_ch)
            outdata[:, :common] = y[:, :common]


# ---------------------------------------------------------------------------
# Live Slicer — ring buffer → onset detect → save WAV → ingest → stage
# ---------------------------------------------------------------------------

_RAW_DIR = _ROOT / "library" / "audio_raw" / "local"
_NORM_DIR = _ROOT / "library" / "audio_normalized" / "local"
_DB_PATH = str(_ROOT / "library" / "becoming.db")


class LiveSlicer:
    """
    Accumulates audio blocks in a ring buffer, detects interesting moments
    (amplitude spikes / onsets), slices them to WAV, and pushes them through
    the full ingest pipeline (normalize → analyze → auto-tag → stage).

    All heavy I/O runs on a background thread so callbacks stay nonblocking.
    """

    def __init__(
        self,
        samplerate: int = 44100,
        buffer_seconds: float = 10.0,
        min_slice_seconds: float = 1.5,
        max_slice_seconds: float = 6.0,
        cooldown_seconds: float = 15.0,
        amplitude_threshold: float = 0.02,
        onset_threshold: float = 0.01,
        auto_tag: bool = True,
        log_fn=None,
    ):
        self.samplerate = samplerate
        self.buffer_len = int(buffer_seconds * samplerate)
        self.min_slice = int(min_slice_seconds * samplerate)
        self.max_slice = int(max_slice_seconds * samplerate)
        self.cooldown = cooldown_seconds
        self.amp_thresh = amplitude_threshold
        self.onset_thresh = onset_threshold
        self.auto_tag = auto_tag

        self._ring = np.zeros(self.buffer_len, dtype=np.float32)
        self._write_pos = 0
        self._lock = threading.Lock()
        self._last_slice_time = 0.0
        self._prev_energy = 0.0
        self._enabled = False

        # Background ingest queue
        self._ingest_queue: deque[Path] = deque()
        self._ingest_stop = threading.Event()
        self._ingest_thread: threading.Thread | None = None

        # Stats
        self.slices_saved = 0
        self.slices_ingested = 0
        self.slices_skipped_dup = 0

        # Spectral fingerprint history for dedup (keep last N fingerprints)
        self._fingerprint_history: deque[np.ndarray] = deque(maxlen=50)
        self._dup_threshold = 0.92  # cosine similarity above this = duplicate

        # Log callback — if set, messages appear in the GUI
        self._log_fn = log_fn

    def _log(self, msg: str):
        print(msg)
        if self._log_fn is not None:
            try:
                self._log_fn(msg)
            except Exception:
                pass

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self):
        """Enable slicing and start the background ingest worker."""
        _RAW_DIR.mkdir(parents=True, exist_ok=True)
        _NORM_DIR.mkdir(parents=True, exist_ok=True)
        self._enabled = True
        self._ingest_stop.clear()
        if self._ingest_thread is None or not self._ingest_thread.is_alive():
            self._ingest_thread = threading.Thread(
                target=self._ingest_worker, daemon=True, name="live-slicer-ingest"
            )
            self._ingest_thread.start()
        self._log("[live-slicer] started")

    def stop(self):
        """Disable slicing and drain the ingest queue."""
        self._enabled = False
        self._ingest_stop.set()
        if self._ingest_thread and self._ingest_thread.is_alive():
            self._ingest_thread.join(timeout=10.0)
        self._ingest_thread = None
        self._log(f"[live-slicer] stopped — {self.slices_saved} saved, {self.slices_ingested} ingested, {self.slices_skipped_dup} skipped as duplicate")

    def feed(self, mono: np.ndarray):
        """
        Feed a block of mono float32 audio.  Called from the audio callback
        via _process_audio_block — must be fast and nonblocking.
        """
        if not self._enabled or mono.size == 0:
            return

        n = mono.size
        with self._lock:
            # Write into ring buffer (may wrap)
            end = self._write_pos + n
            if end <= self.buffer_len:
                self._ring[self._write_pos:end] = mono
            else:
                first = self.buffer_len - self._write_pos
                self._ring[self._write_pos:] = mono[:first]
                self._ring[:n - first] = mono[first:]
            self._write_pos = end % self.buffer_len

        # Detect whether this block is interesting
        now = time.monotonic()
        if now - self._last_slice_time < self.cooldown:
            return

        rms = float(np.sqrt(np.mean(np.square(mono)) + 1e-12))
        rise = max(0.0, rms - self._prev_energy)
        self._prev_energy = rms

        if rms >= self.amp_thresh or rise >= self.onset_thresh:
            self._trigger_slice(now)

    def _trigger_slice(self, now: float):
        """Extract a slice from the ring buffer and queue it for saving."""
        self._last_slice_time = now

        with self._lock:
            # Grab the last max_slice samples ending at write_pos
            length = min(self.max_slice, self.buffer_len)
            start = (self._write_pos - length) % self.buffer_len
            if start < self._write_pos:
                chunk = self._ring[start:self._write_pos].copy()
            else:
                chunk = np.concatenate([
                    self._ring[start:],
                    self._ring[:self._write_pos],
                ]).copy()

            # Clear the ring buffer so the next slice has only fresh audio
            self._ring.fill(0.0)
            self._write_pos = 0

        # Trim leading silence (below -40 dB)
        silence_thresh = 0.01
        above = np.where(np.abs(chunk) > silence_thresh)[0]
        if above.size > 0:
            chunk = chunk[above[0]:]

        if chunk.size < self.min_slice:
            return

        # Spectral fingerprint dedup — reject if too similar to recent slices
        fp = self._fingerprint(chunk)
        if self._is_duplicate(fp):
            self.slices_skipped_dup += 1
            self._log(f"[live-slicer] skipped duplicate slice ({self.slices_skipped_dup} skipped total)")
            return
        self._fingerprint_history.append(fp)

        # Save to WAV in a nonblocking way (just queue the raw data)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        raw_path = _RAW_DIR / f"live_{ts}.wav"
        try:
            self._write_wav(raw_path, chunk)
            self.slices_saved += 1
            self._ingest_queue.append(raw_path)
            self._log(f"[live-slicer] saved slice: {raw_path.name} ({chunk.size / self.samplerate:.1f}s)")
        except Exception as e:
            self._log(f"[live-slicer] save error: {e}")

    def _fingerprint(self, mono: np.ndarray) -> np.ndarray:
        """Compute a compact spectral fingerprint for dedup comparison.

        Returns a normalized vector of: [spectral_centroid, spectral_bandwidth,
        zcr, rms, high-freq ratio, low-freq ratio, spectral_flatness,
        plus 8-bin spectral energy histogram].
        """
        n = mono.size
        spectrum = np.abs(np.fft.rfft(mono)) + 1e-12
        freqs = np.fft.rfftfreq(n, d=1.0 / self.samplerate)
        total_energy = float(np.sum(spectrum))

        # Core features
        centroid = float(np.sum(freqs * spectrum) / total_energy)
        bandwidth = float(np.sqrt(np.sum(((freqs - centroid) ** 2) * spectrum) / total_energy))
        zcr = float(np.mean(np.abs(np.diff(np.signbit(mono)))))
        rms = float(np.sqrt(np.mean(np.square(mono)) + 1e-12))

        # Frequency band ratios
        hf_mask = freqs >= 4000.0
        lf_mask = freqs <= 300.0
        hf_ratio = float(np.sum(spectrum[hf_mask]) / total_energy) if np.any(hf_mask) else 0.0
        lf_ratio = float(np.sum(spectrum[lf_mask]) / total_energy) if np.any(lf_mask) else 0.0

        # Spectral flatness (geometric mean / arithmetic mean of spectrum)
        log_spec = np.log(spectrum + 1e-12)
        flatness = float(np.exp(np.mean(log_spec)) / (np.mean(spectrum) + 1e-12))

        # 8-bin spectral energy histogram (log-spaced bands)
        bin_edges = np.logspace(np.log10(50), np.log10(self.samplerate / 2), 9)
        hist = np.zeros(8, dtype=np.float64)
        for i in range(8):
            mask = (freqs >= bin_edges[i]) & (freqs < bin_edges[i + 1])
            if np.any(mask):
                hist[i] = float(np.sum(spectrum[mask]) / total_energy)

        fp = np.array([centroid / 10000, bandwidth / 10000, zcr, rms,
                        hf_ratio, lf_ratio, flatness] + hist.tolist(),
                       dtype=np.float64)
        # L2 normalize
        norm = np.linalg.norm(fp)
        if norm > 0:
            fp /= norm
        return fp

    def _is_duplicate(self, fp: np.ndarray) -> bool:
        """Check if fingerprint is too similar to any recent slice."""
        for prev_fp in self._fingerprint_history:
            sim = float(np.dot(fp, prev_fp))  # cosine similarity (both L2-normalized)
            if sim >= self._dup_threshold:
                return True
        return False

    def _write_wav(self, path: Path, data: np.ndarray):
        """Write mono float32 data to a 16-bit WAV file."""
        pcm = np.clip(data, -1.0, 1.0)
        pcm16 = (pcm * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.samplerate)
            wf.writeframes(pcm16.tobytes())

    # ── Background ingest worker ──────────────────────────────────────

    def _ingest_worker(self):
        """
        Runs on a background thread.  Pulls saved WAV files from the queue,
        normalizes, analyzes, scores, inserts into DB, auto-tags, and stages
        for the active pool.
        """
        # Lazy imports so the audio callback path is never slowed
        from src.ingestion.database import Database
        from src.ingestion.normalizer import normalize_audio, compute_loudness_features, compute_checksum
        from src.ingestion.analyzer import extract_features, score_quality, score_world_fit, score_pulse_fit, score_drift_fit
        from src.ingestion.enums import TagType

        db = Database(_DB_PATH)
        db.connect()

        # Optional: active pool staging
        active_pool = None
        try:
            from src.engine.active_pool import ActivePool
            active_pool = ActivePool(_DB_PATH)
        except Exception:
            pass

        try:
            while not self._ingest_stop.is_set() or self._ingest_queue:
                if not self._ingest_queue:
                    self._ingest_stop.wait(timeout=1.0)
                    continue

                raw_path = self._ingest_queue.popleft()
                try:
                    self._ingest_one(raw_path, db, active_pool)
                    self.slices_ingested += 1
                except Exception as e:
                    self._log(f"[live-slicer] ingest error for {raw_path.name}: {e}")
        finally:
            db.close()

    def _ensure_live_job(self, db, now_iso: str) -> int:
        """Return or create a single ingestion job for this slicer session."""
        if hasattr(self, '_live_job_id') and self._live_job_id is not None:
            return self._live_job_id
        job_id = db.conn.execute(
            "INSERT INTO ingestion_jobs "
            "(query_text, source_name, requested_limit, status, notes, created_at, started_at) "
            "VALUES ('live_mic_capture', 'local', 9999, 'running', 'live slicer session', ?, ?)",
            (now_iso, now_iso),
        ).lastrowid
        db.conn.commit()
        self._live_job_id = job_id
        return job_id

    def _ingest_one(self, raw_path: Path, db, active_pool):
        """Full ingest pipeline for a single slice."""
        from src.ingestion.normalizer import normalize_audio, compute_loudness_features, compute_checksum
        from src.ingestion.analyzer import extract_features, score_quality, score_world_fit, score_pulse_fit, score_drift_fit
        from src.ingestion.enums import TagType

        # 1. Checksum + local_id
        checksum = compute_checksum(str(raw_path))
        local_id = f"local_live_{raw_path.stem}_{checksum[:8]}"

        # 2. Normalize (44.1kHz stereo WAV)
        self._log(f"[live-slicer] normalizing {raw_path.name}…")
        norm_path = _NORM_DIR / f"{local_id}.wav"
        norm_info = normalize_audio(str(raw_path), str(norm_path))

        # 3. Loudness features
        loudness = compute_loudness_features(str(norm_path))

        # 4. Quality score
        duration = norm_info.get("duration_seconds", 0.0)
        quality = score_quality(loudness, duration, {})

        if quality < 0.2:
            # Too low quality — discard
            norm_path.unlink(missing_ok=True)
            raw_path.unlink(missing_ok=True)
            self._log(f"[live-slicer] discarded {raw_path.name} (quality={quality:.2f})")
            return

        # 5. Feature extraction
        self._log(f"[live-slicer] analyzing {local_id}…")
        features = extract_features(str(norm_path))

        # 6. Fit scores
        world_fit = score_world_fit(features, loudness)
        pulse_fit = score_pulse_fit(features)
        drift_fit = score_drift_fit(features, loudness)

        # 7. Insert asset into DB
        self._log(f"[live-slicer] saving to db: {local_id} ({duration:.1f}s, q={quality:.2f})")

        # Create parent rows required by DB schema (job → candidate → asset)
        now_iso = datetime.now().isoformat()
        job_id = self._ensure_live_job(db, now_iso)
        cand_id = db.conn.execute(
            "INSERT INTO candidate_items "
            "(ingestion_job_id, source_name, source_item_id, title, description, "
            " duration_seconds, original_format, raw_metadata_json, "
            " candidate_status, created_at) "
            "VALUES (?, 'local', ?, ?, ?, ?, 'wav', '{}', 'approved', ?)",
            (job_id, local_id, f"live mic slice {raw_path.name}",
             f"Live-captured {duration:.1f}s audio from mic input",
             duration, now_iso),
        ).lastrowid
        db.conn.commit()

        asset_data = {
            "candidate_item_id": cand_id,
            "local_id": local_id,
            "checksum_sha256": checksum,
            "raw_file_path": str(raw_path),
            "normalized_file_path": str(norm_path),
            "waveform_path": None,
            "spectrogram_path": None,
            "sample_rate": norm_info.get("sample_rate", 44100),
            "channels": norm_info.get("channels", 2),
            "duration_seconds": duration,
            "loudness_lufs": loudness.get("loudness_lufs", 0.0),
            "peak_db": loudness.get("peak_db", 0.0),
            "silence_ratio": loudness.get("silence_ratio", 0.0),
            "rms": loudness.get("rms", 0.0),
            "clipping_ratio": loudness.get("clipping_ratio", 0.0),
            "quality_score": quality,
            "world_fit_score": world_fit,
            "pulse_fit_score": pulse_fit,
            "drift_fit_score": drift_fit,
            "approval_status": "approved",  # live slices auto-approved
            "rejection_reason": "",
        }
        asset_id = db.insert_asset(asset_data)

        # 8. Store analysis features
        db.upsert_features(asset_id, features)

        # 9. Add source tags
        for tag_text in ["live_capture", "mic_input", "field_recording"]:
            tag_id = db.get_or_create_tag(tag_text, TagType.source)
            db.add_asset_tag(asset_id, tag_id, "source_metadata")

        # 10. Auto-tag via LLM (if enabled and available)
        if self.auto_tag:
            self._log(f"[live-slicer] auto-tagging {local_id}…")
            try:
                from auto_tag import get_untagged_assets, build_prompt, call_ollama, apply_tags, DEFAULT_MODEL
                # Fetch just the one we inserted
                assets = get_untagged_assets(db, retag=False)
                target = [a for a in assets if a["id"] == asset_id]
                if target:
                    prompt = build_prompt(target[0])
                    result = call_ollama(prompt, DEFAULT_MODEL)
                    if result:
                        apply_tags(db, asset_id, result)
                        self._log(f"[live-slicer] auto-tagged {local_id}")
            except Exception as e:
                self._log(f"[live-slicer] auto-tag skipped: {e}")

        # 11. Stage for active pool
        if active_pool is not None:
            try:
                active_pool.stage_asset(asset_id)
                self._log(f"[live-slicer] staged asset {asset_id} ({local_id})")
            except Exception as e:
                self._log(f"[live-slicer] staging failed: {e}")
        else:
            self._log(f"[live-slicer] ingested asset {asset_id} ({local_id}), no active pool")
