import time
import random
import threading
from typing import Optional

from .audio_library import AudioLibraryManager
from .playback_engine import PlaybackEngine
from .scheduler import Scheduler


MUTATION_INTERVAL_RANGE = (30, 90)   # seconds
MUTATION_PROBABILITY = 0.20
RARE_EVENT_PROBABILITY = 0.03


class MutationEngine:
    def __init__(
        self,
        library: AudioLibraryManager,
        playback: PlaybackEngine,
        scheduler: Scheduler,
    ):
        self.library = library
        self.playback = playback
        self.scheduler = scheduler
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[mutation] engine started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            interval = random.uniform(*MUTATION_INTERVAL_RANGE)
            time.sleep(interval)
            self._evaluate()

    def _evaluate(self):
        if random.random() < RARE_EVENT_PROBABILITY:
            self._rare_event()
            return

        if random.random() < MUTATION_PROBABILITY:
            self._mutate()

    def _mutate(self):
        mutations = [
            self._replace_fragment,
            self._add_layer,
            self._remove_layer,
            self._swap_fragment,
        ]
        random.choice(mutations)()

    def _replace_fragment(self):
        active = self.playback.active_ids()
        if not active:
            return
        target_id = random.choice(active)
        target = self.library.get(target_id)
        if not target:
            return
        candidates = [
            f for f in self.library.get_by_category(target.category)
            if f.id != target_id
            and f.id not in active
            and time.time() >= self.scheduler.cooldowns.get(f.id, 0)
        ]
        if not candidates:
            return
        replacement = random.choice(candidates)
        self.playback.crossfade(target_id, replacement)
        self.scheduler._register_play(replacement)
        print(f"[mutation] replaced {target_id} -> {replacement.id}")

    def _add_layer(self):
        active = self.playback.active_ids()
        candidates = [
            f for f in self.library.fragments.values()
            if f.id not in active
            and time.time() >= self.scheduler.cooldowns.get(f.id, 0)
        ]
        if not candidates:
            return
        fragment = random.choice(candidates)
        self.playback.play(fragment)
        self.scheduler._register_play(fragment)
        print(f"[mutation] added layer {fragment.id}")

    def _remove_layer(self):
        active = self.playback.active_ids()
        if len(active) <= 1:
            return
        target_id = random.choice(active)
        self.playback.stop_fragment(target_id, crossfade=True)
        print(f"[mutation] removed layer {target_id}")

    def _swap_fragment(self):
        active = self.playback.active_ids()
        if not active:
            return
        target_id = random.choice(active)
        all_candidates = [
            f for f in self.library.fragments.values()
            if f.id not in active
            and time.time() >= self.scheduler.cooldowns.get(f.id, 0)
        ]
        if not all_candidates:
            return
        replacement = random.choice(all_candidates)
        self.playback.crossfade(target_id, replacement)
        self.scheduler._register_play(replacement)
        print(f"[mutation] swapped {target_id} -> {replacement.id}")

    def _rare_event(self):
        events = [
            self._noise_burst,
            self._sudden_silence,
            self._inject_noise_event,
        ]
        random.choice(events)()

    def _noise_burst(self):
        noise_frags = self.library.get_by_category("noise")
        if not noise_frags:
            return
        frag = random.choice(noise_frags)
        self.playback.play(frag, gain=0.8)
        self.scheduler._register_play(frag)
        print(f"[mutation] RARE: noise burst -> {frag.id}")

    def _sudden_silence(self):
        active = self.playback.active_ids()
        for fid in active:
            self.playback.stop_fragment(fid, crossfade=True)
        print("[mutation] RARE: sudden silence")

    def _inject_noise_event(self):
        noise_frags = self.library.get_by_category("noise")
        field_frags = self.library.get_by_category("field")
        candidates = noise_frags + field_frags
        if not candidates:
            return
        frag = random.choice(candidates)
        self.playback.play(frag, gain=1.0)
        self.scheduler._register_play(frag)
        print(f"[mutation] RARE: injected event -> {frag.id}")
