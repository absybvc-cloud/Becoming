"""
Enhanced memory system for the Becoming engine.

Tracks:
  - Recently played fragments (anti-repetition)
  - Recently used tags (variety enforcement)
  - Per-fragment play counts (popularity suppression)
  - Current density trend (momentum tracking)
  - Last event time (event spacing)
  - Layer combination history (anti-combo repetition)

Implements the Anti-Center Mechanism:
  - Popularity Suppression: frequently used tags → weight decreases
  - Edge Promotion: rare tags → weight increases
  This ensures the system continuously drifts away from equilibrium.
"""

import time
from collections import deque, Counter


class EngineMemory:
    """
    Memory system for the Becoming engine.
    Unlike the basic MemorySystem, this tracks tags, popularity,
    density trends, and supports anti-center mechanics.
    """

    def __init__(
        self,
        recent_window: int = 30,
        combo_window: int = 15,
        tag_window: int = 50,
    ):
        self.recent_window = recent_window
        self.combo_window = combo_window
        self.tag_window = tag_window

        # Recent fragment tracking
        self._recent: deque[str] = deque(maxlen=recent_window)
        self._cooldowns: dict[str, float] = {}

        # Tag tracking for variety
        self._recent_tags: deque[str] = deque(maxlen=tag_window)

        # Play counts (lifetime popularity)
        self._play_counts: Counter = Counter()
        self._tag_play_counts: Counter = Counter()

        # Layer combination tracking
        self._combos: deque[frozenset] = deque(maxlen=combo_window)

        # Density trend: rolling window of active layer counts
        self._density_history: deque[int] = deque(maxlen=60)  # ~60 ticks

        # Event timing
        self._last_event_time: float = 0.0

    # ── Fragment tracking ───────────────────────────────────────────────

    def register_play(self, fragment_id: str, tags: list[str], cooldown: float):
        """Record that a fragment was played."""
        self._recent.append(fragment_id)
        self._cooldowns[fragment_id] = time.time() + cooldown
        self._play_counts[fragment_id] += 1
        for tag in tags:
            self._recent_tags.append(tag)
            self._tag_play_counts[tag] += 1

    def is_on_cooldown(self, fragment_id: str) -> bool:
        return time.time() < self._cooldowns.get(fragment_id, 0)

    def was_recently_played(self, fragment_id: str) -> bool:
        return fragment_id in self._recent

    def is_allowed(self, fragment_id: str) -> bool:
        return not self.is_on_cooldown(fragment_id) and not self.was_recently_played(fragment_id)

    def cooldown_remaining(self, fragment_id: str) -> float:
        return max(0.0, self._cooldowns.get(fragment_id, 0) - time.time())

    # ── Combo tracking ──────────────────────────────────────────────────

    def register_combo(self, active_ids: list[str]):
        self._combos.append(frozenset(active_ids))

    def combo_seen_recently(self, active_ids: list[str]) -> bool:
        return frozenset(active_ids) in self._combos

    # ── Density tracking ────────────────────────────────────────────────

    def register_density(self, count: int):
        self._density_history.append(count)

    def density_trend(self) -> float:
        """
        Returns density trend: positive = increasing, negative = decreasing.
        Range roughly -1 to +1.
        """
        if len(self._density_history) < 10:
            return 0.0
        recent = list(self._density_history)
        first_half = sum(recent[:len(recent)//2]) / max(1, len(recent)//2)
        second_half = sum(recent[len(recent)//2:]) / max(1, len(recent) - len(recent)//2)
        max_val = max(max(recent), 1)
        return (second_half - first_half) / max_val

    # ── Event timing ────────────────────────────────────────────────────

    def register_event(self):
        self._last_event_time = time.time()

    def time_since_last_event(self) -> float:
        if self._last_event_time == 0:
            return float("inf")
        return time.time() - self._last_event_time

    # ── Anti-Center: Popularity Suppression ─────────────────────────────

    def rarity_boost(self, fragment_id: str) -> float:
        """
        Boost for rarely-played fragments. More plays → less boost.
        Range: 0.3 (very popular) to 2.0 (never played).
        """
        plays = self._play_counts.get(fragment_id, 0)
        if plays == 0:
            return 2.0
        return max(0.3, 1.0 / (1.0 + plays * 0.15))

    def recency_penalty(self, fragment_id: str) -> float:
        """
        Penalty for recently played fragments.
        Returns 1.0 if not recent, down to 0.1 if very recent.
        """
        if fragment_id not in self._recent:
            return 1.0
        # Position in recent: closer to end (more recent) = lower value
        positions = [i for i, fid in enumerate(self._recent) if fid == fragment_id]
        if not positions:
            return 1.0
        most_recent_pos = max(positions)
        recency = most_recent_pos / max(1, len(self._recent) - 1)
        return 0.1 + 0.9 * (1.0 - recency)

    def tag_staleness(self, tags: list[str]) -> float:
        """
        Boost for fragments whose tags haven't been heard recently.
        All-stale tags → boost. All-recent tags → penalty.
        Range: 0.5 (all tags recent) to 1.5 (all tags stale).
        """
        if not tags:
            return 1.0
        recent_set = set(self._recent_tags)
        stale_count = sum(1 for t in tags if t not in recent_set)
        ratio = stale_count / len(tags)
        return 0.5 + ratio  # 0.5 to 1.5

    # ── Bridge Tag Tracking ──────────────────────────────────────────────

    def register_bridge(self, tags: list[str]):
        """Record bridge tags used in a transition."""
        for t in tags:
            self._tag_play_counts[t] += 1

    def bridge_penalty(self, tag: str) -> float:
        """Penalty for overused bridge tags. 0 = fresh, up to ~0.5."""
        usage = self._tag_play_counts.get(tag, 0)
        if usage <= 2:
            return 0.0
        return min(0.5, usage * 0.03)

    # ── Summary ─────────────────────────────────────────────────────────

    def summary(self) -> dict:
        return {
            "recent_count": len(self._recent),
            "active_cooldowns": sum(1 for f in self._cooldowns if self.is_on_cooldown(f)),
            "total_plays": sum(self._play_counts.values()),
            "unique_played": len(self._play_counts),
            "density_trend": round(self.density_trend(), 3),
            "time_since_event": round(self.time_since_last_event(), 1),
            "top_tags": self._tag_play_counts.most_common(5),
        }
