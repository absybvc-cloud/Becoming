import time
from collections import deque


class MemorySystem:
    """
    Tracks recently played fragments and active layer combinations
    to prevent obvious repetition.
    """

    def __init__(self, recent_window: int = 20, combo_window: int = 10):
        self.recent_window = recent_window
        self.combo_window = combo_window

        self._recent: deque[str] = deque(maxlen=recent_window)
        self._combos: deque[frozenset] = deque(maxlen=combo_window)
        self._cooldowns: dict[str, float] = {}

    def register(self, fragment_id: str, cooldown: float):
        self._recent.append(fragment_id)
        self._cooldowns[fragment_id] = time.time() + cooldown

    def register_combo(self, active_ids: list[str]):
        self._combos.append(frozenset(active_ids))

    def is_on_cooldown(self, fragment_id: str) -> bool:
        expiry = self._cooldowns.get(fragment_id, 0)
        return time.time() < expiry

    def was_recently_played(self, fragment_id: str) -> bool:
        return fragment_id in self._recent

    def combo_seen_recently(self, active_ids: list[str]) -> bool:
        return frozenset(active_ids) in self._combos

    def is_allowed(self, fragment_id: str) -> bool:
        return not self.is_on_cooldown(fragment_id) and not self.was_recently_played(fragment_id)

    def cooldown_remaining(self, fragment_id: str) -> float:
        expiry = self._cooldowns.get(fragment_id, 0)
        return max(0.0, expiry - time.time())

    def summary(self) -> dict:
        return {
            "recent": list(self._recent),
            "active_cooldowns": {
                fid: round(self.cooldown_remaining(fid), 1)
                for fid in self._cooldowns
                if self.cooldown_remaining(fid) > 0
            },
            "combo_count": len(self._combos),
        }
