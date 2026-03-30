"""
Need Detector — Runtime Self-Awareness for Becoming Engine.

Evaluates the engine's current state and detects deficiencies:
  - Structural Deficit: missing roles or clusters
  - Stagnation: low variation, repeating clusters
  - Imbalance: one cluster dominates too heavily
  - Underfill: too few active layers
  - Rupture Need: too long since last event

Produces a NeedSignal that can trigger autonomous harvest.
"""

from __future__ import annotations

import logging
import math
import time
from collections import Counter
from dataclasses import dataclass, field

log = logging.getLogger("need_detector")

# ── Constants ───────────────────────────────────────────────────────────────

HARVEST_COOLDOWN = 300  # seconds between autonomous harvests

# Thresholds
MIN_LAYERS = 2                 # below this → underfill
CLUSTER_DOMINANCE = 0.55       # one cluster > 55% of recent history → imbalance
STAGNATION_RUN_LENGTH = 6      # same cluster N times in a row → stagnation
STAGNATION_ENTROPY_MIN = 1.2   # Shannon entropy below this → stagnation
RUPTURE_EVENT_TIMEOUT = 300.0  # seconds without event → rupture_need
FOCUS_SUPPRESS_INTENSITY = 0.8 # during focus, only trigger if intensity > this

# Mode mapping per spec §9
MODE_MAP = {
    "deficit": "balance",
    "stagnation": "drift",
    "imbalance": "hybrid",
    "rupture_need": "drift",
    "underfill": "balance",
}


# ── Data structures ─────────────────────────────────────────────────────────

@dataclass
class NeedSignal:
    """Output of a single evaluation cycle."""
    trigger: bool = False
    need_type: str = ""            # deficit / stagnation / imbalance / underfill / rupture_need
    target_clusters: list[str] = field(default_factory=list)
    intensity: float = 0.0        # 0.0–1.0
    mode: str = "balance"          # balance / hybrid / drift
    reason: str = ""


@dataclass
class RuntimeState:
    """Snapshot of conductor runtime state for evaluation."""
    current_state: str = "submerged"
    layer_count: int = 0
    max_layers: int = 4
    role_distribution: dict[str, int] = field(default_factory=dict)
    cluster_history: list[str] = field(default_factory=list)
    cluster_run_length: int = 0
    role_demand: dict[str, int] = field(default_factory=dict)


@dataclass
class MemoryState:
    """Snapshot of engine memory state for evaluation."""
    recent_tags: list[str] = field(default_factory=list)
    density_trend: float = 0.0
    time_since_event: float = 0.0
    total_plays: int = 0
    tag_play_counts: dict[str, int] = field(default_factory=dict)


# ── Need Detector ───────────────────────────────────────────────────────────

class NeedDetector:
    """
    Evaluates runtime + memory state and emits NeedSignal
    when the engine needs new material.
    """

    def __init__(self):
        self._last_harvest_time: float = 0.0
        self._last_signal: NeedSignal | None = None

    @property
    def cooldown_remaining(self) -> float:
        return max(0.0, HARVEST_COOLDOWN - (time.time() - self._last_harvest_time))

    def record_harvest(self):
        """Call after a harvest is triggered to start cooldown."""
        self._last_harvest_time = time.time()

    def evaluate(
        self,
        runtime: RuntimeState,
        memory: MemoryState,
        *,
        focus_active: bool = False,
        collapse_active: bool = False,
    ) -> NeedSignal:
        """
        Evaluate the engine state and return a NeedSignal.
        Safe to call every few seconds — respects cooldown internally.
        """
        # Cooldown check
        if time.time() - self._last_harvest_time < HARVEST_COOLDOWN:
            return NeedSignal()

        # During focus, suppress unless extreme
        if focus_active:
            # Only allow if we detect something truly critical
            signal = self._evaluate_inner(runtime, memory, suppress_threshold=FOCUS_SUPPRESS_INTENSITY)
            if signal.trigger:
                signal.reason += " (overrode focus suppression)"
            return signal

        # During collapse, always allow — force drift mode
        if collapse_active:
            signal = self._evaluate_inner(runtime, memory, suppress_threshold=0.0)
            if signal.trigger:
                signal.mode = "drift"
                signal.reason += " (collapse active → drift)"
            return signal

        return self._evaluate_inner(runtime, memory, suppress_threshold=0.0)

    def _evaluate_inner(
        self,
        runtime: RuntimeState,
        memory: MemoryState,
        suppress_threshold: float,
    ) -> NeedSignal:
        """Run all trigger conditions and return the strongest signal."""
        signals: list[NeedSignal] = []

        # 1. Structural deficit
        sig = self._check_deficit(runtime)
        if sig.trigger:
            signals.append(sig)

        # 2. Stagnation
        sig = self._check_stagnation(runtime, memory)
        if sig.trigger:
            signals.append(sig)

        # 3. Imbalance
        sig = self._check_imbalance(runtime)
        if sig.trigger:
            signals.append(sig)

        # 4. Underfill
        sig = self._check_underfill(runtime)
        if sig.trigger:
            signals.append(sig)

        # 5. Rupture need
        sig = self._check_rupture_need(memory)
        if sig.trigger:
            signals.append(sig)

        if not signals:
            return NeedSignal()

        # Pick highest intensity signal
        best = max(signals, key=lambda s: s.intensity)

        # Apply suppression threshold (used during focus)
        if best.intensity < suppress_threshold:
            return NeedSignal()

        self._last_signal = best
        return best

    # ── Trigger conditions ──────────────────────────────────────────────

    def _check_deficit(self, runtime: RuntimeState) -> NeedSignal:
        """Missing roles or empty clusters in recent history."""
        expected_roles = {"ground", "texture"}  # roles that should usually be present
        active_roles = {r for r, c in runtime.role_distribution.items() if c > 0}
        missing_roles = expected_roles - active_roles

        # Check cluster coverage: if recent history uses < 3 distinct clusters
        cluster_set = set(runtime.cluster_history) if runtime.cluster_history else set()
        cluster_gap = max(0, 3 - len(cluster_set))

        if not missing_roles and cluster_gap == 0:
            return NeedSignal()

        # Intensity: more missing → stronger
        intensity = min(1.0, 0.3 * len(missing_roles) + 0.2 * cluster_gap)

        # Target: clusters not appearing in recent history
        all_clusters = {
            "dark_drift", "tonal_meditative", "nature_field", "urban_field",
            "industrial_noise", "texture_evolving", "pulse_rhythm",
            "rupture_event", "ambient_float",
        }
        targets = sorted(all_clusters - cluster_set) if cluster_gap > 0 else []
        # Limit to 3 target clusters
        targets = targets[:3]

        reason_parts = []
        if missing_roles:
            reason_parts.append(f"missing roles: {missing_roles}")
        if cluster_gap > 0:
            reason_parts.append(f"only {len(cluster_set)} clusters in recent history")

        return NeedSignal(
            trigger=True,
            need_type="deficit",
            target_clusters=targets,
            intensity=intensity,
            mode="balance",
            reason="; ".join(reason_parts),
        )

    def _check_stagnation(self, runtime: RuntimeState, memory: MemoryState) -> NeedSignal:
        """Low variation: same clusters repeating, low entropy."""
        history = runtime.cluster_history
        if len(history) < 5:
            return NeedSignal()

        # Metric 1: cluster run length (same cluster N times in a row)
        run = runtime.cluster_run_length
        run_stagnant = run >= STAGNATION_RUN_LENGTH

        # Metric 2: Shannon entropy of recent cluster distribution
        counter = Counter(history[-15:])  # last 15 entries
        total = sum(counter.values())
        entropy = 0.0
        for count in counter.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        entropy_stagnant = entropy < STAGNATION_ENTROPY_MIN

        # Metric 3: density trend (flat or declining for a while)
        density_flat = abs(memory.density_trend) < 0.05

        if not (run_stagnant or entropy_stagnant):
            return NeedSignal()

        # Intensity based on how stagnant
        intensity = 0.0
        if run_stagnant:
            intensity += min(0.5, (run - STAGNATION_RUN_LENGTH) * 0.1 + 0.3)
        if entropy_stagnant:
            intensity += min(0.4, (STAGNATION_ENTROPY_MIN - entropy) * 0.3 + 0.2)
        if density_flat:
            intensity += 0.1
        intensity = min(1.0, max(0.2, intensity))

        # Target: least recently used clusters
        recent_counts = Counter(history)
        all_clusters = {
            "dark_drift", "tonal_meditative", "nature_field", "urban_field",
            "industrial_noise", "texture_evolving", "pulse_rhythm",
            "rupture_event", "ambient_float",
        }
        sorted_clusters = sorted(all_clusters, key=lambda c: recent_counts.get(c, 0))
        targets = sorted_clusters[:3]

        reason_parts = []
        if run_stagnant:
            reason_parts.append(f"cluster run length {run}")
        if entropy_stagnant:
            reason_parts.append(f"low entropy {entropy:.2f}")
        if density_flat:
            reason_parts.append("flat density")

        return NeedSignal(
            trigger=True,
            need_type="stagnation",
            target_clusters=targets,
            intensity=intensity,
            mode="drift",
            reason="; ".join(reason_parts),
        )

    def _check_imbalance(self, runtime: RuntimeState) -> NeedSignal:
        """One cluster dominates recent history too heavily."""
        history = runtime.cluster_history
        if len(history) < 8:
            return NeedSignal()

        counter = Counter(history[-20:])
        total = sum(counter.values())
        dominant_cluster, dominant_count = counter.most_common(1)[0]
        dominance = dominant_count / total

        if dominance < CLUSTER_DOMINANCE:
            return NeedSignal()

        intensity = min(1.0, max(0.2, (dominance - CLUSTER_DOMINANCE) * 3.0 + 0.3))

        # Target: everything except the dominant cluster
        all_clusters = {
            "dark_drift", "tonal_meditative", "nature_field", "urban_field",
            "industrial_noise", "texture_evolving", "pulse_rhythm",
            "rupture_event", "ambient_float",
        }
        targets = sorted(all_clusters - {dominant_cluster})[:3]

        return NeedSignal(
            trigger=True,
            need_type="imbalance",
            target_clusters=targets,
            intensity=intensity,
            mode="hybrid",
            reason=f"{dominant_cluster} at {dominance:.0%}",
        )

    def _check_underfill(self, runtime: RuntimeState) -> NeedSignal:
        """Too few active layers."""
        if runtime.layer_count >= MIN_LAYERS:
            return NeedSignal()

        intensity = min(1.0, max(0.3, (MIN_LAYERS - runtime.layer_count) * 0.4 + 0.3))

        # Target: clusters matching demanded roles
        # For underfill we want generic expansion
        return NeedSignal(
            trigger=True,
            need_type="underfill",
            target_clusters=[],  # let harvest decide
            intensity=intensity,
            mode="balance",
            reason=f"only {runtime.layer_count} layers (min {MIN_LAYERS})",
        )

    def _check_rupture_need(self, memory: MemoryState) -> NeedSignal:
        """Too long since the last event sound."""
        if memory.time_since_event < RUPTURE_EVENT_TIMEOUT:
            return NeedSignal()

        elapsed = memory.time_since_event
        intensity = min(1.0, max(0.3, (elapsed - RUPTURE_EVENT_TIMEOUT) / 300.0 + 0.3))

        return NeedSignal(
            trigger=True,
            need_type="rupture_need",
            target_clusters=["rupture_event", "pulse_rhythm"],
            intensity=intensity,
            mode="drift",
            reason=f"no event for {elapsed:.0f}s",
        )


# ── Helper: build state snapshots from conductor ───────────────────────────

def build_runtime_state(conductor) -> RuntimeState:
    """Extract RuntimeState from a live Conductor instance."""
    layers = conductor.active_layers  # thread-safe copy
    ctx = conductor.context.snapshot()

    # Role distribution from active layers
    role_dist: dict[str, int] = {}
    for layer in layers.values():
        r = layer.role if isinstance(layer.role, str) else layer.role.value
        role_dist[r] = role_dist.get(r, 0) + 1

    return RuntimeState(
        current_state=conductor.state.current,
        layer_count=len(layers),
        max_layers=conductor.state.get_max_layers(),
        role_distribution=role_dist,
        cluster_history=ctx.cluster_history,
        cluster_run_length=conductor.context.cluster_run_length(),
    )


def build_memory_state(memory) -> MemoryState:
    """Extract MemoryState from a live EngineMemory instance."""
    summary = memory.summary()
    return MemoryState(
        recent_tags=list(memory._recent_tags),
        density_trend=summary["density_trend"],
        time_since_event=summary["time_since_event"],
        total_plays=summary["total_plays"],
        tag_play_counts=dict(memory._tag_play_counts),
    )
