"""
Intervention Queue — Formalized External Actions

Interventions are messages from the control surface (GUI, MIDI, stdin)
that affect the scheduler's behavior.  They enter through a thread-safe
queue and are consumed once per tick.

Spec reference: engine_runtime_loop.md §15
"""

import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class InterventionType(str, Enum):
    INTRODUCE_RUPTURE = "introduce_rupture"
    INVITE_SILENCE = "invite_silence"
    ENTER_DRIFT = "enter_drift"
    FORCE_COLLAPSE = "force_collapse"
    STABILIZE = "stabilize"
    AWAKEN = "awaken"
    SILENCE = "silence"
    MUTATE_REPLACE = "mutate_replace"


@dataclass
class Intervention:
    kind: InterventionType
    strength: float = 1.0
    issued_at: float = field(default_factory=time.time)


# ── Effects per intervention (additive modifiers for one scheduler cycle) ──

@dataclass
class InterventionEffect:
    """Modifiers applied to the scheduler for the duration of the intervention."""
    event_prob_mult: float = 1.0        # multiply event probability
    max_layers_delta: int = 0           # add/subtract to max layers
    spawn_rate_mult: float = 1.0        # multiply spawn chance
    fade_out_bias: float = 0.0          # 0-1, probability of forcing fade-out on random layer
    role_bias: dict = field(default_factory=dict)   # role → additive weight
    novelty_mult: float = 1.0           # multiply novelty boost
    suppress_new_spawns: bool = False   # if True, no new layers spawn
    fade_all: bool = False              # if True, gracefully fade everything


EFFECTS: dict[InterventionType, InterventionEffect] = {
    InterventionType.INTRODUCE_RUPTURE: InterventionEffect(
        event_prob_mult=4.0,
        role_bias={"event": 2.0, "ground": -0.5},
        fade_out_bias=0.3,
    ),
    InterventionType.INVITE_SILENCE: InterventionEffect(
        max_layers_delta=-2,
        spawn_rate_mult=0.3,
        fade_out_bias=0.4,
        role_bias={"pulse": -1.0, "event": -1.0},
    ),
    InterventionType.ENTER_DRIFT: InterventionEffect(
        novelty_mult=2.0,
        role_bias={"texture": 0.5},
    ),
    InterventionType.FORCE_COLLAPSE: InterventionEffect(
        fade_out_bias=0.7,
        max_layers_delta=-3,
        spawn_rate_mult=0.2,
    ),
    InterventionType.STABILIZE: InterventionEffect(
        event_prob_mult=0.2,
        role_bias={"ground": 1.0, "texture": 0.3, "event": -1.0},
        spawn_rate_mult=0.8,
    ),
    InterventionType.AWAKEN: InterventionEffect(
        # no special modifiers — just resumes scheduling
    ),
    InterventionType.SILENCE: InterventionEffect(
        suppress_new_spawns=True,
        fade_all=True,
    ),
    InterventionType.MUTATE_REPLACE: InterventionEffect(
        fade_out_bias=0.5,
    ),
}


class InterventionQueue:
    """
    Thread-safe queue of pending interventions.
    Background threads (GUI, MIDI, stdin) enqueue; the scheduler drains.
    """

    def __init__(self):
        self._queue: list[Intervention] = []
        self._lock = threading.Lock()

    def enqueue(self, kind: InterventionType | str, strength: float = 1.0) -> None:
        if isinstance(kind, str):
            kind = InterventionType(kind)
        with self._lock:
            self._queue.append(Intervention(kind=kind, strength=strength))

    def drain(self) -> list[Intervention]:
        """Return all pending interventions and clear the queue."""
        with self._lock:
            items = list(self._queue)
            self._queue.clear()
        return items

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._queue) == 0

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._queue)


def compute_combined_effect(interventions: list[Intervention]) -> InterventionEffect:
    """Combine multiple interventions into a single effect modifier."""
    if not interventions:
        return InterventionEffect()

    combined = InterventionEffect()
    for iv in interventions:
        effect = EFFECTS.get(iv.kind, InterventionEffect())
        s = iv.strength

        combined.event_prob_mult *= (1.0 + (effect.event_prob_mult - 1.0) * s)
        combined.max_layers_delta += int(effect.max_layers_delta * s)
        combined.spawn_rate_mult *= (1.0 + (effect.spawn_rate_mult - 1.0) * s)
        combined.fade_out_bias = min(1.0, combined.fade_out_bias + effect.fade_out_bias * s)
        combined.novelty_mult *= (1.0 + (effect.novelty_mult - 1.0) * s)

        for role, bias in effect.role_bias.items():
            combined.role_bias[role] = combined.role_bias.get(role, 0.0) + bias * s

        if effect.suppress_new_spawns:
            combined.suppress_new_spawns = True
        if effect.fade_all:
            combined.fade_all = True

    return combined
