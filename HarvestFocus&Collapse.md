# Harvest Focus & Collapse – GUI-Integrated Version

**Becoming Engine – Obsession Layer (Integrated with Unified Harvest UI)**

---

## 1. Purpose

Enhance the existing Unified Harvest system with:

- **Focus** — temporary obsession
- **Saturation tracking**
- **Collapse** — forced reset

This version is specifically designed to integrate with:

- Unified harvest button
- Mode selector (`balance` / `hybrid` / `drift`)
- Break balance button
- Intervention panel
- Task log output

---

## 2. Core Principle

The system should:

- Not remain evenly balanced
- Not remain purely random
- Not remain purely deficit-driven

Instead:

> It should temporarily concentrate, overgrow, then destabilize.

---

## 3. Integration Overview

This module modifies:

- `unified_harvest.py`
- `HarvestState`
- `score_clusters()`
- `build_harvest_plan()`
- GUI triggers (buttons)

---

## 4. Extended HarvestState

Add the following state dictionaries:

```python
focus_state = {
    "active": False,
    "cluster": None,
    "started_at": 0.0,
    "duration": 0.0,
    "intensity": 1.0,
}

collapse_state = {
    "active": False,
    "triggered_at": 0.0,
    "duration": 0.0,
    "target_cluster": None,
}

saturation = {
    cluster: 0.0  # per-cluster saturation level
}
```

---

## 5. Focus Activation (Hook into Existing Flow)

### 5.1 Trigger Points

Focus can start when:

- `mode == "drift"`
- `mode == "hybrid"` AND `random < drift_amount`
- User clicks **"enter drift"**

### 5.2 GUI Hook

When user presses `[enter drift]`:

```python
activate_focus(force=True)
```

### 5.3 Activation Logic

```python
def activate_focus(force=False):
    if focus_state["active"] and not force:
        return

    focus_cluster = weighted_sample(cluster_score)

    focus_state.update({
        "active": True,
        "cluster": focus_cluster,
        "started_at": now,
        "duration": random(600, 1800),
        "intensity": random(2.0, 4.0),
    })

    log("[focus] cluster={} intensity={}".format(
        focus_cluster,
        focus_state["intensity"],
    ))
```

---

## 6. Focus Effect (Modify `score_clusters`)

Inside `score_clusters()`, add:

```python
if focus_state["active"]:
    if cluster == focus_state["cluster"]:
        cluster_score *= focus_state["intensity"]
```

### Additional Effect

In `build_harvest_plan()`:

```python
if cluster == focus_state["cluster"]:
    target_count *= 1.5  # range: 1.5 ~ 2.5
```

---

## 7. Saturation Tracking

### 7.1 Update per Round

After each harvest round:

```python
saturation[cluster] = (
    0.4 * normalized_presence
  + 0.4 * recent_usage
  + 0.2 * dominance_duration
)
```

### 7.2 Log

```
[saturation] texture_evolving=0.78
```

---

## 8. Collapse Trigger

### 8.1 Automatic Trigger

```python
if saturation[focus_cluster] > 0.75:
    trigger_collapse(focus_cluster)
```

### 8.2 Manual Trigger (GUI)

When user clicks `[force collapse]`:

```python
trigger_collapse(current_focus_cluster or dominant_cluster)
```

---

## 9. Collapse Activation

```python
def trigger_collapse(cluster):
    collapse_state.update({
        "active": True,
        "triggered_at": now,
        "duration": random(60, 240),
        "target_cluster": cluster,
    })

    focus_state["active"] = False

    log("[collapse] triggered_by={}".format(cluster))
```

---

## 10. Collapse Effects

Modify `score_clusters()`:

```python
if collapse_state["active"]:
    if cluster == collapse_state["target_cluster"]:
        cluster_score *= 0.1
```

### Global Effects

Inside `run_unified_harvest()`:

```python
if collapse_state["active"]:
    # reduce target_count globally
    # increase novelty_weight
    # increase mutation_rate
```

---

## 11. Query Generator Integration

Pass additional context:

```python
desire_state.update({
    "focus_cluster": focus_state["cluster"],
    "collapse_active": collapse_state["active"],
    "avoid_cluster": collapse_state["target_cluster"],
})
```

### Query Behavior

During collapse:

- Avoid dominant cluster terms
- Increase cross-cluster mutation
- Inject unrelated semantics

---

## 12. Lifecycle Management

### 12.1 Focus End

```python
if now > focus_state["started_at"] + focus_state["duration"]:
    focus_state["active"] = False
    log("[focus] ended")
```

### 12.2 Collapse End

```python
if now > collapse_state["triggered_at"] + collapse_state["duration"]:
    collapse_state["active"] = False
    log("[collapse] ended")
```

### 12.3 Cooldown

Prevent immediate re-focus:

```python
focus_cooldown = random(300, 900)
```

---

## 13. GUI Behavior

### 13.1 Mode Interaction

| Mode      | Focus Behavior |
|-----------|----------------|
| `balance` | disabled       |
| `hybrid`  | occasional     |
| `drift`   | frequent       |

### 13.2 Buttons Mapping

| Button            | Effect            |
|-------------------|-------------------|
| unified harvest   | normal loop       |
| break balance     | boost drift_bias  |
| enter drift       | force focus       |
| force collapse    | trigger collapse  |
| stabilize         | reduce intensity  |

---

## 14. Logging (Task Log Panel)

```
[focus] cluster=texture_evolving intensity=3.1
[saturation] texture_evolving=0.81
[collapse] triggered_by=texture_evolving
[collapse] ended
```

---

## 15. Interaction with Existing System

This module must:

- **NOT** break existing `unified_harvest` loop
- **NOT** directly modify `active_pool`
- **ONLY** modify scoring + planning + query generation
- Remain compatible with `staging_queue`

---

## 16. Minimal Implementation Steps

1. Extend `HarvestState`
2. Add focus activation logic
3. Modify `score_clusters()`
4. Add saturation tracking
5. Implement collapse trigger
6. Modify query generator input
7. Hook into GUI buttons
8. Add logging

---

## 17. Success Criteria

System behaves correctly when:

- Unified harvest sometimes locks onto one cluster
- Cluster grows disproportionately
- Saturation visibly increases
- Sudden collapse reduces that cluster
- System shifts into a new direction afterward

---

## 18. Final Definition

> This module turns the current system into **a system that becomes obsessed, overproduces, then rejects itself**.

---

## 19. One-Line Summary

> A harvest system that **fixates, saturates, collapses, and continues evolving**.
