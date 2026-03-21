#!/usr/bin/env python3
"""
Becoming Engine — Main Runner

A state-driven, memory-aware, probability-weighted,
externally modulated sound ecology engine.

Usage:
    python engine.py                          # start with defaults
    python engine.py --state submerged        # start in a specific state
    python engine.py --tension 0.7            # start with high tension
    python engine.py --density 0.3            # start sparse

Runtime controls (stdin):
    s <state>    - force state (submerged/tense/dissolved/rupture/drifting)
    t <0-1>      - set tension
    d <0-1>      - set density
    q            - quit
"""

import os
import sys
import time
import signal
import threading

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.playback_engine import PlaybackEngine
from src.engine.library import SoundLibrary
from src.engine.states import StateMachine, STATE_NAMES
from src.engine.memory import EngineMemory
from src.engine.world import WorldInterface
from src.engine.weights import WeightEngine
from src.engine.conductor import Conductor
from src.engine.roles import Role


def on_state_change(old: str, new: str):
    print(f"\n[engine] ── state transition: {old} -> {new} ──")


def build_engine(
    initial_state: str = "submerged",
    tension: float = 0.3,
    density: float = 0.5,
) -> tuple:
    """Build and wire all engine components."""

    # 1. Load sound library from database
    library = SoundLibrary()
    library.load()

    if not library.fragments:
        print("[engine] ERROR: no approved sounds in library. Run the review tool first.")
        sys.exit(1)

    # 2. Create subsystems
    memory = EngineMemory()
    world = WorldInterface(auto_time=True)
    world.update(tension=tension, density=density)

    state_machine = StateMachine(
        initial_state=initial_state,
        on_state_change=on_state_change,
    )

    weight_engine = WeightEngine(
        state_machine=state_machine,
        memory=memory,
        world=world,
    )

    playback = PlaybackEngine()

    conductor = Conductor(
        library=library,
        playback=playback,
        state_machine=state_machine,
        weight_engine=weight_engine,
        memory=memory,
        world=world,
    )

    return library, memory, world, state_machine, weight_engine, playback, conductor


def status_line(state_machine, conductor, memory, world, playback):
    """Print a status summary."""
    layers = conductor.active_layers
    role_counts = {r.value: 0 for r in Role}
    for layer in layers.values():
        role_counts[layer.role.value] += 1

    roles_str = " ".join(f"{r}={c}" for r, c in role_counts.items() if c > 0)
    mem = memory.summary()
    w = world.get()
    ttl = state_machine.time_until_transition()

    print(
        f"[status] state={state_machine.current} "
        f"| layers={len(layers)}/{state_machine.get_max_layers()} [{roles_str}] "
        f"| trend={mem['density_trend']:+.2f} "
        f"| plays={mem['total_plays']} "
        f"| event={mem['time_since_event']:.0f}s ago "
        f"| tension={w.tension:.1f} density={w.density:.1f} "
        f"| next_transition={ttl:.0f}s"
    )

    # Print active fragment details
    for fid, layer in layers.items():
        print(f"  └ {layer.role.value:>7}: {fid} ({layer.age:.0f}s/{layer.expected_duration:.0f}s)")


def input_listener(state_machine, world, conductor, stop_event):
    """Listen for runtime control commands on stdin."""
    while not stop_event.is_set():
        try:
            line = input()
        except EOFError:
            break
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        if cmd == "q":
            print("[engine] quit requested")
            stop_event.set()
            os.kill(os.getpid(), signal.SIGINT)
        elif cmd == "s" and len(parts) > 1:
            try:
                state_machine.force_state(parts[1])
            except ValueError as e:
                print(f"[engine] {e}")
        elif cmd == "t" and len(parts) > 1:
            try:
                val = float(parts[1])
                world.update(tension=max(0.0, min(1.0, val)))
                print(f"[engine] tension set to {val:.2f}")
            except ValueError:
                print("[engine] usage: t <0-1>")
        elif cmd == "d" and len(parts) > 1:
            try:
                val = float(parts[1])
                world.update(density=max(0.0, min(1.0, val)))
                print(f"[engine] density set to {val:.2f}")
            except ValueError:
                print("[engine] usage: d <0-1>")
        elif cmd == "m":
            conductor.mutate_replace()
        elif cmd == "!":
            conductor.mutate_silence()
        else:
            print("[engine] commands: s <state> | t <0-1> | d <0-1> | m (mutate) | ! (silence) | q (quit)")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Becoming — generative sound ecology engine")
    parser.add_argument("--state", type=str, default="submerged",
                        choices=STATE_NAMES, help="Initial state")
    parser.add_argument("--tension", type=float, default=0.3, help="Initial tension (0-1)")
    parser.add_argument("--density", type=float, default=0.5, help="Initial density (0-1)")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════╗")
    print("║          B E C O M I N G                 ║")
    print("║   sound ecology engine                   ║")
    print("╚══════════════════════════════════════════╝")
    print()

    library, memory, world, state_machine, weight_engine, playback, conductor = build_engine(
        initial_state=args.state,
        tension=args.tension,
        density=args.density,
    )

    stop_event = threading.Event()

    def shutdown(sig, frame):
        print("\n[engine] shutting down...")
        stop_event.set()
        conductor.stop()
        state_machine.stop()
        playback.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start all subsystems
    playback.start()
    state_machine.start()
    conductor.start()

    # Start input listener in background
    input_thread = threading.Thread(
        target=input_listener,
        args=(state_machine, world, conductor, stop_event),
        daemon=True,
    )
    input_thread.start()

    print()
    print("[engine] running. Commands: s <state> | t <0-1> | d <0-1> | m | ! | q")
    print()

    # Status loop
    while not stop_event.is_set():
        time.sleep(8)
        if not stop_event.is_set():
            status_line(state_machine, conductor, memory, world, playback)


if __name__ == "__main__":
    main()
