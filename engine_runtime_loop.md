# Engine Runtime Loop – Continuous Generative Execution

**Becoming Engine – Runtime, Scheduler, Layers, and Live Evolution**

---

## 1. Purpose

Build the continuous runtime core of Becoming.

This module is responsible for:

- Keeping the engine alive over time
- Selecting sounds from the active pool
- Maintaining active layers
- Reacting to interventions
- Integrating hot-ingested assets safely
- Evolving state without hard resets

This is the runtime organism of the system.

---

## 2. Runtime Philosophy

The engine must not behave like a playlist.

It must behave like:

- An environment
- A pressure system
- A slow-moving field with intermittent rupture
- A memory-bearing process

The engine does not "play tracks." It maintains a **living sound condition**.

---

## 3. Runtime Responsibilities

The runtime loop must handle:

- Current global state
- Active layers
- Scheduling / spawning
- Fade in / fade out
- Memory and repetition control
- Safe hot merge of new assets
- Intervention handling
- World-state influence
- Logging / trace output

---

## 4. Main Runtime Components

```text
Control Surface
        ↓
Runtime Engine
    ├── State Machine
    ├── Scheduler
    ├── Layer Manager
    ├── Memory System
    ├── Active Pool
    ├── Staging Merge
    └── Audio Output
```

---

## 5. Core Runtime Objects

### 5.1 Engine Context

```python
engine_context = {
    "running": True,
    "current_state": "submerged",
    "state_entered_at": 0.0,
    "tick_index": 0,
    "last_spawn_at": 0.0,
    "last_event_at": 0.0,
    "intervention_queue": [],
    "world_state": {},
    "trace_enabled": True,
}
```

### 5.2 Active Layers

```python
active_layers = [
    {
        "layer_id": "uuid",
        "asset_id": 441,
        "role": "ground",
        "state": "playing",          # pending / fading_in / playing / fading_out / ended
        "started_at": 0.0,
        "expected_end_at": 0.0,
        "fade_in_sec": 4.0,
        "fade_out_sec": 6.0,
        "target_gain": 0.55,
        "current_gain": 0.12,
        "pan": 0.0,
        "metadata_version": 1,
    }
]
```

### 5.3 Memory State

```python
memory_state = {
    "recent_asset_ids": [],
    "recent_roles": [],
    "recent_tags": [],
    "recent_clusters": [],
    "cluster_usage_window": {},
    "last_focus_cluster": None,
    "dominance_duration": {},
    "last_merge_at": 0.0,
}
```

---

## 6. Runtime Tick Model

The engine runs on a regular tick.

Recommended:

- Tick interval: `0.5s` to `2.0s`
- Scheduler decisions every 1–4 ticks
- Audio playback itself remains continuous outside tick granularity

### 6.1 Main Loop

```python
while engine_context["running"]:
    now = current_time()

    update_world_state(now)
    process_interventions(now)
    update_state_machine(now)
    update_layers(now)
    scheduler_tick(now)

    if safe_point(now):
        merge_staging_queue()

    if safe_point(now):
        refresh_dirty_metadata()

    cleanup_finished_layers(now)
    emit_trace(now)

    sleep(tick_interval)
```

---

## 7. State Machine

The runtime always has one current macro-state.

States: `submerged`, `tense`, `dissolved`, `rupture`, `drifting`

### 7.1 State Properties

Each state should define:

```python
state_def = {
    "role_weights": {
        "ground": 1.0,
        "texture": 0.7,
        "event": 0.1,
        "pulse": 0.2,
    },
    "max_layers": 4,
    "event_probability": 0.08,
    "spawn_interval_range": [4.0, 12.0],
    "duration_range": [120.0, 480.0],
    "transition_tendency": {
        "drifting": 0.4,
        "dissolved": 0.2,
        "rupture": 0.05,
    },
}
```

### 7.2 State Transition Rules

A state can change when:

- Duration range has been satisfied
- Intervention requests it
- World state strongly biases transition
- Collapse / drift conditions are met

State transitions must be smooth:

- No hard stop of active layers
- Only future scheduling changes immediately
- Optional global transition fade modifier

---

## 8. Layer Roles and Behavior

The scheduler manages four major roles:

### 8.1 Ground

- Long duration
- Low change rate
- Few simultaneous layers
- Provides continuity

### 8.2 Texture

- Medium duration
- Medium activity
- Surface movement

### 8.3 Event

- Short duration
- Rare
- Disruptive
- High contrast

### 8.4 Pulse

- Rhythmic or semi-rhythmic
- Moderate duration
- Internal life signal

---

## 9. Scheduler Design

The scheduler decides whether to spawn a new sound. It should **not** spawn blindly every tick.

### 9.1 Scheduler Questions

At each scheduler cycle, ask:

1. Is the system under-filled?
2. Which roles are currently missing?
3. Is an event due?
4. Is the state asking for change?
5. Is repetition risk too high?
6. Have new assets recently entered?
7. Is an intervention active?

### 9.2 Basic Spawn Logic

```python
if len(active_layers) < state.max_layers:
    choose_role_to_fill()
    choose_asset_for_role()
    spawn_layer()
```

---

## 10. Role Selection

Role selection should be weighted by:

- State role weights
- Current active role distribution
- World state bias
- Intervention bias
- Fatigue / repetition suppression

Example formula:

```
role_score =
    state_role_weight
  - current_role_saturation
  + missing_role_bonus
  + intervention_role_bias
```

---

## 11. Asset Selection

The scheduler must choose assets from `active_pool` only. Selection is **weighted**, not random.

### 11.1 Asset Weight Formula

```
asset_weight =
    base_weight
  × role_match
  × state_tag_bias
  × novelty_boost
  × recency_penalty
  × fatigue_penalty
  × world_modulation
  × intervention_boost
```

### 11.2 Suppression Rules

Strongly suppress:

- Assets used in recent history
- Same asset back-to-back
- Same cluster too many times in short window
- Over-dominant tags

### 11.3 New Asset Warmup

Newly merged assets should not dominate immediately.

Suggested rule:

- First N scheduler cycles: apply `0.3–0.7` weight multiplier
- Gradually normalize after warmup

---

## 12. Layer Spawning

When a layer is spawned:

```python
new_layer = {
    "layer_id": uuid(),
    "asset_id": selected_asset["asset_id"],
    "role": selected_asset["role"],
    "state": "fading_in",
    "started_at": now,
    "expected_end_at": now + selected_duration,
    "fade_in_sec": choose_fade_in(role),
    "fade_out_sec": choose_fade_out(role),
    "target_gain": choose_gain(role, state, world_state),
    "current_gain": 0.0,
    "pan": choose_pan(role),
    "metadata_version": selected_asset["metadata_version"],
}
```

Then hand off to audio output backend.

---

## 13. Layer Update Logic

Each tick, active layers must be updated.

### 13.1 Fade In

If `state == fading_in`:

- Ramp `current_gain` toward `target_gain`
- When complete → `playing`

### 13.2 Playing

If `now < expected_end_at - fade_out_sec`:

- Maintain `target_gain`
- Optionally apply slow modulation

### 13.3 Fade Out

If `now >= expected_end_at - fade_out_sec`:

- State → `fading_out`
- Ramp `current_gain` downward

### 13.4 End

If `gain <= threshold` or `now >= expected_end_at`:

- Mark `ended`
- Release audio resources

---

## 14. Audio Output Boundary

Runtime loop should not depend tightly on a single audio backend.

Define an abstraction:

```python
audio_backend.play(layer)
audio_backend.update_gain(layer_id, gain)
audio_backend.stop(layer_id)
```

This allows later replacement with:

- Local audio output
- Stream buffer output
- File rendering backend
- Remote broadcast backend

---

## 15. Interventions

The GUI already exposes interventions. These should enter runtime through an intervention queue.

Example interventions: `introduce_rupture`, `invite_silence`, `enter_drift`, `force_collapse`, `stabilize`, `awaken`, `silence`

### 15.1 Intervention Queue

```python
intervention_queue = [
    {
        "type": "introduce_rupture",
        "issued_at": 123.4,
        "strength": 0.8,
    }
]
```

### 15.2 Intervention Effects

| Intervention | Effects |
|---|---|
| `introduce_rupture` | Raise event probability; temporarily reduce ground continuity; bias toward rupture/event clusters |
| `invite_silence` | Reduce max layers; slow spawn rate; increase fade-out preference; suppress pulse and event |
| `enter_drift` | Increase novelty bias; increase edge promotion; bias toward underused clusters |
| `force_collapse` | Aggressively fade dominant layers; suppress dominant clusters; shorten active density |
| `stabilize` | Reduce event rate; bias toward ground and field; lower transition volatility |
| `awaken` | Engine starts / resumes scheduling |
| `silence` | No new spawns; fade all layers out gracefully |

---

## 16. World State Integration

Runtime should read `world_state` every tick.

Minimum example:

```python
world_state = {
    "time_of_day": "night",
    "tension": 0.42,
    "density": 0.31,
    "noise_level": 0.12,
    "human_bias": {
        "texture_evolving": 0.2,
    },
}
```

### 16.1 Recommended Effects

| Input | Effect |
|---|---|
| `tension` | Event and pulse probability |
| `density` | Max layers and overlap tolerance |
| `noise_level` | Texture/noise weight |
| `time_of_day` | State transition bias |
| `human_bias` | Cluster or tag weight shift |

---

## 17. Hot Ingest Integration

Use the simplified live integration model:

- Runtime reads from `active_pool`
- Background pipeline writes new valid assets to `staging_queue`
- Runtime merges only at safe points

### 17.1 Merge Rules

When merging:

- Do **not** interrupt currently playing layers
- New assets only affect future scheduling
- Rebuild lightweight lookup indices
- Mark merge time in `memory_state`

### 17.2 Dirty Metadata Refresh

If tags/roles are changed:

- Do **not** mutate active layers directly
- Refresh `active_pool` metadata at safe point
- Future scheduling uses updated metadata

---

## 18. Safe Point Rules

A safe point is when:

- Scheduler is **not** mid-selection
- No structural mutation of `active_layers` is happening
- No forced intervention transition is halfway applied

Recommended merge timing:

- End of scheduler cycle
- Before next spawn decision

---

## 19. Repetition and Memory Control

This is critical. Without memory, the system becomes a random player.

### 19.1 Track

- Recent assets
- Recent tags
- Recent roles
- Recent clusters
- Time since last event
- Cluster dominance duration

### 19.2 Apply

- Recency penalty
- Cluster fatigue penalty
- Dormant cluster boost
- Rare resurfacing bonus

### 19.3 Example

```python
if asset_id in recent_asset_ids[-12:]:
    weight *= 0.1

if cluster_usage_window[cluster] > dominance_threshold:
    weight *= 0.35

if cluster_unused_for_long_time:
    weight *= 1.8
```

---

## 20. Silence as Positive Structure

Silence is not absence. Silence is an **active scheduling choice**.

The scheduler must be allowed to decide:

- No spawn this cycle
- Let density fall
- Leave one layer exposed
- Delay event despite probability

This is necessary for breathing room.

---

## 21. Runtime Logging / Trace

Emit lightweight trace output for debugging:

```
[tick 1042]
state=submerged
layers=3
spawn=no
merge=2 assets
event_prob=0.04
dominant_cluster=dark_drift
```

Also log:

- State transitions
- Interventions
- Merges
- Metadata refresh
- Asset spawns
- Asset suppressions

---

## 22. Failure Isolation

The runtime must continue even if:

- One asset fails to play
- One merge item is invalid
- Metadata refresh fails for one asset
- `world_state` input is missing

Rules:

- Skip bad asset
- Log error
- Keep engine alive

---

## 23. Minimal Runtime API

```python
engine.start()
engine.stop()
engine.pause()
engine.resume()

engine.enqueue_intervention(type, strength=1.0)
engine.update_world_state(world_state)
engine.get_runtime_status()
engine.get_active_layers()
engine.merge_now()   # optional manual merge
```

---

## 24. Minimal Implementation Order

| Step | Task |
|------|------|
| 1 | Create engine context and main loop |
| 2 | Implement active layer model |
| 3 | Implement scheduler tick |
| 4 | Implement state machine |
| 5 | Integrate `active_pool` selection |
| 6 | Integrate `staging_queue` merge |
| 7 | Integrate interventions |
| 8 | Integrate memory / repetition control |
| 9 | Abstract audio backend |
| 10 | Add trace and diagnostics |

---

## 25. Definition of Done

Runtime loop is successful when:

- Engine runs continuously for long periods
- Layers fade in and out without abrupt cuts
- States shift gradually
- Interventions are audible and meaningful
- New assets can enter during runtime
- Current playback is not interrupted by merges
- Repetition is controlled
- Silence can emerge intentionally

---

## 26. Final Definition

This module is the **continuous metabolism** of Becoming.

It must sustain:

- Persistence
- Change
- Memory
- Interruption
- Drift
- Renewal

---

## 27. One-Line Summary

> Build a persistent runtime organism that schedules, remembers, drifts, and absorbs new sound without collapsing.
