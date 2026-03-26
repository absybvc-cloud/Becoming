"""
Conductor (Scheduler) for the Becoming engine.

This is the MOST IMPORTANT module. It decides:
  - when to spawn a sound
  - which role needs filling
  - when to remove layers
  - when to trigger events
  - when to transition state

The conductor maintains a set of "active layers", each with a role,
and continuously adjusts the mix based on state, weights, and memory.
"""

import time
import random
import threading
from dataclasses import dataclass, field
from typing import Optional

from .roles import Role, SoundFragment
from .states import StateMachine
from .weights import WeightEngine
from .memory import EngineMemory
from .world import WorldInterface
from .library import SoundLibrary
from .active_pool import ActivePool
from .context import ContextWindow
from .transitions import TransitionEngine, TransitionType
from .vectors import SemanticVector, build_semantic_vector, assign_cluster
from .drift import DriftEngine
from .layers import Layer, LayerState, create_layer, update_layer, force_fade_out
from .interventions import (
    InterventionQueue, InterventionEffect, InterventionType,
    compute_combined_effect,
)
from ..playback_engine import PlaybackEngine


# ── Layer duration ranges per role (seconds) ───────────────────────────────
ROLE_DURATION_RANGE = {
    Role.GROUND: (60.0, 300.0),    # 1-5 min (long bed)
    Role.TEXTURE: (30.0, 120.0),   # 30s-2 min
    Role.EVENT: (3.0, 20.0),       # 3-20s (brief interruption)
    Role.PULSE: (20.0, 90.0),      # 20s-1.5 min
}

# Gain ranges per role
ROLE_GAIN = {
    Role.GROUND: (0.5, 0.8),
    Role.TEXTURE: (0.3, 0.6),
    Role.EVENT: (0.4, 0.7),
    Role.PULSE: (0.3, 0.5),
}


class Conductor:
    """
    The conductor drives the sonic ecology. Every tick it:
    1. Checks which layers should end (age-based)
    2. Determines which roles need filling (state-driven density)
    3. Decides whether to trigger an event
    4. Selects and spawns fragments using the weight engine
    5. Records everything in memory
    """

    def __init__(
        self,
        active_pool: ActivePool,
        playback: PlaybackEngine,
        state_machine: StateMachine,
        weight_engine: WeightEngine,
        memory: EngineMemory,
        world: WorldInterface,
        drift_engine: DriftEngine | None = None,
        intervention_queue: InterventionQueue | None = None,
        tick_interval: float = 2.0,
        temperature: float = 0.5,
        transition_log_path: str | None = None,
    ):
        self.pool = active_pool
        self.playback = playback
        self.state = state_machine
        self.weights = weight_engine
        self.memory = memory
        self.world = world
        self.drift = drift_engine
        self.interventions = intervention_queue or InterventionQueue()
        self.tick_interval = tick_interval

        self._layers: dict[str, Layer] = {}
        self._fragments: dict[str, SoundFragment] = {}  # layer_id → fragment
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tick_index: int = 0
        self._current_effect: InterventionEffect = InterventionEffect()

        # Phase 2: semantic transition engine + context window
        self.context = ContextWindow(size=5)
        self.transitions = TransitionEngine(
            memory=memory,
            temperature=temperature,
            log_path=transition_log_path,
            drift_engine=drift_engine,
        )

        # Optional callbacks invoked on each spawn: fn(fragment_id, role, tags)
        self.spawn_callbacks: list = []

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[conductor] started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[conductor] stopped")

    @property
    def active_layers(self) -> dict[str, Layer]:
        with self._lock:
            return dict(self._layers)

    @property
    def active_fragments(self) -> dict[str, SoundFragment]:
        """Return layer_id → SoundFragment for active layers."""
        with self._lock:
            return dict(self._fragments)

    # ── Main Loop ───────────────────────────────────────────────────────

    def _loop(self):
        # Small initial delay to let playback engine start
        time.sleep(1.0)
        while self._running:
            self._tick()
            time.sleep(self.tick_interval)

    def _tick(self):
        with self._lock:
            self._tick_index += 1

            # 0. Process interventions
            self._process_interventions()

            # 1. Sync with playback engine: remove layers whose audio stopped
            self._sync_with_playback()

            # 2. Update layer states (fade in/out gain ramps)
            self._update_layers()

            # 3. Clean up ended layers
            self._cleanup_ended()

            # 4. Record current density
            active_count = len(self._layers)
            self.memory.register_density(active_count)
            self.memory.register_combo(list(self._layers.keys()))

            # 5. Scheduling (unless suppressed by intervention)
            if not self._current_effect.suppress_new_spawns:
                if not self._current_effect.fade_all:
                    self._schedule()

            # 6. Check for event trigger (probabilistic)
            if not self._current_effect.suppress_new_spawns:
                active_ids = set(self._layers.keys())
                self._maybe_trigger_event(active_ids)

            # 7. Tick warmup counters for recently merged assets
            self.pool.tick_warmup()

            # ── Safe point: merge staging + refresh dirty metadata ──
            merged = self.pool.merge_staging()
            refreshed = self.pool.refresh_dirty_metadata()

            # 8. Trace output
            if self._tick_index % 5 == 0:
                self._emit_trace(merged, refreshed)

    # ── Layer Management ────────────────────────────────────────────────

    def _sync_with_playback(self):
        """Remove layers whose audio has finished in the playback engine."""
        playing = set(self.playback.active_ids())
        dead = [lid for lid in self._layers if lid not in playing]
        for lid in dead:
            self._layers[lid].state = LayerState.ENDED

    def _update_layers(self):
        """Advance every layer's fade state and gain."""
        dt = self.tick_interval
        for layer in self._layers.values():
            update_layer(layer, dt)
            # Push gain change to playback engine
            self.playback.set_gain(layer.layer_id, layer.current_gain)

    def _cleanup_ended(self):
        """Remove ended layers and release resources."""
        to_remove = [lid for lid, layer in self._layers.items() if layer.is_finished]
        for lid in to_remove:
            self.playback.stop_fragment(lid, crossfade=False)
            frag = self._fragments.pop(lid, None)
            del self._layers[lid]
            if frag:
                print(f"[conductor] ended: {lid} ({frag.role.value})")

    def _schedule(self):
        """Determine role demand and fill empty slots."""
        max_layers = self.state.get_max_layers()
        density_mod = self.world.get_density_modifier()
        # Apply intervention modifier
        max_layers = max(1, max_layers + self._current_effect.max_layers_delta)
        target = max(1, int(max_layers * density_mod))

        # Silence-as-structure: sometimes deliberately skip spawning
        living = [l for l in self._layers.values() if l.state != LayerState.ENDED]
        if len(living) >= target:
            return

        role_demand = self._compute_role_demand(target)
        active_ids = set(self._layers.keys())

        # Apply spawn rate multiplier (intervention can slow spawning)
        spawn_chance = self._current_effect.spawn_rate_mult
        if random.random() > spawn_chance:
            return  # silence-as-structure: skip this tick

        for role, needed in role_demand.items():
            for _ in range(needed):
                fragment = self._select_fragment(role, active_ids)
                if fragment:
                    self._spawn_layer(fragment)
                    active_ids.add(fragment.id)

    def _spawn_layer(self, fragment: SoundFragment):
        """Start a new layer using the Layer lifecycle system."""
        role = fragment.role
        dur_range = ROLE_DURATION_RANGE[role]

        expected_dur = random.uniform(*dur_range)
        if not fragment.loopable:
            expected_dur = min(expected_dur, fragment.duration)

        gain_range = ROLE_GAIN[role]
        target_gain = random.uniform(*gain_range)

        # Create a playback-compatible Fragment adapter
        adapter = _PlaybackAdapter(fragment)
        if not self.playback.play(adapter, gain=0.0):  # start silent, fade in
            return

        # Create layer with fade-in state
        layer = create_layer(
            fragment_id=fragment.id,
            asset_id=fragment.asset_id,
            role=role.value,
            duration=expected_dur,
            target_gain=target_gain,
        )
        # Use fragment.id as layer key for playback engine compatibility
        layer.layer_id = fragment.id

        self._layers[fragment.id] = layer
        self._fragments[fragment.id] = fragment
        self.memory.register_play(fragment.id, fragment.tags, fragment.cooldown)

        # Update context window
        svec = self.pool.get_vector(fragment.id) or build_semantic_vector(fragment)
        self.context.push(fragment, svec)

        # Register cluster usage with drift engine
        if self.drift:
            cluster = self.pool.get_cluster(fragment.id) or assign_cluster(fragment)
            self.drift.register_cluster_usage(cluster)

        print(f"[conductor] spawn: {fragment.id} as {role.value} "
              f"(dur={expected_dur:.0f}s, gain={target_gain:.2f}, fade_in={layer.fade_in_sec:.1f}s)")
        for cb in self.spawn_callbacks:
            try:
                cb(fragment.id, role.value, list(fragment.tags))
            except Exception:
                pass

    # ── Role Demand ─────────────────────────────────────────────────────

    def _compute_role_demand(self, target: int) -> dict[Role, int]:
        """
        Figure out how many layers of each role we need.
        Uses state role_weights as proportions.
        """
        role_weights = self.state.get_role_weights()
        total_weight = sum(role_weights.values())
        if total_weight == 0:
            return {}

        # Count current layers per role (exclude ended/fading-out)
        current_per_role = {r: 0 for r in Role}
        for layer in self._layers.values():
            if layer.state not in (LayerState.ENDED, LayerState.FADING_OUT):
                role_enum = Role(layer.role) if isinstance(layer.role, str) else layer.role
                current_per_role[role_enum] += 1

        # Calculate desired per role (proportional to weights)
        demand = {}
        for role in Role:
            if role == Role.EVENT:
                # Events are triggered separately, not filled like other roles
                continue
            proportion = role_weights.get(role, 0) / total_weight
            desired = max(0, round(target * proportion))
            needed = max(0, desired - current_per_role[role])
            if needed > 0:
                demand[role] = needed

        return demand

    # ── Fragment Selection ──────────────────────────────────────────────

    def _select_fragment(
        self,
        role: Role,
        exclude_ids: set[str],
    ) -> Optional[SoundFragment]:
        """Select a fragment using the semantic transition engine."""
        candidates = [
            (f, sv, rv)
            for f, sv, rv in self.pool.get_candidates()
            if f.id not in exclude_ids
        ]
        if not candidates:
            return None

        ctx = self.context.snapshot()
        source_frag = self.context.last_fragment
        source_vec = None
        if source_frag:
            source_vec = self.pool.get_vector(source_frag.id)

        result = self.transitions.select_next(
            candidates=candidates,
            context=ctx,
            current_state=self.state.current,
            source_fragment=source_frag,
            source_vector=source_vec,
            for_role=role,
        )

        if result:
            ttype_str = result.transition_type.value
            bridge_str = ','.join(result.bridge_tags[:3]) if result.bridge_tags else '-'
            print(f"[conductor] transition={ttype_str} bridge=[{bridge_str}] sim={result.similarity:.2f}")
            return result.fragment

        # Fallback: plain weight-based selection if transition engine returns nothing
        fallback = self.weights.compute_weights_for_role(
            self.pool.all_fragments(),
            role=role,
            exclude_ids=exclude_ids,
        )
        if not fallback:
            role_frags = [f for f in self.pool.get_by_role(role)
                         if f.id not in exclude_ids
                         and not self.memory.is_on_cooldown(f.id)]
            if not role_frags:
                return None
            return random.choice(role_frags)

        fragments, weights = zip(*fallback)
        # Apply warmup weight for newly merged assets
        weights = [w * self.pool.warmup_weight(f.id) for f, w in zip(fragments, weights)]
        return random.choices(fragments, weights=weights, k=1)[0]

    # ── Event Triggering ────────────────────────────────────────────────

    def _maybe_trigger_event(self, active_ids: set[str]):
        """Probabilistically trigger an event based on state + world."""
        event_prob = self.state.get_event_probability()
        # World tension amplifies event probability
        tension_mod = self.world.get_tension_modifier()
        adjusted_prob = min(0.5, event_prob * tension_mod)

        # Reduce probability if an event was very recent
        if self.memory.time_since_last_event() < 15.0:
            adjusted_prob *= 0.1  # cool down between events

        if random.random() > adjusted_prob:
            return

        # Select an event fragment
        fragment = self._select_fragment(Role.EVENT, active_ids)
        if fragment:
            self._spawn_layer(fragment)
            self.memory.register_event()
            print(f"[conductor] EVENT triggered: {fragment.id}")

    # ── Intervention Processing ───────────────────────────────────────────

    def _process_interventions(self):
        """Drain intervention queue and compute combined effect for this tick."""
        pending = self.interventions.drain()
        if not pending:
            # Decay effect back to neutral
            self._current_effect = InterventionEffect()
            return

        self._current_effect = compute_combined_effect(pending)

        for iv in pending:
            print(f"[conductor] intervention: {iv.kind.value} (strength={iv.strength:.1f})")

        # Handle fade_all: force all active layers into fade-out
        if self._current_effect.fade_all:
            for layer in self._layers.values():
                force_fade_out(layer)

        # Handle fade_out_bias: randomly fade some layers
        if self._current_effect.fade_out_bias > 0:
            living = [l for l in self._layers.values()
                      if l.state in (LayerState.FADING_IN, LayerState.PLAYING)]
            for layer in living:
                if random.random() < self._current_effect.fade_out_bias:
                    force_fade_out(layer)
                    print(f"[conductor] intervention fade-out: {layer.layer_id}")

    # ── Trace Output ──────────────────────────────────────────────────────

    def _emit_trace(self, merged: int, refreshed: int):
        """Lightweight trace output (spec §21)."""
        living = [l for l in self._layers.values() if l.state != LayerState.ENDED]
        role_counts = {}
        for layer in living:
            role_counts[layer.role] = role_counts.get(layer.role, 0) + 1
        roles_str = " ".join(f"{r}={c}" for r, c in role_counts.items())
        parts = [
            f"[tick {self._tick_index}]",
            f"state={self.state.current}",
            f"layers={len(living)} [{roles_str}]",
            f"pool={self.pool.fragment_count}",
        ]
        if merged:
            parts.append(f"merged={merged}")
        if refreshed:
            parts.append(f"refreshed={refreshed}")
        staging = self.pool.staging_size()
        if staging:
            parts.append(f"staging={staging}")
        print(" | ".join(parts))

    # ── Mutation (intervention-compatible) ──────────────────────────────

    def mutate_replace(self):
        """Replace a random non-ground layer with something else."""
        with self._lock:
            candidates = [
                (fid, layer) for fid, layer in self._layers.items()
                if layer.role != "ground"
                and layer.state in (LayerState.PLAYING, LayerState.FADING_IN)
            ]
            if not candidates:
                return
            fid, layer = random.choice(candidates)
            active_ids = set(self._layers.keys())

            role = Role(layer.role) if isinstance(layer.role, str) else layer.role
            replacement = self._select_fragment(role, active_ids)
            if replacement:
                force_fade_out(layer)
                self._spawn_layer(replacement)
                print(f"[conductor] mutate: replaced {fid} -> {replacement.id}")

    def mutate_silence(self):
        """Graceful silence: fade out everything."""
        with self._lock:
            for layer in self._layers.values():
                force_fade_out(layer)
            print("[conductor] RARE: graceful silence")


class _PlaybackAdapter:
    """
    Adapts SoundFragment to the interface expected by PlaybackEngine.play().
    The existing PlaybackEngine expects a Fragment with .id, .file_path, .loopable.
    """

    def __init__(self, fragment: SoundFragment):
        self.id = fragment.id
        self.file_path = fragment.file_path
        self.loopable = fragment.loopable
        self.category = fragment.role.value
        self.duration = fragment.duration
        self.energy_level = int(fragment.energy * 10)
        self.density_level = int(fragment.density * 10)
        self.cooldown = fragment.cooldown
        self.tags = fragment.tags

    def exists(self) -> bool:
        import os
        return os.path.isfile(self.file_path)
