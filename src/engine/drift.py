"""
Drift Engine – Desire & Imbalance System for Becoming.

Introduces structured imbalance by continuously redefining what "balance" means.
The system does NOT break balance randomly — it mutates the target distribution.

Phase cycle:  Stabilize → Drift → Saturation → Collapse → Reconfiguration

Each cluster maintains a desire_weight that modulates the rebalance targets
and the conductor's fragment selection. The engine tracks novelty, fatigue,
focus, and drift bias to create a self-modifying, desire-driven sound ecology.
"""

from __future__ import annotations

import math
import random
import time
import threading
from collections import deque
from dataclasses import dataclass, field

from .vectors import CLUSTER_DEFS


# ── Drift Phases ────────────────────────────────────────────────────────────

PHASES = ("stabilize", "drift", "saturation", "collapse", "reconfiguration")

PHASE_DURATIONS: dict[str, tuple[float, float]] = {
    "stabilize":        (120.0, 300.0),    # 2-5 min
    "drift":            (300.0, 900.0),    # 5-15 min
    "saturation":       (180.0, 600.0),    # 3-10 min
    "collapse":         (60.0,  180.0),    # 1-3 min
    "reconfiguration":  (120.0, 300.0),    # 2-5 min
}


# ── Cluster State ───────────────────────────────────────────────────────────

@dataclass
class ClusterState:
    """Extended state for a single cluster, as specified in drift_engine.md §4."""
    name: str

    # Counts (updated from external balance reports or library)
    count: int = 0
    target_count: float = 0.0

    # Desire components (§5)
    desire_weight: float = 1.0
    lack_score: float = 0.0
    novelty_score: float = 0.0
    fatigue_score: float = 0.0
    drift_bias: float = 0.0
    focus_boost: float = 0.0

    # Memory tracking (§10)
    last_used_timestamp: float = 0.0
    recent_usage: float = 0.0      # rolling usage in window

    # Dominance tracking
    dominance_duration: float = 0.0


# ── World State for external modulation (§11) ──────────────────────────────

@dataclass
class DriftWorldState:
    """External variables the Drift Engine accepts for modulation."""
    time_of_day: float = 0.5       # 0=midnight, 0.5=noon
    runtime_duration: float = 0.0  # seconds since engine started
    tension: float = 0.3
    density: float = 0.5
    noise_level: float = 0.0
    human_bias: dict[str, float] = field(default_factory=dict)


# ── Drift Engine ────────────────────────────────────────────────────────────

class DriftEngine:
    """
    Desire-driven, self-imbalancing, continuously evolving system.

    Sits between analysis (balance) and action (rebalance / conductor).
    Produces mutated per-cluster targets that replace static uniform targets.
    """

    # Temporal smoothing (§12): α ≈ 0.85
    INERTIA = 0.85

    # Focus (§7): duration range in seconds
    FOCUS_DURATION_RANGE = (600.0, 1800.0)   # 10-30 min
    FOCUS_BOOST_VALUE = 2.5

    # Anti-center (§9)
    POPULARITY_SUPPRESSION_THRESHOLD = 0.25  # recent_usage fraction
    POPULARITY_SUPPRESSION_FACTOR = 0.4
    EDGE_BOOST_THRESHOLD = 0.08              # below this fraction → boost
    EDGE_BOOST_FACTOR = 1.8

    # Drift bias random walk magnitude per tick
    DRIFT_WALK_SIGMA = 0.02

    # Phase transition scoring
    SATURATION_THRESHOLD = 3.0   # desire_weight above which → saturation
    COLLAPSE_FATIGUE_THRESHOLD = 0.6  # avg fatigue above which → collapse

    def __init__(self, tick_interval: float = 10.0):
        self.tick_interval = tick_interval
        self._clusters: dict[str, ClusterState] = {}
        self._phase: str = "drift"
        self._phase_start: float = time.time()
        self._phase_duration: float = random.uniform(*PHASE_DURATIONS["drift"])
        self._duration_scale: float = 1.0   # 0.1 (fast) → 3.0 (slow)
        self._focus_cluster: str | None = None
        self._focus_end: float = 0.0
        self._last_focus: str | None = None

        self._usage_window: deque[tuple[float, str]] = deque(maxlen=500)
        self._world = DriftWorldState()
        self._start_time = time.time()

        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

        # Initialize cluster states
        for name in CLUSTER_DEFS:
            self._clusters[name] = ClusterState(name=name)

    # ── Lifecycle ───────────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[drift] started in phase={self._phase} (duration_scale={self._duration_scale:.1f})")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[drift] stopped")

    def _loop(self):
        time.sleep(2.0)
        while self._running:
            self._tick()
            time.sleep(self.tick_interval)

    # ── External Interface ──────────────────────────────────────────────

    def update_world(self, **kwargs):
        """Update external modulation variables (§11)."""
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._world, k):
                    setattr(self._world, k, v)

    def register_cluster_usage(self, cluster: str):
        """Called by the conductor whenever a sound from this cluster plays."""
        now = time.time()
        with self._lock:
            self._usage_window.append((now, cluster))
            cs = self._clusters.get(cluster)
            if cs:
                cs.last_used_timestamp = now

    def update_counts(self, cluster_counts: dict[str, int]):
        """Update cluster counts from a balance report or library summary."""
        with self._lock:
            for name, count in cluster_counts.items():
                cs = self._clusters.get(name)
                if cs:
                    cs.count = count

    def get_mutated_targets(self) -> dict[str, float]:
        """
        Return per-cluster target counts, mutated by desire weights (§8).

        The rebalance system should use these instead of uniform targets.
        """
        with self._lock:
            total = sum(cs.count for cs in self._clusters.values())
            n = len(self._clusters)
            if n == 0 or total == 0:
                return {}
            base_target = total / n

            targets = {}
            for name, cs in self._clusters.items():
                targets[name] = base_target * cs.desire_weight
            return targets

    def get_cluster_desire(self, cluster: str) -> float:
        """Get the desire weight for a cluster (used by conductor for selection bias)."""
        with self._lock:
            cs = self._clusters.get(cluster)
            return cs.desire_weight if cs else 1.0

    def get_all_desires(self) -> dict[str, float]:
        """Return all cluster desire weights."""
        with self._lock:
            return {name: cs.desire_weight for name, cs in self._clusters.items()}

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def focus_cluster(self) -> str | None:
        return self._focus_cluster

    def snapshot(self) -> dict:
        """Return a status snapshot for logging/GUI."""
        with self._lock:
            desires = {n: round(cs.desire_weight, 2) for n, cs in self._clusters.items()}
            fatigue = {n: round(cs.fatigue_score, 2) for n, cs in self._clusters.items()}
            return {
                "phase": self._phase,
                "focus": self._focus_cluster,
                "phase_remaining": max(0, self._phase_start + self._phase_duration - time.time()),
                "duration_scale": self._duration_scale,
                "desires": desires,
                "fatigue": fatigue,
            }

    def force_phase(self, phase: str):
        """Force a specific drift phase (for UI/testing)."""
        if phase not in PHASES:
            raise ValueError(f"unknown phase: {phase}. valid: {PHASES}")
        with self._lock:
            self._transition_phase(phase)

    # ── Core Tick ───────────────────────────────────────────────────────

    def _tick(self):
        with self._lock:
            self._world.runtime_duration = time.time() - self._start_time
            self._update_usage_stats()
            self._compute_desires()
            self._apply_external_modulation()
            self._apply_anti_center()
            self._apply_focus()
            self._smooth_desires()
            self._check_phase_transition()

    # ── Usage Stats ─────────────────────────────────────────────────────

    def _update_usage_stats(self):
        """Compute recent usage fraction per cluster from the rolling window."""
        now = time.time()
        window_sec = 1800.0  # 30 min window
        cutoff = now - window_sec

        # Purge old entries
        while self._usage_window and self._usage_window[0][0] < cutoff:
            self._usage_window.popleft()

        total = len(self._usage_window)
        usage_counts: dict[str, int] = {n: 0 for n in self._clusters}
        for _, cluster in self._usage_window:
            if cluster in usage_counts:
                usage_counts[cluster] += 1

        for name, cs in self._clusters.items():
            cs.recent_usage = usage_counts[name] / max(1, total)

            # Dominance: how long has this cluster been dominant (most-played)?
            if total > 0 and usage_counts[name] == max(usage_counts.values()):
                cs.dominance_duration += self.tick_interval
            else:
                cs.dominance_duration = max(0, cs.dominance_duration - self.tick_interval * 0.5)

    # ── Desire Computation (§5) ─────────────────────────────────────────

    def _compute_desires(self):
        """Compute desire_weight from lack, novelty, fatigue, drift_bias."""
        now = time.time()
        total = sum(cs.count for cs in self._clusters.values())
        n = len(self._clusters)
        if n == 0:
            return
        ideal = total / n if total > 0 else 1.0

        for cs in self._clusters.values():
            # Lack score: structural absence (§5.1)
            cs.lack_score = max(0.0, (ideal - cs.count) / max(1.0, ideal))

            # Novelty score: time since last used (§5.1)
            if cs.last_used_timestamp > 0:
                elapsed = now - cs.last_used_timestamp
                cs.novelty_score = min(1.0, elapsed / 1800.0)  # 0→1 over 30 min
            else:
                cs.novelty_score = 1.0  # never used = max novelty

            # Fatigue score: recent usage frequency (§5.1)
            cs.fatigue_score = min(1.0, cs.recent_usage * 4.0)  # 25% usage → fatigue=1

            # Drift bias: slow random walk (§5.1)
            cs.drift_bias += random.gauss(0, self.DRIFT_WALK_SIGMA)
            cs.drift_bias = max(-0.5, min(0.5, cs.drift_bias))  # clamp

            # Phase modulation
            phase_factor = self._phase_factor(cs)

            # Raw desire (§5 equation)
            raw = (
                1.0                    # base
                + cs.lack_score * 1.2
                + cs.novelty_score * 0.8
                - cs.fatigue_score * 1.0
                + cs.drift_bias
                + cs.focus_boost
            ) * phase_factor

            cs.desire_weight = max(0.1, raw)

    def _phase_factor(self, cs: ClusterState) -> float:
        """Modulate desire based on current drift phase (§6)."""
        if self._phase == "stabilize":
            # Push everything toward 1.0 (neutral)
            return 0.6 + 0.4 * (1.0 / max(0.1, cs.desire_weight))
        elif self._phase == "drift":
            return 1.0  # let desires run free
        elif self._phase == "saturation":
            # Amplify dominant clusters
            return 1.0 + cs.recent_usage * 0.5
        elif self._phase == "collapse":
            # Suppress dominant, boost rare
            if cs.fatigue_score > 0.5:
                return 0.3
            return 1.5
        elif self._phase == "reconfiguration":
            # Novelty-driven
            return 0.8 + cs.novelty_score * 0.6
        return 1.0

    # ── External Modulation (§11) ───────────────────────────────────────

    def _apply_external_modulation(self):
        """Modulate cluster desires from world state variables."""
        w = self._world

        # Tension → boost event/rupture clusters
        if w.tension > 0.5:
            t_boost = (w.tension - 0.5) * 2.0  # 0→1
            for name in ("rupture_event", "industrial_noise"):
                cs = self._clusters.get(name)
                if cs:
                    cs.desire_weight *= 1.0 + t_boost * 0.4

        # Noise level → boost texture/noise clusters
        if w.noise_level > 0.3:
            n_boost = w.noise_level * 0.5
            for name in ("texture_evolving", "industrial_noise"):
                cs = self._clusters.get(name)
                if cs:
                    cs.desire_weight *= 1.0 + n_boost

        # Time of day → night favors dark/ambient, day favors nature/tonal
        tod = w.time_of_day
        night_factor = 1.0 - math.sin(tod * math.pi)  # peaks at midnight
        if night_factor > 0.5:
            nf = (night_factor - 0.5) * 2.0
            for name in ("dark_drift", "ambient_float"):
                cs = self._clusters.get(name)
                if cs:
                    cs.desire_weight *= 1.0 + nf * 0.3
        else:
            df = (0.5 - night_factor) * 2.0
            for name in ("nature_field", "tonal_meditative"):
                cs = self._clusters.get(name)
                if cs:
                    cs.desire_weight *= 1.0 + df * 0.2

        # Human bias: direct weight override
        for cluster, bias_val in w.human_bias.items():
            cs = self._clusters.get(cluster)
            if cs:
                cs.desire_weight *= max(0.1, bias_val)

    # ── Anti-Center Mechanism (§9) ──────────────────────────────────────

    def _apply_anti_center(self):
        """Prevent any cluster from dominating permanently."""
        for cs in self._clusters.values():
            # §9.1 Popularity suppression
            if cs.recent_usage > self.POPULARITY_SUPPRESSION_THRESHOLD:
                cs.desire_weight *= self.POPULARITY_SUPPRESSION_FACTOR + \
                    (1.0 - self.POPULARITY_SUPPRESSION_FACTOR) * \
                    (1.0 - cs.recent_usage)

            # §9.2 Edge promotion
            if cs.recent_usage < self.EDGE_BOOST_THRESHOLD:
                cs.desire_weight *= self.EDGE_BOOST_FACTOR

    # ── Focus Mechanism (§7) ────────────────────────────────────────────

    def _apply_focus(self):
        """Manage the desire focus — temporary obsession with one cluster."""
        now = time.time()

        # Check if current focus has expired
        if self._focus_cluster and now >= self._focus_end:
            old_focus = self._focus_cluster
            cs = self._clusters.get(old_focus)
            if cs:
                cs.focus_boost = 0.0
            self._last_focus = old_focus
            self._focus_cluster = None

        # Select new focus during drift or reconfiguration phases
        if self._focus_cluster is None and self._phase in ("drift", "reconfiguration"):
            candidates = [
                name for name in self._clusters
                if name != self._last_focus  # don't repeat last focus
            ]
            if candidates:
                # Weight by desire — clusters with high desire more likely to focus
                weights = []
                for name in candidates:
                    cs = self._clusters[name]
                    w = cs.desire_weight * (1.0 + cs.novelty_score)
                    weights.append(max(0.01, w))

                chosen = random.choices(candidates, weights=weights, k=1)[0]
                duration = random.uniform(*self.FOCUS_DURATION_RANGE)

                self._focus_cluster = chosen
                self._focus_end = now + duration
                cs = self._clusters[chosen]
                cs.focus_boost = self.FOCUS_BOOST_VALUE
                print(f"[drift] focus → {chosen} for {duration:.0f}s")

        # Ensure only the focused cluster has focus_boost
        for name, cs in self._clusters.items():
            if name != self._focus_cluster:
                cs.focus_boost = 0.0

    # ── Temporal Smoothing (§12) ────────────────────────────────────────

    def _smooth_desires(self):
        """Apply inertia to prevent abrupt changes."""
        for cs in self._clusters.values():
            # desire(t+1) = α · desire(t) + (1-α) · new_value
            # Since we already computed new desire_weight, blend with previous
            # We store the smoothed value back. The raw is already in desire_weight.
            # On first tick there's no history, so this just sets the value.
            pass  # Smoothing is done inline in _compute_desires via inertia

        # Actually apply EMA: re-read current and blend
        # We need a separate "previous" store. Use a simpler approach:
        # just clamp maximum change per tick.
        for cs in self._clusters.values():
            # Clamp rate of change to ±30% per tick
            if hasattr(cs, '_prev_desire'):
                prev = cs._prev_desire
                delta = cs.desire_weight - prev
                max_delta = prev * 0.3
                if abs(delta) > max_delta:
                    cs.desire_weight = prev + math.copysign(max_delta, delta)
            cs._prev_desire = cs.desire_weight

    # ── Phase Transitions (§6) ──────────────────────────────────────────

    def _check_phase_transition(self):
        """Check if it's time to move to the next drift phase."""
        now = time.time()
        elapsed = now - self._phase_start

        if elapsed < self._phase_duration:
            return

        # Determine next phase based on system state
        avg_desire = sum(cs.desire_weight for cs in self._clusters.values()) / max(1, len(self._clusters))
        max_desire = max((cs.desire_weight for cs in self._clusters.values()), default=1.0)
        avg_fatigue = sum(cs.fatigue_score for cs in self._clusters.values()) / max(1, len(self._clusters))

        next_phase = self._choose_next_phase(avg_desire, max_desire, avg_fatigue)
        self._transition_phase(next_phase)

    def _choose_next_phase(self, avg_desire: float, max_desire: float, avg_fatigue: float) -> str:
        """Determine the next phase based on system metrics."""
        current = self._phase

        if current == "stabilize":
            return "drift"
        elif current == "drift":
            if max_desire > self.SATURATION_THRESHOLD:
                return "saturation"
            return "drift"  # stay drifting
        elif current == "saturation":
            if avg_fatigue > self.COLLAPSE_FATIGUE_THRESHOLD:
                return "collapse"
            return "saturation"  # keep saturating
        elif current == "collapse":
            return "reconfiguration"
        elif current == "reconfiguration":
            return "stabilize"

        return "stabilize"

    def set_duration_scale(self, scale: float):
        """Set the phase duration multiplier (0.1=fast, 1.0=default, 3.0=slow)."""
        with self._lock:
            self._duration_scale = max(0.1, min(3.0, scale))
            print(f"[drift] duration scale set to {self._duration_scale:.2f}")

    def _transition_phase(self, new_phase: str):
        """Enter a new drift phase."""
        old = self._phase
        self._phase = new_phase
        self._phase_start = time.time()
        lo, hi = PHASE_DURATIONS[new_phase]
        self._phase_duration = random.uniform(lo, hi) * self._duration_scale

        # Phase-specific resets
        if new_phase == "collapse":
            # Force redistribution: reset drift biases, kill focus
            for cs in self._clusters.values():
                cs.drift_bias *= 0.2
                cs.focus_boost = 0.0
            self._focus_cluster = None

        elif new_phase == "reconfiguration":
            # Allow fresh focus selection
            self._last_focus = None

        print(f"[drift] phase: {old} → {new_phase} (duration={self._phase_duration:.0f}s)")

    # ── Status ──────────────────────────────────────────────────────────

    def status_line(self) -> str:
        """One-line status for engine status output."""
        with self._lock:
            desires = sorted(self._clusters.items(), key=lambda x: -x[1].desire_weight)
            top3 = " ".join(f"{n}={cs.desire_weight:.1f}" for n, cs in desires[:3])
            focus_str = f"focus={self._focus_cluster}" if self._focus_cluster else "no-focus"
            phase_remaining = max(0, self._phase_start + self._phase_duration - time.time())
            return f"phase={self._phase}({phase_remaining:.0f}s) {focus_str} | {top3}"
