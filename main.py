import time
import signal
import sys
import os

from src.audio_library import AudioLibraryManager
from src.playback_engine import PlaybackEngine
from src.memory import MemorySystem
from src.state_engine import StateEngine
from src.scheduler import Scheduler
from src.mutation_engine import MutationEngine

MANIFEST_PATH = os.path.join("assets", "library", "manifest.json")


def on_state_change(old: str, new: str):
    print(f"[main] state changed: {old} -> {new}")


def build_system():
    library = AudioLibraryManager(MANIFEST_PATH)
    library.load()

    summary = library.summary()
    total = sum(summary.values())
    if total == 0:
        print("[main] WARNING: no fragments loaded. Add audio files and update manifest.json")

    memory = MemorySystem()
    state = StateEngine(on_state_change=on_state_change)
    playback = PlaybackEngine()
    scheduler = Scheduler(library=library, playback=playback, memory=memory, state=state)
    mutation = MutationEngine(library=library, playback=playback, scheduler=scheduler)

    return library, memory, state, playback, scheduler, mutation


def main():
    print("=== Becoming ===")
    print("Starting generative music engine...\n")

    library, memory, state, playback, scheduler, mutation = build_system()

    # graceful shutdown
    def shutdown(sig, frame):
        print("\n[main] shutting down...")
        mutation.stop()
        scheduler.stop()
        state.stop()
        playback.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    playback.start()
    state.start()
    scheduler.start()
    mutation.start()

    print("\n[main] running. Press Ctrl+C to stop.\n")

    # status loop
    while True:
        time.sleep(10)
        active = playback.active_ids()
        mem = memory.summary()
        print(
            f"[status] state={state.state} | "
            f"density={len(active)}/{state.get_density()} | "
            f"active={active} | "
            f"recent_played={len(mem['recent'])}"
        )


if __name__ == "__main__":
    main()
