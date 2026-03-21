"""
External variables interface for the Becoming engine.

The engine accepts external input to modulate its behavior:
  time_of_day   - affects density and brightness
  tension       - controls Event probability, compresses Pulse
  density       - controls max layers and overlap
  noise_level   - increases texture/noise probability
  human_bias    - manual override weighting

These can be set externally (API, clock, sensors) or left at defaults.
"""

import time
from dataclasses import dataclass


@dataclass
class WorldState:
    """Current external variables affecting the engine."""
    time_of_day: float = 0.5     # 0=midnight, 0.5=noon, 1.0=midnight
    tension: float = 0.3         # 0=calm, 1=maximal tension
    density: float = 0.5         # 0=sparse, 1=dense
    noise_level: float = 0.0     # 0=quiet, 1=noisy
    human_bias: dict = None      # tag → weight override

    def __post_init__(self):
        if self.human_bias is None:
            self.human_bias = {}


class WorldInterface:
    """
    Manages the world state. Can be updated externally or driven
    by the system clock for time_of_day.
    """

    def __init__(self, auto_time: bool = True):
        self.state = WorldState()
        self.auto_time = auto_time
        self._runtime_start = time.time()

    def update(self, **kwargs):
        """Update one or more world variables."""
        for key, value in kwargs.items():
            if hasattr(self.state, key):
                setattr(self.state, key, value)

    def get(self) -> WorldState:
        """Get current world state, auto-updating time if enabled."""
        if self.auto_time:
            lt = time.localtime()
            # 0-1 wrapped: 0=midnight, 0.5=noon
            self.state.time_of_day = (lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec) / 86400.0
        return self.state

    @property
    def runtime_hours(self) -> float:
        return (time.time() - self._runtime_start) / 3600.0

    def get_density_modifier(self) -> float:
        """World density as a multiplier for max_layers."""
        return 0.5 + self.state.density  # range: 0.5 - 1.5

    def get_tension_modifier(self) -> float:
        """World tension as an event probability multiplier."""
        return 0.5 + self.state.tension * 1.5  # range: 0.5 - 2.0

    def get_time_brightness(self) -> float:
        """
        Time-based brightness: higher during day, lower at night.
        Peaks at noon (0.5), lowest at midnight (0.0/1.0).
        """
        t = self.state.time_of_day
        # sine curve: peak at 0.5 (noon)
        import math
        return 0.5 + 0.5 * math.sin(t * math.pi * 2 - math.pi / 2)
