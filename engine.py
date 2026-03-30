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
from need_detector import NeedDetector, build_runtime_state, build_memory_state


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


def input_listener(state_machine, world, conductor, drift_engine, library, active_pool, intervention_queue, stop_event, playback, auto_harvest_enabled=None, interact_engine=None):
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

        elif cmd.lower() == "ah":
            if auto_harvest_enabled is not None:
                if auto_harvest_enabled.is_set():
                    auto_harvest_enabled.clear()
                    print("[engine] auto-harvest: OFF")
                else:
                    auto_harvest_enabled.set()
                    print("[engine] auto-harvest: ON")
            else:
                print("[engine] auto-harvest not available")

        elif cmd.lower() == "reload":
            n = active_pool.ingest_new_from_db()
            print(f"[engine] reloaded pool: {n} new assets")

        # DSP controls (silent — these may arrive at high frequency from camera)
        elif cmd == "lp" and len(parts) > 1:
            try:
                val = float(parts[1])
                playback.set_filter(max(0.0, min(1.0, val)), playback._highpass)
            except ValueError:
                pass
        elif cmd == "hp" and len(parts) > 1:
            try:
                val = float(parts[1])
                playback.set_filter(playback._lowpass, max(0.0, min(1.0, val)))
            except ValueError:
                pass
        elif cmd == "rv" and len(parts) > 1:
            try:
                playback.set_reverb(float(parts[1]))
            except ValueError:
                pass
        elif cmd == "dist" and len(parts) > 1:
            try:
                playback.set_distortion(float(parts[1]))
            except ValueError:
                pass
        elif cmd == "mg" and len(parts) > 1:
            try:
                playback.set_master_gain(float(parts[1]))
            except ValueError:
                pass
        elif cmd == "spread" and len(parts) > 1:
            try:
                playback.set_stereo_spread(float(parts[1]))
            except ValueError:
                pass
        elif cmd == "pan" and len(parts) > 1:
            try:
                playback.set_pan(float(parts[1]))
            except ValueError:
                pass
        elif cmd == "trem_rate" and len(parts) > 1:
            try:
                playback.set_tremolo(float(parts[1]), playback._tremolo_depth)
            except ValueError:
                pass
        elif cmd == "trem_depth" and len(parts) > 1:
            try:
                playback.set_tremolo(playback._tremolo_rate, float(parts[1]))
            except ValueError:
                pass
        elif cmd == "bitcrush" and len(parts) > 1:
            try:
                playback.set_bitcrush(float(parts[1]))
            except ValueError:
                pass
        elif cmd == "noise" and len(parts) > 1:
            try:
                playback.set_noise_floor(float(parts[1]))
            except ValueError:
                pass
        elif cmd == "fade_time" and len(parts) > 1:
            try:
                playback.set_fade_time(float(parts[1]))
            except ValueError:
                pass
        elif cmd == "rv_size" and len(parts) > 1:
            try:
                playback.set_reverb_size(float(parts[1]))
            except ValueError:
                pass
        elif cmd == "rv_fb" and len(parts) > 1:
            try:
                playback.set_reverb_feedback(float(parts[1]))
            except ValueError:
                pass

        elif cmd.lower() == "cam":
            if interact_engine is None:
                print("[engine] camera interaction not available (missing mediapipe/opencv)")
            elif interact_engine.running:
                interact_engine.stop()
                print("[engine] camera: OFF")
            else:
                interact_engine.start()
                print("[engine] camera: ON")

        else:
            print("[engine] commands: s <state> | t <0-1> | d <0-1> | T <0-1> | p <phase> | D (drift) | dur <0.1-3> | poem | rec | rec_stop | m | ! | rupture | silence | drift | collapse | stabilize | ah | reload | cam | lp/hp/rv/dist/mg/spread <0-1> | q")


# ── Interaction Apply Loop ─────────────────────────────────────────────────

def interaction_apply_loop(
    control_state,
    world,
    drift_engine,
    conductor,
    playback,
    stop_event: threading.Event,
    interval: float = 0.1,
):
    """
    Background thread that reads the shared ControlState from the camera
    perception module and applies it to the engine's behavior and audio layers.
    Runs at ~10 Hz — fast enough for smooth response, light on CPU.
    """
    while not stop_event.is_set():
        stop_event.wait(timeout=interval)
        if stop_event.is_set():
            break
        if not control_state.active:
            continue

        snap = control_state.snapshot()
        audio = snap["audio"]
        behavior = snap["behavior"]

        # Apply behavior control → world + drift + conductor
        world.update(
            tension=behavior["strain"],
            density=behavior["saturation"],
        )
        drift_engine.update_world(
            tension=behavior["strain"],
            density=behavior["saturation"],
        )
        if hasattr(conductor, 'transitions'):
            conductor.transitions.set_temperature(behavior["heat"])
        drift_engine.set_duration_scale(0.5 + behavior["time_scale"] * 2.0)

        # Apply audio control → PlaybackEngine DSP
        playback.set_filter(audio["lowpass"], audio["highpass"])
        playback.set_reverb(audio["reverb"])
        playback.set_distortion(audio["distortion"])
        playback.set_stereo_spread(audio["stereo_spread"])
        playback.set_master_gain(audio["master_gain"])


# ── Auto-Harvest Loop ──────────────────────────────────────────────────────

def auto_harvest_loop(
    conductor,
    memory,
    need_detector: NeedDetector,
    active_pool,
    stop_event: threading.Event,
    enabled: threading.Event,
    interval: float = 16.0,
):
    """
    Background thread that periodically evaluates engine needs
    and triggers harvest as a subprocess when a real deficiency is detected.
    Never blocks the runtime loop.
    """
    import subprocess

    _harvest_proc: subprocess.Popen | None = None

    while not stop_event.is_set():
        stop_event.wait(timeout=interval)
        if stop_event.is_set():
            break

        # Only evaluate if auto-harvest is enabled
        if not enabled.is_set():
            continue

        # Don't evaluate while a harvest is already running
        if _harvest_proc is not None and _harvest_proc.poll() is None:
            continue

        # Build state snapshots (thread-safe reads)
        runtime_state = build_runtime_state(conductor)
        memory_state = build_memory_state(memory)

        # Evaluate
        signal = need_detector.evaluate(
            runtime_state,
            memory_state,
        )

        if not signal.trigger:
            continue

        # Log the need
        print(f"[need] type={signal.need_type} intensity={signal.intensity:.2f} — {signal.reason}")

        # Build harvest command
        cmd = [
            sys.executable, "unified_harvest.py",
            "--mode", signal.mode,
            "--limit", str(max(10, int(signal.intensity * 30))),
        ]
        if signal.target_clusters:
            # Pass target clusters as focus hint
            cmd.extend(["--focus"])

        print(f"[harvest_trigger] mode={signal.mode} clusters={signal.target_clusters}")

        # Spawn harvest asynchronously — never block
        try:
            _harvest_proc = subprocess.Popen(
                cmd,
                cwd=os.path.dirname(os.path.abspath(__file__)),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            need_detector.record_harvest()

            # Read output in background so it doesn't block
            def _drain(proc):
                assert proc.stdout is not None
                for line in proc.stdout:
                    print(f"[auto-harvest] {line.rstrip()}")
                proc.wait()
                print(f"[auto-harvest] done (exit={proc.returncode})")
                # Load newly downloaded assets into the active pool
                active_pool.ingest_new_from_db()

            threading.Thread(target=_drain, args=(_harvest_proc,), daemon=True).start()
        except Exception as e:
            print(f"[auto-harvest] ERROR: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Becoming — generative sound ecology engine")
    parser.add_argument("--state", type=str, default="submerged",
                        choices=STATE_NAMES, help="Initial state")
    parser.add_argument("--tension", type=float, default=0.3, help="Initial tension (0-1)")
    parser.add_argument("--density", type=float, default=0.5, help="Initial density (0-1)")
    parser.add_argument("--temperature", type=float, default=0.5, help="Semantic temperature (0-1)")
    parser.add_argument("--auto-harvest", action="store_true", default=True,
                        help="Enable autonomous need-based harvesting (default: on)")
    parser.add_argument("--no-auto-harvest", dest="auto_harvest", action="store_false",
                        help="Disable autonomous harvesting")
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
        if interact_engine is not None:
            interact_engine.stop()
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

    # Set up camera interaction (optional — graceful if deps missing)
    interact_engine = None
    control_state = None
    try:
        from interact import InteractionEngine, ControlState
        control_state = ControlState()
        interact_engine = InteractionEngine(control_state)
        print("[engine] camera interaction: available (type 'cam' to toggle)")
    except Exception as e:
        print(f"[engine] camera interaction: unavailable ({e})")

    # Set up auto-harvest (must exist before input_listener references it)
    need_detector = NeedDetector()
    auto_harvest_enabled = threading.Event()
    if args.auto_harvest:
        auto_harvest_enabled.set()
        print("[engine] auto-harvest: ON")
    else:
        print("[engine] auto-harvest: OFF")

    # Start input listener in background
    input_thread = threading.Thread(
        target=input_listener,
        args=(state_machine, world, conductor, drift_engine, library, active_pool, intervention_queue, stop_event, playback, auto_harvest_enabled, interact_engine),
        daemon=True,
    )
    input_thread.start()

    # Start interaction apply loop (bridges camera control → engine)
    if interact_engine is not None:
        interact_thread = threading.Thread(
            target=interaction_apply_loop,
            args=(control_state, world, drift_engine, conductor, playback, stop_event),
            daemon=True,
        )
        interact_thread.start()

    # Start auto-harvest detector thread
    harvest_thread = threading.Thread(
        target=auto_harvest_loop,
        args=(conductor, memory, need_detector, active_pool, stop_event, auto_harvest_enabled),
        daemon=True,
    )
    harvest_thread.start()

    print()
    print("[engine] running. Commands: s <state> | t <0-1> | d <0-1> | T <0-1> | p <phase> | poem | m | ! | rupture | silence | drift | collapse | stabilize | ah | cam | q")
    print()

    # Status loop
    while not stop_event.is_set():
        time.sleep(8)
        if not stop_event.is_set():
            status_line(state_machine, conductor, memory, world, playback, drift_engine, active_pool)


if __name__ == "__main__":
    main()
