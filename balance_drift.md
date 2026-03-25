# Balance Drift — Redefining What "Balanced" Means

## Becoming Phase 2.1

---

## 1. Problem

The current balance system enforces a fixed definition:

> "Balanced" = every cluster has equal count → entropy ratio ≈ 1.0

This is a static, dead equilibrium. A perfectly uniform distribution is:

- Predictable
- Emotionally flat
- Antithetical to a living system

The balance score (95.8%, 98%, 100%) is a number pursuing a **frozen ideal**.

---

## 2. Core Idea

> The definition of "balanced" should itself drift.

There is no permanent 100%. What is "perfect" today is "stale" tomorrow.

Instead of:

```
target = total / n_clusters   (uniform for every cluster)
```

We introduce:

```
target[cluster] = base × shape_weight[cluster]
```

Where `shape_weight` is a **time-varying distribution shape** that redefines
what the system considers its ideal form.

---

## 3. Shape Vocabularies

A **shape** is a named target distribution. The system drifts between shapes.

### 3.1 Built-in Shapes

| Shape Name         | Description                                    | Weight Pattern                                      |
|--------------------|------------------------------------------------|-----------------------------------------------------|
| `uniform`          | Classical equal distribution                   | all clusters = 1.0                                  |
| `convergent`       | One cluster dominates, others orbit            | focus = 2.5, neighbors = 1.2, rest = 0.6           |
| `bipolar`          | Two opposing poles, hollow middle              | pole_a = 2.0, pole_b = 2.0, rest = 0.5            |
| `cascade`          | Descending gradient — ranked hierarchy         | rank 1 = 2.0, rank 2 = 1.7, ... rank N = 0.5      |
| `hollow`           | Periphery heavy, center suppressed             | rare clusters boosted, dominant suppressed          |
| `surge`            | Everything amplified — maximum saturation      | all clusters × 1.5                                  |
| `drought`          | Everything suppressed — minimal acquisition    | all clusters × 0.3                                  |
| `seasonal`         | Time-of-day / runtime driven shift             | dark/ambient at night, nature/tonal at day          |

### 3.2 Shape Definition

```python
Shape = dict[str, float]   # cluster_name → weight multiplier

# Example: "convergent" focused on dark_drift
{
    "dark_drift": 2.5,
    "ambient_float": 1.2,
    "tonal_meditative": 1.2,
    "nature_field": 0.6,
    "urban_field": 0.6,
    "industrial_noise": 0.6,
    "texture_evolving": 0.6,
    "rupture_event": 0.6,
    "pulse_rhythm": 0.6,
}
```

---

## 4. Balance Score Redefinition

### 4.1 Old Model

```
balance_score = entropy(actual) / max_entropy
```

This measures distance from **uniform**. It can only see one shape.

### 4.2 New Model

```
balance_score = 1.0 - divergence(actual, target_shape)
```

Where `divergence` is the Jensen-Shannon divergence between:
- The actual distribution (what the library looks like)
- The target shape (what the system currently *wants* to look like)

When the target shape IS uniform, this reduces to the old model.
When the target shape is `convergent`, a library with one dominant cluster
scores HIGH — because that's what's desired.

### 4.3 Display

The GUI and report should show:

```
Shape: convergent (focus=dark_drift)
Balance: 87.3% (toward current shape)
Drift:   uniform → convergent (43% transitioned)
```

Not just a single percentage, but where the system is going.

---

## 5. Shape Drift Mechanism

### 5.1 Drift Engine Integration

The Drift Engine already produces `desire_weight` per cluster.
The Shape Drift system reads these desires and constructs the target shape:

```python
def compute_target_shape(desires: dict[str, float]) -> dict[str, float]:
    """Convert desire weights into a normalized target distribution shape."""
    total = sum(desires.values())
    n = len(desires)
    if total == 0:
        return {name: 1.0 for name in desires}
    
    # Normalize so average weight = 1.0
    avg = total / n
    return {name: w / avg for name, w in desires.items()}
```

This means: when the Drift Engine focuses on `dark_drift` (desire=3.5),
the target shape shifts to want MORE dark_drift and LESS of saturated clusters.

### 5.2 Shape Blending

Shapes transition smoothly. At any moment the active shape is a blend:

```
active_shape = α × current_shape + (1 - α) × next_shape
```

Where α decays from 1.0 → 0.0 over the transition period.

### 5.3 Named Shape Triggers

Shapes can be triggered by:
- **Drift phase transitions**: collapse → hollow, saturation → convergent
- **Time**: seasonal shape at dawn/dusk
- **Manual**: user forces a shape via GUI or MIDI
- **Desire accumulation**: when desires naturally converge on a pattern,
  the system names it and locks it as the current shape

---

## 6. Rebalance Integration

### 6.1 Modified compute_rebalance_plan

Instead of uniform ideal:

```python
# OLD
ideal = total / n_clusters

# NEW
shape = compute_target_shape(drift_engine.get_all_desires())
ideal_for_cluster = (total / n_clusters) * shape[cluster]
```

### 6.2 Modified analyze_balance

The balance report should include:
- `shape_name`: current active shape (or "drifting")
- `shape_weights`: the target distribution weights
- `shape_score`: how close actual distribution is to target shape
- Classic `entropy_score`: still computed for reference

### 6.3 Modified TARGET_BALANCE

The rebalance target is no longer a fixed 0.98.
It becomes: **how close are we to the current shape?**

If the shape says "dark_drift should be 2.5×", and it IS 2.5×, balance is 100%
even though entropy is low.

---

## 7. Implementation Plan

### 7.1 New: `balance_shapes.py`

Module containing:
- `BUILT_IN_SHAPES` dict
- `compute_target_shape(desires)` function
- `blend_shapes(a, b, alpha)` function
- `shape_divergence(actual_dist, target_shape)` → float (0=identical, 1=opposite)
- `name_shape(shape)` → best-matching built-in name or "drifting"

### 7.2 Modify: `balance.py`

- `analyze_balance(db, target_shape=None)`: accept optional shape
  - When shape is provided, compute `shape_score` using JS divergence
  - When shape is None, fall back to entropy ratio (backward compatible)
- `compute_rebalance_plan(report, target_shape=None)`: use shape-aware targets
- `print_balance_report`: display shape info
- `run_rebalance`: pull target_shape from drift engine if running

### 7.3 Modify: `unified_gui.py`

- Show current shape name + transition status in the Drift Engine card
- Add shape override combobox (dropdown of built-in shapes)
- Show shape_score alongside entropy_score in Library tab

### 7.4 Modify: `engine.py`

- New stdin command: `shape <name>` to force a shape
- Drift status line includes current shape name

---

## 8. Phase → Shape Mapping

When the Drift Engine transitions phases, it biases toward a shape:

| Drift Phase        | Suggested Shape   | Reasoning                              |
|--------------------|-------------------|----------------------------------------|
| stabilize          | uniform           | Return to neutral                      |
| drift              | (from desires)    | Let desire weights define the shape    |
| saturation         | convergent        | Amplify the dominant                   |
| collapse           | hollow            | Suppress the oversaturated             |
| reconfiguration    | cascade           | Rebuild with ranked priority           |

---

## 9. Philosophical Frame

> Balance is not a destination. It is a tension between forms.

The system never "achieves" balance. It is always moving toward a shape
it will abandon. The rebalance system harvests sounds to match a form
that is already dissolving.

This creates:
- **Temporal texture** in the library itself (not just playback)
- **Archaeology**: past shapes leave traces in cluster sizes
- **Irony**: the system works hardest to reach a target it will change

The balance score becomes a measure of **coherence with current desire**,
not conformity to a static ideal.

---

## 10. Naming Convention

| Term              | Meaning                                                |
|-------------------|--------------------------------------------------------|
| Shape             | A target distribution (dict of cluster → weight)       |
| Shape Score       | How close actual distribution matches current shape    |
| Entropy Score     | Classic uniformity measure (kept for reference)        |
| Active Shape      | The blended shape the system is currently pursuing     |
| Shape Drift       | The transition between two shapes over time            |
| Shape Archaeology | Historical record of past shapes and their traces      |
