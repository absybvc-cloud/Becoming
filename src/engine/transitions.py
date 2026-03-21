"""
Transition engine for Becoming.

This is the CORE of the Phase 2 concept:
  "each sound selects the next sound"

Three transition types:
  CONTINUE  - select nearest neighbors, high similarity, low novelty
  DRIFT     - partial tag overlap, introduce 1-2 new semantic dimensions
  RUPTURE   - low similarity, must share at least one bridge tag or role compatibility

Candidate scoring:
  score = similarity + role_compatibility + novelty_bonus
        - repetition_penalty - cluster_penalty

Selection is probabilistic (NOT argmax).
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from .roles import SoundFragment, Role
from .vectors import SemanticVector, RoleVector, assign_cluster
from .context import ContextWindow, ContextSnapshot
from .memory import EngineMemory


class TransitionType(str, Enum):
    CONTINUE = "continue"
    DRIFT = "drift"
    RUPTURE = "rupture"


@dataclass
class TransitionResult:
    """Result of a transition decision."""
    fragment: SoundFragment
    transition_type: TransitionType
    bridge_tags: list[str]
    score: float
    similarity: float


@dataclass
class CandidateScore:
    fragment: SoundFragment
    total: float
    similarity: float
    role_compat: float
    novelty: float
    repetition_pen: float
    cluster_pen: float
    bridge_tags: list[str]


# ── Transition Type Selector ────────────────────────────────────────────────

# Base probabilities per system state.  Overridden by temperature.
STATE_TRANSITION_BIAS: dict[str, dict[TransitionType, float]] = {
    "submerged":  {TransitionType.CONTINUE: 0.60, TransitionType.DRIFT: 0.35, TransitionType.RUPTURE: 0.05},
    "tense":      {TransitionType.CONTINUE: 0.30, TransitionType.DRIFT: 0.40, TransitionType.RUPTURE: 0.30},
    "dissolved":  {TransitionType.CONTINUE: 0.65, TransitionType.DRIFT: 0.30, TransitionType.RUPTURE: 0.05},
    "rupture":    {TransitionType.CONTINUE: 0.15, TransitionType.DRIFT: 0.30, TransitionType.RUPTURE: 0.55},
    "drifting":   {TransitionType.CONTINUE: 0.35, TransitionType.DRIFT: 0.50, TransitionType.RUPTURE: 0.15},
}


class TransitionEngine:
    """
    Decides the NEXT sound based on the current context, transition type,
    and candidate scoring.
    """

    def __init__(
        self,
        memory: EngineMemory,
        temperature: float = 0.5,
        log_path: str | None = None,
    ):
        self.memory = memory
        self.temperature = max(0.0, min(1.0, temperature))
        self._bridge_usage: dict[str, int] = {}  # tag → times used as bridge
        self._log_path = log_path

    # ── Public API ──────────────────────────────────────────────────────

    def select_next(
        self,
        candidates: list[tuple[SoundFragment, SemanticVector, RoleVector]],
        context: ContextSnapshot,
        current_state: str,
        source_fragment: SoundFragment | None = None,
        source_vector: SemanticVector | None = None,
        for_role: Role | None = None,
    ) -> TransitionResult | None:
        """
        Select the next sound from candidates using semantic transitions.

        Returns None if no valid candidate found.
        """
        if not candidates:
            return None

        # 1. Choose transition type
        ttype = self._choose_transition_type(current_state, context)

        # 2. Score all candidates for this transition type
        scored = self._score_candidates(
            candidates, context, ttype,
            source_vector=source_vector or context.combined_vector,
            for_role=for_role,
        )

        if not scored:
            return None

        # 3. Probabilistic selection (NOT argmax)
        fragments = [s.fragment for s in scored]
        weights = [max(0.001, s.total) for s in scored]
        chosen_idx = random.choices(range(len(fragments)), weights=weights, k=1)[0]
        chosen = scored[chosen_idx]

        # 4. Record bridge usage
        for tag in chosen.bridge_tags:
            self._bridge_usage[tag] = self._bridge_usage.get(tag, 0) + 1

        # 5. Log transition
        self._log_transition(source_fragment, chosen.fragment, ttype, chosen.bridge_tags)

        return TransitionResult(
            fragment=chosen.fragment,
            transition_type=ttype,
            bridge_tags=chosen.bridge_tags,
            score=chosen.total,
            similarity=chosen.similarity,
        )

    def set_temperature(self, t: float):
        self.temperature = max(0.0, min(1.0, t))

    # ── Transition Type Selection ───────────────────────────────────────

    def _choose_transition_type(
        self, current_state: str, context: ContextSnapshot,
    ) -> TransitionType:
        bias = STATE_TRANSITION_BIAS.get(current_state, STATE_TRANSITION_BIAS["drifting"]).copy()

        # Temperature shifts toward drift/rupture
        temp = self.temperature
        bias[TransitionType.CONTINUE] *= (1.0 - temp * 0.6)
        bias[TransitionType.DRIFT] *= (0.7 + temp * 0.6)
        bias[TransitionType.RUPTURE] *= (0.3 + temp * 1.4)

        # Cluster run length: long runs push toward drift/rupture
        run = context.cluster_history[-3:].count(context.cluster_history[-1]) if context.cluster_history else 0
        if run >= 3:
            bias[TransitionType.DRIFT] *= 1.5
            bias[TransitionType.RUPTURE] *= 1.3
            bias[TransitionType.CONTINUE] *= 0.5

        types = list(bias.keys())
        weights = [max(0.01, bias[t]) for t in types]
        return random.choices(types, weights=weights, k=1)[0]

    # ── Candidate Scoring ───────────────────────────────────────────────

    def _score_candidates(
        self,
        candidates: list[tuple[SoundFragment, SemanticVector, RoleVector]],
        context: ContextSnapshot,
        ttype: TransitionType,
        source_vector: SemanticVector,
        for_role: Role | None = None,
    ) -> list[CandidateScore]:
        scored: list[CandidateScore] = []

        for frag, svec, rvec in candidates:
            # Skip cooldown / recently played
            if not self.memory.is_allowed(frag.id):
                continue

            # Optional role filter
            if for_role is not None and frag.role != for_role:
                continue

            sim = source_vector.similarity(svec)
            bridge_tags = list(source_vector.shared_tags(svec))
            role_compat = self._role_compatibility_score(rvec, context)
            novelty = self._novelty_score(frag, svec, context)
            rep_pen = self._repetition_penalty(frag, bridge_tags)
            cluster_pen = self._cluster_penalty(frag, context)

            # Combine based on transition type
            if ttype == TransitionType.CONTINUE:
                total = sim * 2.0 + role_compat * 0.5 + novelty * 0.3 - rep_pen - cluster_pen
            elif ttype == TransitionType.DRIFT:
                total = sim * 0.8 + role_compat * 0.8 + novelty * 1.5 - rep_pen - cluster_pen
                # Drift requires partial overlap (at least 1 bridge tag)
                if not bridge_tags:
                    total *= 0.2
            else:  # RUPTURE
                total = (1.0 - sim) * 1.5 + role_compat * 0.5 + novelty * 2.0 - rep_pen - cluster_pen
                # Rupture requires at least 1 bridge tag OR role compatibility
                if not bridge_tags and role_compat < 0.4:
                    total *= 0.1

            # Temperature noise
            total += random.gauss(0, self.temperature * 0.3)
            total = max(0.001, total)

            scored.append(CandidateScore(
                fragment=frag,
                total=total,
                similarity=sim,
                role_compat=role_compat,
                novelty=novelty,
                repetition_pen=rep_pen,
                cluster_pen=cluster_pen,
                bridge_tags=bridge_tags,
            ))

        return scored

    def _role_compatibility_score(self, rvec: RoleVector, context: ContextSnapshot) -> float:
        """How much the mix needs this sound's role characteristics."""
        role_dist = context.role_distribution
        total = sum(role_dist.values()) or 1

        # Favor sounds whose role is underrepresented
        score = 0.5
        if rvec.grounding > 0.5 and role_dist.get("ground", 0) / total < 0.3:
            score += 0.3
        if rvec.eventfulness > 0.5 and role_dist.get("event", 0) / total < 0.1:
            score += 0.2
        if rvec.pulse_strength > 0.5 and role_dist.get("pulse", 0) / total < 0.1:
            score += 0.2

        return min(1.0, score)

    def _novelty_score(
        self, frag: SoundFragment, svec: SemanticVector, context: ContextSnapshot,
    ) -> float:
        """Reward tags and clusters not in the recent context."""
        if not frag.tags:
            return 0.5

        # Tag novelty: fraction of tags NOT in dominant context tags
        dominant = set(context.dominant_tags)
        novel_count = sum(1 for t in frag.tags if t.lower() not in dominant)
        tag_novelty = novel_count / len(frag.tags)

        # Cluster novelty
        cluster = assign_cluster(frag)
        cluster_novelty = context.combined_vector.similarity(svec)
        # Invert: low similarity to context = high novelty
        cluster_novelty = 1.0 - cluster_novelty

        return tag_novelty * 0.6 + cluster_novelty * 0.4

    def _repetition_penalty(self, frag: SoundFragment, bridge_tags: list[str]) -> float:
        """Penalize repeated fragments, tags, and bridge patterns."""
        pen = 0.0

        # Fragment recency
        if self.memory.was_recently_played(frag.id):
            pen += 0.5

        # Rarity: popular fragments get penalized
        plays = self.memory._play_counts.get(frag.id, 0)
        if plays > 3:
            pen += min(0.5, plays * 0.05)

        # Bridge tag overuse
        for tag in bridge_tags:
            usage = self._bridge_usage.get(tag, 0)
            if usage > 5:
                pen += min(0.3, usage * 0.02)

        # Suppressed tags
        suppressed = set()
        # We handle this via the context snapshot in the caller
        return pen

    def _cluster_penalty(self, frag: SoundFragment, context: ContextSnapshot) -> float:
        """Penalize staying in the same cluster too long."""
        cluster = assign_cluster(frag)
        if not context.cluster_history:
            return 0.0

        # Count how many of the last N sounds were in this cluster
        recent = context.cluster_history[-5:]
        same_count = sum(1 for c in recent if c == cluster)
        if same_count <= 1:
            return 0.0
        return min(0.8, same_count * 0.15)

    # ── Transition Logging ──────────────────────────────────────────────

    def _log_transition(
        self,
        source: SoundFragment | None,
        target: SoundFragment,
        ttype: TransitionType,
        bridge_tags: list[str],
    ):
        if not self._log_path:
            return
        entry = {
            "from": source.id if source else None,
            "to": target.id,
            "type": ttype.value,
            "bridge_tags": bridge_tags,
            "timestamp": time.time(),
        }
        try:
            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # non-critical
