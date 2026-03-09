import time
import random
import threading
from typing import Optional

from .audio_library import AudioLibraryManager, Fragment
from .playback_engine import PlaybackEngine
from .memory import MemorySystem
from .state_engine import StateEngine


class Scheduler:
    def __init__(
        self,
        library: AudioLibraryManager,
        playback: PlaybackEngine,
        memory: MemorySystem,
        state: StateEngine,
        tick_interval: float = 1.0,
    ):
        self.library = library
        self.playback = playback
        self.memory = memory
        self.state = state
        self.tick_interval = tick_interval

        # expose cooldowns for MutationEngine compatibility
        self.cooldowns: dict[str, float] = {}

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[scheduler] started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[scheduler] stopped")

    def _loop(self):
        while self._running:
            self._tick()
            time.sleep(self.tick_interval)

    def _tick(self):
        active = self.playback.active_ids()
        target = self.state.get_density()

        # register current combo for anti-repetition tracking
        self.memory.register_combo(active)

        if len(active) < target:
            slots = target - len(active)
            for _ in range(slots):
                fragment = self._pick_fragment(exclude=active)
                if fragment:
                    self.playback.play(fragment)
                    self._register_play(fragment)
                    active.append(fragment.id)

    def _pick_fragment(self, exclude: list[str]) -> Optional[Fragment]:
        weights = self.state.get_category_weights()
        now = time.time()

        # build weighted candidate pool
        pool: list[tuple[Fragment, int]] = []
        for frag in self.library.fragments.values():
            if frag.id in exclude:
                continue
            if now < self.cooldowns.get(frag.id, 0):
                continue
            if self.memory.was_recently_played(frag.id):
                continue
            w = weights.get(frag.category, 0)
            if w > 0:
                pool.append((frag, w))

        if not pool:
            # relax recent-play constraint
            pool = [
                (f, weights.get(f.category, 1))
                for f in self.library.fragments.values()
                if f.id not in exclude
                and now >= self.cooldowns.get(f.id, 0)
                and weights.get(f.category, 0) > 0
            ]

        if not pool:
            return None

        fragments, w = zip(*pool)
        return random.choices(fragments, weights=w, k=1)[0]

    def _register_play(self, fragment: Fragment):
        now = time.time()
        expiry = now + fragment.cooldown
        self.cooldowns[fragment.id] = expiry
        self.memory.register(fragment.id, fragment.cooldown)
