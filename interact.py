"""
Real-Time Interaction System — Camera + Gesture Control

Transforms human presence (face + hands) into continuous control signals
that modulate both the audio backend and behavior layers of Becoming.

Architecture:
  Camera → MediaPipe FaceLandmarker + HandLandmarker (Tasks API) →
  Feature Extraction → Mapping → Exponential Smoothing →
  Shared ControlState → Engine (behavior + audio DSP)
"""

import threading
import time
import math
import numpy as np
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

try:
    import cv2
    import mediapipe as mp
    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False


# ---------------------------------------------------------------------------
# Shared control state
# ---------------------------------------------------------------------------

class ControlState:
    """Thread-safe container for interaction-derived control values."""

    def __init__(self):
        self._lock = threading.Lock()
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
        }
        self.active = False  # True while camera is running

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
        self.control.active = False
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
            self.control.active = False
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
            self.control.active = False
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

        self.control.active = True
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
            self.control.active = False
