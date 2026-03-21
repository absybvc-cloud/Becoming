"""
Context window for the Becoming engine.

The next sound is NOT chosen based on the current sound alone.
The context window holds the last N sounds and produces:
  - a combined semantic vector (weighted average)
  - dominant tags across the window
  - suppressed tags (overused → penalized)
  - cluster history
  - role distribution
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field

from .roles import SoundFragment
from .vectors import SemanticVector, RoleVector, assign_cluster


@dataclass
class ContextSnapshot:
    """Immutable snapshot of the current context for transition decisions."""
    combined_vector: SemanticVector
    dominant_tags: list[str]
    suppressed_tags: set[str]
    cluster_history: list[str]
    role_distribution: dict[str, int]
    window_size: int


class ContextWindow:
    """
    Sliding context window over recent sounds.
    Decays older entries so the most recently played sounds
    contribute more to the combined vector.
    """

    def __init__(self, size: int = 5, suppression_threshold: int = 3):
        self.size = size
        self.suppression_threshold = suppression_threshold

        self._entries: deque[tuple[SoundFragment, SemanticVector]] = deque(maxlen=size)
        self._cluster_history: deque[str] = deque(maxlen=20)
        self._tag_counter: Counter = Counter()

    def push(self, fragment: SoundFragment, vector: SemanticVector):
        """Add a new sound to the context window."""
        self._entries.append((fragment, vector))
        cluster = assign_cluster(fragment)
        self._cluster_history.append(cluster)
        for tag in fragment.tags:
            self._tag_counter[tag.lower()] += 1

    def snapshot(self) -> ContextSnapshot:
        """Build a snapshot of the current context."""
        if not self._entries:
            return ContextSnapshot(
                combined_vector=SemanticVector(),
                dominant_tags=[],
                suppressed_tags=set(),
                cluster_history=[],
                role_distribution={},
                window_size=0,
            )

        # Combined vector: exponentially decay older entries
        combined = SemanticVector()
        total_w = 0.0
        for i, (_, vec) in enumerate(self._entries):
            age_weight = 0.5 + 0.5 * (i / max(1, len(self._entries) - 1))
            for tag, val in vec.weights.items():
                combined.weights[tag] = combined.weights.get(tag, 0.0) + val * age_weight
            total_w += age_weight

        if total_w > 0:
            combined.weights = {k: v / total_w for k, v in combined.weights.items()}

        # Dominant tags: top tags across window
        all_tags: Counter = Counter()
        for frag, vec in self._entries:
            for tag in frag.tags:
                all_tags[tag.lower()] += 1
        dominant = [t for t, _ in all_tags.most_common(8)]

        # Suppressed tags: overused in recent history
        suppressed = {t for t, c in self._tag_counter.items() if c >= self.suppression_threshold}

        # Role distribution
        role_dist: Counter = Counter()
        for frag, _ in self._entries:
            role_dist[frag.role.value] += 1

        return ContextSnapshot(
            combined_vector=combined,
            dominant_tags=dominant,
            suppressed_tags=suppressed,
            cluster_history=list(self._cluster_history),
            role_distribution=dict(role_dist),
            window_size=len(self._entries),
        )

    @property
    def last_fragment(self) -> SoundFragment | None:
        if self._entries:
            return self._entries[-1][0]
        return None

    @property
    def last_cluster(self) -> str | None:
        if self._cluster_history:
            return self._cluster_history[-1]
        return None

    def cluster_staleness(self, cluster: str) -> float:
        """
        How long since this cluster was used. Higher = more stale (novel).
        Returns 0.0 if it was the last cluster, up to 1.0 if never seen.
        """
        if cluster not in self._cluster_history:
            return 1.0
        # Find most recent occurrence
        for i, c in enumerate(reversed(self._cluster_history)):
            if c == cluster:
                return min(1.0, i / max(1, len(self._cluster_history)))
        return 1.0

    def cluster_run_length(self) -> int:
        """How many consecutive sounds from the same cluster."""
        if not self._cluster_history:
            return 0
        current = self._cluster_history[-1]
        count = 0
        for c in reversed(self._cluster_history):
            if c == current:
                count += 1
            else:
                break
        return count
