# Unified Harvest Engine

## Rebalance + Query Generator Integration

**Becoming System — Intelligent Library Expansion Module**

---

## 1. Objective

Merge the existing:

- **Rebalance system** (deficit-driven)
- **Query Generator system** (desire-driven)

Into a unified module:

> **Unified Harvest Engine**

This system must:

- Maintain structural balance
- Introduce controlled imbalance (drift)
- Generate intelligent search queries
- Continuously evolve the sound library
- Integrate seamlessly with existing ingest pipeline

---

## 2. Core Principle

**DO NOT** treat rebalance and query generation as separate actions.

> Rebalance defines *"what is missing"*
> Query Generator defines *"how to search for it"*

---

## 3. High-Level Architecture

```
Library Stats
     ↓
Deficit Analysis (Rebalance)
     ↓
Desire Layer (Drift + Memory + Fatigue)
     ↓
Query Generation
     ↓
Harvest Execution
     ↓
Ingest Pipeline
```

---

## 4. Replace Existing Functions

Replace:

- `generate_query()`
- `smart_rebalance()`
- `generate_harvest_plan()`

With:

```python
run_unified_harvest(mode: str)
```

---

## 5. Modes

Support three modes:

### 5.1 `"balance"`

Pure rebalance behavior:

- Prioritize deficit clusters
- Minimal semantic drift
- Deterministic queries

### 5.2 `"drift"`

Pure desire behavior:

- Ignore strict deficit
- Prioritize novelty and underused clusters
- High semantic mutation

### 5.3 `"hybrid"` (default)

Blend both:

- Deficit determines direction
- Desire modifies query generation

---

## 6. Deficit Analysis (Rebalance Layer)

Input:

```python
cluster_stats = {
    cluster: {
        "count": int,
        "target": int,
        "deficit": int
    }
}
```

Compute:

```python
deficit_score = max(0, target - count)
```

Normalize across clusters.

---

## 7. Desire Layer (New)

Enhance cluster scoring:

```
cluster_score =
    deficit_weight × deficit_score
  + novelty_weight × novelty_score
  - fatigue_weight × fatigue_score
  + drift_bias
```

### 7.1 Novelty Score

$$\text{novelty\_score} \propto \text{time\_since\_last\_used}$$

### 7.2 Fatigue Score

$$\text{fatigue\_score} \propto \text{recent\_usage\_frequency}$$

### 7.3 Drift Bias

- Random walk
- Influenced by current state (`submerged`, `rupture`, etc.)

---

## 8. Cluster Selection

Instead of selecting **all** deficit clusters:

```python
selected_clusters = weighted_sample(cluster_score, k=N)
```

Where:

- `N` = number of queries per cycle
- Allow repetition only if deficit is extreme

---

## 9. Query Generation Integration

For each selected cluster:

```python
query = QueryGenerator.generate(desire_state_for_cluster)
```

Where:

```python
desire_state_for_cluster = {
    "focus_cluster": str,
    "current_state": str,
    "tension": float,
    "density": float,
    "recent_clusters": list,
    "fatigue": dict,
}
```

---

## 10. Harvest Plan

Generate a plan:

```python
harvest_plan = [
    {
        "cluster": str,
        "query": str,
        "target_count": int,
        "priority": float,
    }
]
```

### 10.1 Target Count Logic

```
target_count = base_harvest_size × normalized_cluster_score
```

---

## 11. Execution Engine

Execute sequentially:

```python
for task in harvest_plan:
    run_harvest(
        query=task["query"],
        limit=task["target_count"],
        auto_tag=True,
    )
```

### 11.1 Stop Support

Must support:

- User stop button
- Graceful termination
- Partial completion

---

## 12. UI Integration

Replace existing buttons:

| Old                  | New                        |
|----------------------|----------------------------|
| `"generate query"`   | **Unified Harvest** button |
| `"smart rebalance"`  | Mode selector              |

### Primary Button

```
[ UNIFIED HARVEST ]
```

### Mode Selector

```
Mode: [ balance ] [ hybrid ] [ drift ]
```

### Optional Controls

| Control              | Range   |
|----------------------|---------|
| Intensity            | 0.0–1.0 |
| Drift amount         | 0.0–1.0 |
| Max queries          | int     |
| Max downloads/query  | int     |

---

## 13. Logging

Log per cycle:

```
[harvest]
mode=hybrid
selected_clusters=[texture_evolving, industrial_noise]
queries=[
  "metallic granular evolving texture",
  "industrial hum mechanical dark ambient"
]
downloaded=18
accepted=12
```

---

## 14. Integration with Existing Pipeline

Unified Harvest must:

- Call existing ingest pipeline
- Reuse auto-tag system
- Push results to `staging_queue`
- **NOT** modify `active_pool` directly

---

## 15. Constraints

- **MUST** avoid query repetition
- **MUST** avoid overfilling dominant clusters
- **MUST** support interruption
- **MUST** remain stable during runtime

---

## 16. Minimal Implementation Plan

| Step | Task                                              |
|------|---------------------------------------------------|
| 1    | Extract rebalance deficit calculation              |
| 2    | Implement `cluster_score` (deficit + desire)       |
| 3    | Replace `generate_query` with cluster-aware generator |
| 4    | Implement `harvest_plan` builder                   |
| 5    | Implement `run_unified_harvest()`                  |
| 6    | Replace UI buttons                                 |

---

## 17. Success Criteria

The system is successful when:

- Library remains roughly balanced over time
- But continuously drifts and evolves
- New sound types appear
- No static equilibrium forms
- Queries are diverse and non-repeating

---

## 18. Final Definition

> This system transforms **static rebalance** into **adaptive evolutionary expansion**.

---

## 19. One-Line Summary

> Build a system that balances the library while continuously destabilizing it through intelligent search.