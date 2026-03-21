"""
State machine for the Becoming engine.

States define the global condition of the sonic ecology:
  Submerged - slow, low contrast, dominated by Ground + Texture
  Tense     - higher density, Event probability increases, Pulse tightens
  Dissolved - blurred boundaries, long pads dominate, low structure
  Rupture   - short duration, high Event frequency, unstable

Each state specifies role_weights, tag_bias, event_probability,
max_layers, duration_range, and transition tendencies.
"""

import time
import random
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable

from .roles import Role


@dataclass
class StateConfig:
    """Full configuration for a single system state."""
    name: str
    role_weights: dict[Role, float]
    tag_bias: dict[str, float]
    event_probability: float       # 0-1, chance of spawning an event each tick
    max_layers: int
    duration_range: tuple[float, float]  # (min_sec, max_sec) how long state lasts
    transition_tendency: dict[str, float]  # state_name → probability


# ── State Definitions ───────────────────────────────────────────────────────

STATES: dict[str, StateConfig] = {
    "submerged": StateConfig(
        name="submerged",
        role_weights={
            Role.GROUND: 5.0,
            Role.TEXTURE: 3.0,
            Role.EVENT: 0.2,
            Role.PULSE: 0.5,
        },
        tag_bias={
            "drone": 1.5, "ambient": 1.3, "dark": 1.2, "low": 1.4,
            "ocean": 1.5, "meditative": 1.3, "bassy": 1.2,
        },
        event_probability=0.02,
        max_layers=3,
        duration_range=(600, 1800),   # 10-30 min
        transition_tendency={
            "tense": 0.25,
            "dissolved": 0.50,
            "rupture": 0.05,
            "drifting": 0.20,
        },
    ),

    "tense": StateConfig(
        name="tense",
        role_weights={
            Role.GROUND: 2.0,
            Role.TEXTURE: 4.0,
            Role.EVENT: 3.0,
            Role.PULSE: 4.0,
        },
        tag_bias={
            "industrial": 1.5, "aggressive": 1.4, "noise": 1.3,
            "distorted": 1.3, "atonal": 1.2, "feedback": 1.4,
        },
        event_probability=0.15,
        max_layers=6,
        duration_range=(300, 900),    # 5-15 min
        transition_tendency={
            "rupture": 0.40,
            "submerged": 0.20,
            "dissolved": 0.25,
            "drifting": 0.15,
        },
    ),

    "dissolved": StateConfig(
        name="dissolved",
        role_weights={
            Role.GROUND: 6.0,
            Role.TEXTURE: 2.0,
            Role.EVENT: 0.1,
            Role.PULSE: 0.3,
        },
        tag_bias={
            "ambient": 1.5, "meditative": 1.4, "evolving": 1.3,
            "shimmering": 1.3, "drone": 1.2, "mysterious": 1.1,
        },
        event_probability=0.01,
        max_layers=2,
        duration_range=(900, 2400),   # 15-40 min
        transition_tendency={
            "submerged": 0.45,
            "drifting": 0.30,
            "tense": 0.20,
            "rupture": 0.05,
        },
    ),

    "rupture": StateConfig(
        name="rupture",
        role_weights={
            Role.GROUND: 1.0,
            Role.TEXTURE: 3.0,
            Role.EVENT: 6.0,
            Role.PULSE: 2.0,
        },
        tag_bias={
            "glitch": 1.5, "aggressive": 1.5, "noise": 1.4,
            "industrial": 1.3, "rare_event": 2.0, "distorted": 1.3,
        },
        event_probability=0.30,
        max_layers=7,
        duration_range=(120, 420),    # 2-7 min (short, unstable)
        transition_tendency={
            "submerged": 0.30,
            "tense": 0.25,
            "dissolved": 0.35,
            "drifting": 0.10,
        },
    ),

    "drifting": StateConfig(
        name="drifting",
        role_weights={
            Role.GROUND: 4.0,
            Role.TEXTURE: 3.0,
            Role.EVENT: 0.5,
            Role.PULSE: 1.0,
        },
        tag_bias={
            "drift_material": 1.5, "evolving": 1.3, "atmosphere": 1.3,
            "texture": 1.2, "shimmering": 1.2, "found_sound": 1.1,
        },
        event_probability=0.05,
        max_layers=4,
        duration_range=(600, 1500),   # 10-25 min
        transition_tendency={
            "submerged": 0.30,
            "dissolved": 0.25,
            "tense": 0.30,
            "rupture": 0.15,
        },
    ),
}

STATE_NAMES = list(STATES.keys())


class StateMachine:
    """
    Manages the current system state and probabilistic transitions.

    States persist for a configurable duration range, then transition
    probabilistically based on each state's transition_tendency.
    No instant switching — the system has inertia.
    """

    def __init__(
        self,
        initial_state: str = "submerged",
        on_state_change: Optional[Callable[[str, str], None]] = None,
    ):
        if initial_state not in STATES:
            raise ValueError(f"Unknown state: {initial_state}")

        self.current: str = initial_state
        self.on_state_change = on_state_change
        self._transition_at: float = time.time() + self._roll_duration()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def config(self) -> StateConfig:
        return STATES[self.current]

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[state] started in: {self.current}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            time.sleep(10)
            self._check_transition()

    def _check_transition(self):
        if time.time() >= self._transition_at:
            self._transition()

    def _transition(self):
        with self._lock:
            old = self.current
            tendencies = STATES[old].transition_tendency
            # Filter to valid states only
            candidates = {s: w for s, w in tendencies.items() if s in STATES and s != old}
            if not candidates:
                self._transition_at = time.time() + self._roll_duration()
                return

            states = list(candidates.keys())
            weights = list(candidates.values())
            self.current = random.choices(states, weights=weights, k=1)[0]
            self._transition_at = time.time() + self._roll_duration()

        print(f"[state] {old} -> {self.current}")
        if self.on_state_change:
            self.on_state_change(old, self.current)

    def _roll_duration(self) -> float:
        cfg = STATES[self.current]
        return random.uniform(*cfg.duration_range)

    def force_state(self, state: str):
        if state not in STATES:
            raise ValueError(f"Unknown state: {state}. Valid: {STATE_NAMES}")
        with self._lock:
            old = self.current
            self.current = state
            self._transition_at = time.time() + self._roll_duration()
        print(f"[state] forced: {old} -> {state}")
        if self.on_state_change:
            self.on_state_change(old, state)

    def get_role_weights(self) -> dict[Role, float]:
        return dict(self.config.role_weights)

    def get_tag_bias(self) -> dict[str, float]:
        return dict(self.config.tag_bias)

    def get_event_probability(self) -> float:
        return self.config.event_probability

    def get_max_layers(self) -> int:
        return self.config.max_layers

    def time_until_transition(self) -> float:
        return max(0.0, self._transition_at - time.time())
