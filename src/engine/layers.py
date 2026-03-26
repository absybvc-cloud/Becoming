"""
Layer Manager — Runtime Layer Lifecycle

Manages active sound layers with explicit state transitions:
    pending → fading_in → playing → fading_out → ended

Each layer tracks its own fade envelope, role, gain, and timing.
The conductor spawns layers; the layer manager updates them each tick.
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class LayerState(str, Enum):
    PENDING = "pending"
    FADING_IN = "fading_in"
    PLAYING = "playing"
    FADING_OUT = "fading_out"
    ENDED = "ended"


@dataclass
class Layer:
    """A sound currently playing as part of the mix."""
    layer_id: str
    fragment_id: str
    asset_id: int
    role: str               # ground / texture / event / pulse
    state: LayerState
    started_at: float
    expected_end_at: float
    fade_in_sec: float
    fade_out_sec: float
    target_gain: float
    current_gain: float
    pan: float
    metadata_version: int

    @property
    def age(self) -> float:
        return time.time() - self.started_at

    @property
    def remaining(self) -> float:
        return max(0.0, self.expected_end_at - time.time())

    @property
    def should_fade_out(self) -> bool:
        """True when it's time to start fading out."""
        return time.time() >= self.expected_end_at - self.fade_out_sec

    @property
    def is_finished(self) -> bool:
        return self.state == LayerState.ENDED


# ── Fade timing per role ────────────────────────────────────────────────

ROLE_FADE_IN = {
    "ground": 6.0,
    "texture": 3.0,
    "event": 0.5,
    "pulse": 2.0,
}

ROLE_FADE_OUT = {
    "ground": 8.0,
    "texture": 4.0,
    "event": 1.0,
    "pulse": 3.0,
}


def create_layer(
    fragment_id: str,
    asset_id: int,
    role: str,
    duration: float,
    target_gain: float,
    pan: float = 0.0,
    metadata_version: int = 1,
) -> Layer:
    """Create a new layer in fading_in state."""
    now = time.time()
    fade_in = ROLE_FADE_IN.get(role, 3.0)
    fade_out = ROLE_FADE_OUT.get(role, 4.0)

    return Layer(
        layer_id=str(uuid.uuid4())[:8],
        fragment_id=fragment_id,
        asset_id=asset_id,
        role=role,
        state=LayerState.FADING_IN,
        started_at=now,
        expected_end_at=now + duration,
        fade_in_sec=fade_in,
        fade_out_sec=fade_out,
        target_gain=target_gain,
        current_gain=0.0,
        pan=pan,
        metadata_version=metadata_version,
    )


def update_layer(layer: Layer, dt: float) -> None:
    """
    Advance a layer's state and gain each tick.
    Modifies the layer in-place.
    """
    now = time.time()

    if layer.state == LayerState.FADING_IN:
        # Ramp gain toward target
        if layer.fade_in_sec > 0:
            rate = layer.target_gain / layer.fade_in_sec
            layer.current_gain = min(layer.target_gain, layer.current_gain + rate * dt)
        else:
            layer.current_gain = layer.target_gain

        if layer.current_gain >= layer.target_gain * 0.99:
            layer.current_gain = layer.target_gain
            layer.state = LayerState.PLAYING

    elif layer.state == LayerState.PLAYING:
        layer.current_gain = layer.target_gain
        if layer.should_fade_out:
            layer.state = LayerState.FADING_OUT

    elif layer.state == LayerState.FADING_OUT:
        if layer.fade_out_sec > 0:
            rate = layer.target_gain / layer.fade_out_sec
            layer.current_gain = max(0.0, layer.current_gain - rate * dt)
        else:
            layer.current_gain = 0.0

        if layer.current_gain <= 0.01 or now >= layer.expected_end_at:
            layer.current_gain = 0.0
            layer.state = LayerState.ENDED

    elif layer.state == LayerState.ENDED:
        layer.current_gain = 0.0


def force_fade_out(layer: Layer) -> None:
    """Force a layer to start fading out immediately."""
    if layer.state in (LayerState.FADING_IN, LayerState.PLAYING):
        layer.state = LayerState.FADING_OUT
