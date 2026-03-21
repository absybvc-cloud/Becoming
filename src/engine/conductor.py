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
from .context import ContextWindow
from .transitions import TransitionEngine, TransitionType
from .vectors import SemanticVector, build_semantic_vector
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


@dataclass
class ActiveLayer:
    """A sound currently playing as part of the mix."""
    fragment: SoundFragment
    role: Role
    start_time: float
    expected_duration: float
    gain: float

    @property
    def age(self) -> float:
        return time.time() - self.start_time

    @property
    def should_end(self) -> bool:
        """True if the layer has exceeded its expected duration."""
        return self.age >= self.expected_duration


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
        library: SoundLibrary,
        playback: PlaybackEngine,
        state_machine: StateMachine,
        weight_engine: WeightEngine,
        memory: EngineMemory,
        world: WorldInterface,
        tick_interval: float = 2.0,
        temperature: float = 0.5,
        transition_log_path: str | None = None,
    ):
        self.library = library
        self.playback = playback
        self.state = state_machine
        self.weights = weight_engine
        self.memory = memory
        self.world = world
        self.tick_interval = tick_interval

        self._layers: dict[str, ActiveLayer] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Phase 2: semantic transition engine + context window
        self.context = ContextWindow(size=5)
        self.transitions = TransitionEngine(
            memory=memory,
            temperature=temperature,
            log_path=transition_log_path,
        )

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
    def active_layers(self) -> dict[str, ActiveLayer]:
        with self._lock:
            return dict(self._layers)

    # ── Main Loop ───────────────────────────────────────────────────────

    def _loop(self):
        # Small initial delay to let playback engine start
        time.sleep(1.0)
        while self._running:
            self._tick()
            time.sleep(self.tick_interval)

    def _tick(self):
        with self._lock:
            # Sync with playback engine: remove layers whose audio stopped
            self._sync_with_playback()

            # 1. End expired layers
            self._expire_layers()

            # 2. Record current density
            active_count = len(self._layers)
            self.memory.register_density(active_count)
            self.memory.register_combo(list(self._layers.keys()))

            # 3. Determine desired layer count from state + world
            max_layers = self.state.get_max_layers()
            density_mod = self.world.get_density_modifier()
            target = max(1, int(max_layers * density_mod))

            # 4. Determine role demands
            role_demand = self._compute_role_demand(target)

            # 5. Fill empty role slots
            active_ids = set(self._layers.keys())
            for role, needed in role_demand.items():
                for _ in range(needed):
                    fragment = self._select_fragment(role, active_ids)
                    if fragment:
                        self._spawn_layer(fragment)
                        active_ids.add(fragment.id)

            # 6. Check for event trigger (probabilistic)
            self._maybe_trigger_event(active_ids)

    # ── Layer Management ────────────────────────────────────────────────

    def _sync_with_playback(self):
        """Remove layers whose audio has finished in the playback engine."""
        playing = set(self.playback.active_ids())
        dead = [fid for fid in self._layers if fid not in playing]
        for fid in dead:
            del self._layers[fid]

    def _expire_layers(self):
        """Fade out layers that exceeded their expected duration."""
        to_remove = []
        for fid, layer in self._layers.items():
            if layer.should_end:
                self.playback.stop_fragment(fid, crossfade=True)
                to_remove.append(fid)
                print(f"[conductor] expired: {fid} ({layer.role.value}, {layer.age:.0f}s)")
        for fid in to_remove:
            del self._layers[fid]

    def _spawn_layer(self, fragment: SoundFragment):
        """Start a new layer for a fragment."""
        role = fragment.role
        dur_range = ROLE_DURATION_RANGE[role]
        gain_range = ROLE_GAIN[role]

        # For loopable sounds, use the full expected duration
        # For non-loopable, cap at actual audio duration
        expected_dur = random.uniform(*dur_range)
        if not fragment.loopable:
            expected_dur = min(expected_dur, fragment.duration)

        gain = random.uniform(*gain_range)

        # Create a playback-compatible Fragment adapter
        adapter = _PlaybackAdapter(fragment)
        if not self.playback.play(adapter, gain=gain):
            return

        layer = ActiveLayer(
            fragment=fragment,
            role=role,
            start_time=time.time(),
            expected_duration=expected_dur,
            gain=gain,
        )
        self._layers[fragment.id] = layer
        self.memory.register_play(fragment.id, fragment.tags, fragment.cooldown)

        # Update context window
        svec = self.library.get_vector(fragment.id) or build_semantic_vector(fragment)
        self.context.push(fragment, svec)

        print(f"[conductor] spawn: {fragment.id} as {role.value} (dur={expected_dur:.0f}s, gain={gain:.2f})")

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

        # Count current layers per role
        current_per_role = {r: 0 for r in Role}
        for layer in self._layers.values():
            current_per_role[layer.role] += 1

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
            for f, sv, rv in self.library.get_candidates()
            if f.id not in exclude_ids
        ]
        if not candidates:
            return None

        ctx = self.context.snapshot()
        source_frag = self.context.last_fragment
        source_vec = None
        if source_frag:
            source_vec = self.library.get_vector(source_frag.id)

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
            self.library.all_fragments(),
            role=role,
            exclude_ids=exclude_ids,
        )
        if not fallback:
            role_frags = [f for f in self.library.get_by_role(role)
                         if f.id not in exclude_ids
                         and not self.memory.is_on_cooldown(f.id)]
            if not role_frags:
                return None
            return random.choice(role_frags)

        fragments, weights = zip(*fallback)
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

    # ── Mutation (built-in) ─────────────────────────────────────────────

    def mutate_replace(self):
        """Replace a random non-ground layer with something else."""
        with self._lock:
            candidates = [
                (fid, layer) for fid, layer in self._layers.items()
                if layer.role != Role.GROUND  # don't yank the bed
            ]
            if not candidates:
                return
            fid, layer = random.choice(candidates)
            active_ids = set(self._layers.keys())

            replacement = self._select_fragment(layer.role, active_ids)
            if replacement:
                self.playback.stop_fragment(fid, crossfade=True)
                del self._layers[fid]
                self._spawn_layer(replacement)
                print(f"[conductor] mutate: replaced {fid} -> {replacement.id}")

    def mutate_silence(self):
        """Sudden silence: fade out everything briefly."""
        with self._lock:
            for fid in list(self._layers.keys()):
                self.playback.stop_fragment(fid, crossfade=True)
            self._layers.clear()
            print("[conductor] RARE: sudden silence")


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
