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

import json
import os
import sys
import time
import signal
import threading
from datetime import datetime
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.playback_engine import PlaybackEngine
from src.engine.library import SoundLibrary
from src.engine.active_pool import ActivePool
from src.engine.states import StateMachine, STATE_NAMES
from src.engine.memory import EngineMemory
from src.engine.world import WorldInterface
from src.engine.weights import WeightEngine
from src.engine.conductor import Conductor
from src.engine.drift import DriftEngine
from src.engine.roles import Role
from src.engine.interventions import InterventionQueue, InterventionType


def on_state_change(old: str, new: str):
    print(f"\n[engine] ── state transition: {old} -> {new} ──")


def build_engine(
    initial_state: str = "submerged",
    tension: float = 0.3,
    density: float = 0.5,
    temperature: float = 0.5,
) -> tuple:
    """Build and wire all engine components."""

    # 1. Load sound library from database
    library = SoundLibrary()
    library.load()

    if not library.fragments:
        print("[engine] ERROR: no approved sounds in library. Run the review tool first.")
        sys.exit(1)

    # 1b. Populate Active Pool from library (two-buffer hot-ingest system)
    active_pool = ActivePool()
    active_pool.load_from_library(library)

    # 2. Create subsystems
    memory = EngineMemory()
    world = WorldInterface(auto_time=True)
    world.update(tension=tension, density=density)

    drift_engine = DriftEngine(tick_interval=10.0)

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

    intervention_queue = InterventionQueue()

    transition_log = os.path.join("library", "transitions.jsonl")

    conductor = Conductor(
        active_pool=active_pool,
        playback=playback,
        state_machine=state_machine,
        weight_engine=weight_engine,
        memory=memory,
        world=world,
        drift_engine=drift_engine,
        intervention_queue=intervention_queue,
        temperature=temperature,
        transition_log_path=transition_log,
    )

    return library, active_pool, memory, world, state_machine, weight_engine, playback, conductor, drift_engine, intervention_queue


def status_line(state_machine, conductor, memory, world, playback, drift_engine, active_pool):
    """Print a status summary."""
    layers = conductor.active_layers
    fragments = conductor.active_fragments
    role_counts = {}
    for layer in layers.values():
        role_counts[layer.role] = role_counts.get(layer.role, 0) + 1

    roles_str = " ".join(f"{r}={c}" for r, c in role_counts.items() if c > 0)
    mem = memory.summary()
    w = world.get()
    ttl = state_machine.time_until_transition()

    # Context info
    ctx = conductor.context.snapshot()
    cluster_run = conductor.context.cluster_run_length()
    last_cluster = conductor.context.last_cluster or "-"
    temp = conductor.transitions.temperature

    print(
        f"[status] state={state_machine.current} "
        f"| layers={len(layers)}/{state_machine.get_max_layers()} [{roles_str}] "
        f"| cluster={last_cluster}(run={cluster_run}) "
        f"| temp={temp:.1f} "
        f"| trend={mem['density_trend']:+.2f} "
        f"| plays={mem['total_plays']} "
        f"| event={mem['time_since_event']:.0f}s ago "
        f"| tension={w.tension:.1f} density={w.density:.1f} "
        f"| next_transition={ttl:.0f}s"
    )
    print(f"[drift] {drift_engine.status_line()}")
    print(f"[pool] total={active_pool.fragment_count} staging={active_pool.staging_size()} dirty={active_pool.dirty_count()}")

    # Print active fragment details
    for lid, layer in layers.items():
        remaining = layer.remaining
        print(f"  └ {layer.role:>7}: {lid} state={layer.state.value} gain={layer.current_gain:.2f} rem={remaining:.0f}s")


def input_listener(state_machine, world, conductor, drift_engine, library, active_pool, intervention_queue, stop_event, playback):
    """Listen for runtime control commands on stdin."""

    # Recording state
    rec_active = False
    rec_start_time = None
    rec_fragments: list[dict] = []  # [{time, id, role, tags}, ...]

    def _on_spawn(frag_id, role, tags):
        nonlocal rec_active, rec_fragments
        if rec_active:
            rec_fragments.append({
                "time": time.time() - rec_start_time,
                "id": frag_id,
                "role": role,
                "tags": tags,
            })

    conductor.spawn_callbacks.append(_on_spawn)

    while not stop_event.is_set():
        try:
            line = input()
        except EOFError:
            break
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        cmd = parts[0]

        if cmd.lower() == "q":
            print("[engine] quit requested")
            stop_event.set()
            os.kill(os.getpid(), signal.SIGINT)
        elif cmd.lower() == "s" and len(parts) > 1:
            try:
                state_machine.force_state(parts[1])
            except ValueError as e:
                print(f"[engine] {e}")
        elif cmd == "t" and len(parts) > 1:
            try:
                val = float(parts[1])
                world.update(tension=max(0.0, min(1.0, val)))
                drift_engine.update_world(tension=val)
                print(f"[engine] tension set to {val:.2f}")
            except ValueError:
                print("[engine] usage: t <0-1>")
        elif cmd == "T" and len(parts) > 1:
            try:
                val = float(parts[1])
                conductor.transitions.set_temperature(max(0.0, min(1.0, val)))
                print(f"[engine] temperature set to {val:.2f}")
            except ValueError:
                print("[engine] usage: T <0-1>")
        elif cmd.lower() == "d" and len(parts) > 1:
            try:
                val = float(parts[1])
                world.update(density=max(0.0, min(1.0, val)))
                drift_engine.update_world(density=val)
                print(f"[engine] density set to {val:.2f}")
            except ValueError:
                print("[engine] usage: d <0-1>")
        elif cmd.lower() == "p" and len(parts) > 1:
            try:
                drift_engine.force_phase(parts[1])
                print(f"[engine] drift phase forced to {parts[1]}")
            except ValueError as e:
                print(f"[engine] {e}")
        elif cmd.lower() == "m":
            intervention_queue.enqueue(InterventionType.MUTATE_REPLACE)
            conductor.mutate_replace()
        elif cmd == "!":
            intervention_queue.enqueue(InterventionType.SILENCE)
        elif cmd.lower() == "rupture":
            intervention_queue.enqueue(InterventionType.INTRODUCE_RUPTURE)
            print("[engine] intervention: introduce_rupture")
        elif cmd.lower() == "silence":
            intervention_queue.enqueue(InterventionType.INVITE_SILENCE)
            print("[engine] intervention: invite_silence")
        elif cmd.lower() == "drift":
            intervention_queue.enqueue(InterventionType.ENTER_DRIFT)
            print("[engine] intervention: enter_drift")
        elif cmd.lower() == "collapse":
            intervention_queue.enqueue(InterventionType.FORCE_COLLAPSE)
            print("[engine] intervention: force_collapse")
        elif cmd.lower() == "stabilize":
            intervention_queue.enqueue(InterventionType.STABILIZE)
            print("[engine] intervention: stabilize")
        elif cmd == "D":
            snap = drift_engine.snapshot()
            print(f"[drift-snapshot] {json.dumps(snap)}")
        elif cmd.lower() == "dur" and len(parts) > 1:
            try:
                val = float(parts[1])
                drift_engine.set_duration_scale(val)
                print(f"[engine] drift duration scale set to {val:.2f}")
            except ValueError:
                print("[engine] usage: dur <0.1-3.0>")
        elif cmd.lower() == "poem":
            from poem_maker import FILTER_TAGS
            fragments = conductor.active_fragments
            words = set()
            for fid, frag in fragments.items():
                words.update(t.lower() for t in frag.tags)
                words.add(frag.role.value)
                cluster = active_pool.get_cluster(fid)
                if cluster:
                    words.add(cluster.replace("_", " "))
            words -= FILTER_TAGS
            w = world.get()
            blob = {
                "words": sorted(words),
                "state": state_machine.current,
                "phase": drift_engine.snapshot().get("phase", "drift"),
                "tension": round(w.tension, 2),
                "density": round(w.density, 2),
            }
            print(f"[poem-words] {json.dumps(blob)}")
        elif cmd.lower() == "rec":
            if rec_active:
                print("[recording] already recording")
            else:
                rec_fragments.clear()
                rec_start_time = time.time()
                playback.start_recording()
                rec_active = True
                print("[recording] started")

        elif cmd.lower() == "rec_stop":
            if not rec_active:
                print("[recording] not recording")
            else:
                rec_active = False
                audio = playback.stop_recording()
                stamp = datetime.fromtimestamp(rec_start_time).strftime("%Y%m%d_%H%M%S")
                folder = Path("recordings") / f"recording_{stamp}"
                folder.mkdir(parents=True, exist_ok=True)
                if audio is not None and len(audio) > 0:
                    PlaybackEngine.save_recording(audio, folder / f"recording_{stamp}.wav")
                    print(f"[recording] saved {folder / f'recording_{stamp}.wav'}")
                else:
                    print("[recording] no audio captured")
                # write fragment log
                with open(folder / f"recording_{stamp}.txt", "w") as f:
                    f.write(f"Recording started: {datetime.fromtimestamp(rec_start_time).isoformat()}\n")
                    f.write(f"Duration: {time.time() - rec_start_time:.1f}s\n")
                    f.write(f"Fragments spawned: {len(rec_fragments)}\n\n")
                    for entry in rec_fragments:
                        mins = int(entry['time'] // 60)
                        secs = entry['time'] % 60
                        f.write(f"  [{mins:02d}:{secs:05.2f}] {entry['id']}  role={entry['role']}  tags={', '.join(entry['tags'])}\n")
                print(f"[recording] saved {folder / f'recording_{stamp}.txt'} ({len(rec_fragments)} fragments)")
                rec_fragments.clear()
                rec_start_time = None

        else:
            print("[engine] commands: s <state> | t <0-1> | d <0-1> | T <0-1> | p <phase> | D (drift) | dur <0.1-3> | poem | rec | rec_stop | m | ! | rupture | silence | drift | collapse | stabilize | q")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Becoming — generative sound ecology engine")
    parser.add_argument("--state", type=str, default="submerged",
                        choices=STATE_NAMES, help="Initial state")
    parser.add_argument("--tension", type=float, default=0.3, help="Initial tension (0-1)")
    parser.add_argument("--density", type=float, default=0.5, help="Initial density (0-1)")
    parser.add_argument("--temperature", type=float, default=0.5, help="Semantic temperature (0-1)")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════╗")
    print("║          B E C O M I N G                 ║")
    print("║   sound ecology engine                   ║")
    print("╚══════════════════════════════════════════╝")
    print()

    library, active_pool, memory, world, state_machine, weight_engine, playback, conductor, drift_engine, intervention_queue = build_engine(
        initial_state=args.state,
        tension=args.tension,
        density=args.density,
        temperature=args.temperature,
    )

    stop_event = threading.Event()

    def shutdown(sig, frame):
        print("\n[engine] shutting down...")
        stop_event.set()
        conductor.stop()
        drift_engine.stop()
        state_machine.stop()
        playback.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start all subsystems
    playback.start()
    state_machine.start()
    drift_engine.start()
    conductor.start()

    # Start input listener in background
    input_thread = threading.Thread(
        target=input_listener,
        args=(state_machine, world, conductor, drift_engine, library, active_pool, intervention_queue, stop_event, playback),
        daemon=True,
    )
    input_thread.start()

    print()
    print("[engine] running. Commands: s <state> | t <0-1> | d <0-1> | T <0-1> | p <phase> | poem | m | ! | rupture | silence | drift | collapse | stabilize | q")
    print()

    # Status loop
    while not stop_event.is_set():
        time.sleep(8)
        if not stop_event.is_set():
            status_line(state_machine, conductor, memory, world, playback, drift_engine, active_pool)


if __name__ == "__main__":
    main()
