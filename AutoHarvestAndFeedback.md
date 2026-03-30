# Runtime ↔ Harvest Feedback Loop

**Becoming Engine – Autonomous Self-Expansion Trigger**

---

## 1. Purpose

Enable the runtime engine to:

- Detect its own deficiencies
- Generate internal demand signals
- Trigger unified harvest automatically
- Evolve without manual intervention

This creates a closed loop:

```
runtime → need → harvest → new assets → runtime
```

---

## 2. Core Principle

Do **NOT** trigger harvest based on time alone.

Instead:

> Trigger harvest based on perceived lack, imbalance, or stagnation.

---

## 3. Architecture

```
Runtime Engine
      ↓
Need Detector
      ↓
Demand Signal
      ↓
Unified Harvest
      ↓
Staging Queue → Active Pool
      ↓
Runtime Engine
```

---

## 4. Need Detector

Add a new module:

```python
class NeedDetector:
    def evaluate(runtime_state, memory_state) -> need_signal:
        pass
```

---

## 5. Runtime Inputs

`NeedDetector` reads:

```python
runtime_state = {
    "active_layers": [...],
    "current_state": str,
    "layer_count": int,
    "role_distribution": dict,
    "cluster_distribution": dict,
}

memory_state = {
    "recent_clusters": [],
    "recent_tags": [],
    "cluster_usage_window": {},
    "last_event_time": float,
}
```

---

## 6. Need Signals

Return:

```python
need_signal = {
    "trigger": bool,
    "type": str,              # deficit / stagnation / imbalance / rupture_need
    "target_clusters": list,
    "intensity": float,
    "mode": str,              # balance / hybrid / drift
}
```

---

## 7. Trigger Conditions

### 7.1 Structural Deficit

```python
if missing_roles or missing_clusters:
    trigger = True
    type = "deficit"
```

Examples:
- No event sounds for a long time
- No texture layer present

### 7.2 Stagnation (**VERY IMPORTANT**)

```python
if low_variation over time_window:
    trigger = True
    type = "stagnation"
```

Metrics:
- Same clusters repeating
- Low entropy
- Low novelty

### 7.3 Imbalance

```python
if cluster_dominance > threshold:
    trigger = True
    type = "imbalance"
```

### 7.4 Silence / Emptiness

```python
if layer_count < min_threshold:
    trigger = True
    type = "underfill"
```

### 7.5 Rupture Need

```python
if time_since_last_event > threshold:
    trigger = True
    type = "rupture_need"
```

---

## 8. Intensity Mapping

```python
intensity = (
    deficit_strength
  + stagnation_level
  + imbalance_level
)
# Clamp: 0.2 → 1.0
```

---

## 9. Mode Selection

| Need Type      | Mode      |
|----------------|-----------|
| `deficit`      | `balance` |
| `stagnation`   | `drift`   |
| `imbalance`    | `hybrid`  |
| `rupture_need` | `drift`   |
| `underfill`    | `balance` |

---

## 10. Target Cluster Selection

```python
if type == "deficit":
    target_clusters = lowest_count_clusters

if type == "stagnation":
    target_clusters = least_recently_used

if type == "imbalance":
    target_clusters = non_dominant_clusters

if type == "rupture_need":
    target_clusters = ["rupture_event", "pulse_rhythm"]
```

---

## 11. Cooldown Mechanism (**CRITICAL**)

Prevent over-triggering:

```python
HARVEST_COOLDOWN = 300  # seconds

if now - last_harvest_time < cooldown:
    trigger = False
```

---

## 12. Trigger Execution

Inside runtime loop:

```python
if need_signal["trigger"]:
    unified_harvest(
        mode=need_signal["mode"],
        intensity=need_signal["intensity"],
        target_clusters=need_signal["target_clusters"],
    )
```

---

## 13. Logging

```
[need] type=stagnation intensity=0.62
[harvest_trigger] mode=drift clusters=[texture_evolving]
```

---

## 14. Interaction with Focus/Collapse

### During Focus

- Suppress new harvest triggers (unless extreme)
- Allow continuation of obsession

### During Collapse

- Allow immediate harvest
- Force drift mode

---

## 15. Integration Points

### Runtime Loop

```python
need_signal = need_detector.evaluate(runtime_state, memory_state)

if safe_point and need_signal.trigger:
    trigger_harvest(need_signal)
```

### Unified Harvest

Accept external override:

```python
run_unified_harvest(
    mode,
    intensity,
    target_clusters,
)
```

---

## 16. Safety Rules

- **NEVER** interrupt current playback
- **NEVER** block runtime loop
- Run harvest asynchronously
- Queue multiple triggers safely

---

## 17. Minimal Implementation Plan

1. Implement `NeedDetector`
2. Define trigger conditions
3. Add cooldown system
4. Integrate into runtime loop
5. Connect to `unified_harvest`
6. Add logging

---

## 18. Success Criteria

System is correct when:

- Harvest triggers without user input
- Triggers reflect runtime condition
- System avoids repetition
- System recovers from stagnation
- Sound library evolves continuously

---

## 19. Final Definition

> This module enables: **self-awareness → self-demand → self-expansion**

---

## 20. One-Line Summary

> A system that **notices what it lacks and goes out to find it**.