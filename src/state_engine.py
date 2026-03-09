import time
import random
import threading
from typing import Optional, Callable


STATES = ["pulse", "drift", "low_density", "ritual", "noise_event"]

# density targets per state
STATE_DENSITY = {
    "pulse":       5,
    "drift":       2,
    "low_density": 1,
    "ritual":      4,
    "noise_event": 6,
}

# category weights per state
STATE_CATEGORY_WEIGHTS = {
    "pulse":       {"rhythm": 4, "tonal": 2, "drone": 1, "field": 1, "noise": 1},
    "drift":       {"drone": 5, "field": 3, "tonal": 2, "rhythm": 0, "noise": 1},
    "low_density": {"drone": 4, "field": 4, "tonal": 1, "rhythm": 0, "noise": 1},
    "ritual":      {"rhythm": 3, "tonal": 3, "drone": 2, "field": 1, "noise": 1},
    "noise_event": {"noise": 6, "rhythm": 2, "drone": 1, "field": 1, "tonal": 1},
}

# how long (seconds) before state can change again
STATE_DURATION_RANGE = (600, 1800)  # 10–30 minutes


class StateEngine:
    def __init__(self, on_state_change: Optional[Callable[[str, str], None]] = None):
        self.state = "drift"
        self.on_state_change = on_state_change
        self._next_transition = time.time() + self._random_duration()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[state] started in state: {self.state}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            time.sleep(10)
            self._check_transition()

    def _check_transition(self):
        if time.time() >= self._next_transition:
            self._transition()

    def _transition(self):
        old = self.state
        options = [s for s in STATES if s != old]
        self.state = random.choice(options)
        self._next_transition = time.time() + self._random_duration()
        print(f"[state] {old} -> {self.state}")
        if self.on_state_change:
            self.on_state_change(old, self.state)

    def _random_duration(self) -> float:
        return random.uniform(*STATE_DURATION_RANGE)

    def get_density(self) -> int:
        return STATE_DENSITY[self.state]

    def get_category_weights(self) -> dict[str, int]:
        return STATE_CATEGORY_WEIGHTS[self.state]

    def force_state(self, state: str):
        if state not in STATES:
            raise ValueError(f"unknown state: {state}")
        old = self.state
        self.state = state
        self._next_transition = time.time() + self._random_duration()
        print(f"[state] forced {old} -> {self.state}")
        if self.on_state_change:
            self.on_state_change(old, self.state)
