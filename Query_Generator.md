# Query Generator – Desire → Language → Sound

**Becoming Engine – Autonomous Sound Discovery Module**

---

## 1. Purpose

The Query Generator transforms internal system desire into external search queries.

It enables the system to:

- Actively search for new sounds
- Expand beyond existing dataset
- Evolve its sonic identity
- Create non-repeating semantic trajectories

This module connects:

> `internal state → language → world → new audio`

---

## 2. Core Principle

Do **not** generate static or deterministic queries.

> Generate drifting, unstable, semantically evolving queries.

The system should:

- Mutate its own queries over time
- Avoid repetition
- Mix concepts across clusters
- Reflect system state and memory

---

## 3. Architecture

```
Desire State
    ↓
Semantic Expansion
    ↓
Query Mutation
    ↓
Language Realization
    ↓
Source Adapter
```

---

## 4. Input: Desire State

```python
desire_state = {
    "focus_cluster": str,
    "state": str,
    "tension": float,
    "density": float,
    "recent_clusters": list[str],
    "fatigue": dict[str, float],
    "time_of_day": str,
}
```

---

## 5. Semantic Map (Critical)

Define a manually curated semantic space.

```python
SEMANTIC_MAP = {
    "texture_evolving": [
        "granular", "shimmering", "unstable", "metallic",
        "digital decay", "glitch texture", "flowing particles",
    ],
    "nature_field": [
        "wind", "forest", "rain", "water stream",
        "insects", "night ambience",
    ],
    "dark_drift": [
        "low drone", "sub bass", "dark ambient",
        "void", "rumble", "deep hum",
    ],
    "industrial_noise": [
        "machine", "metal", "factory",
        "mechanical noise", "grinding", "electrical hum",
    ],
    "rupture_event": [
        "impact", "explosion", "glitch",
        "break", "crack", "distortion",
    ],
}
```

---

## 6. State Semantic Modifiers

```python
STATE_TERMS = {
    "submerged": ["distant", "underwater", "blurred", "deep"],
    "tense":     ["tight", "pressured", "compressed"],
    "dissolved": ["soft", "diffused", "floating"],
    "rupture":   ["sudden", "violent", "sharp"],
    "drifting":  ["slow", "evolving", "endless"],
}
```

---

## 7. Query Generation Pipeline

### Step 1 – Select Base Cluster

```python
base_cluster = desire_state["focus_cluster"]
```

### Step 2 – Semantic Expansion

```python
base_terms  = sample(SEMANTIC_MAP[base_cluster], k=2)
cross_cluster = sample_other_clusters(exclude=base_cluster, k=1)
cross_terms = sample(SEMANTIC_MAP[cross_cluster], k=1)
state_terms = sample(STATE_TERMS[state], k=1)
```

### Step 3 – Noise Injection

Add 0–2 random modifiers:

```python
NOISE_TERMS = [
    "field recording", "ambient", "background",
    "loop", "texture", "soundscape",
]
```

### Step 4 – Compose Query Tokens

```python
tokens = shuffle(
    base_terms + cross_terms + state_terms + noise_terms
)
```

### Step 5 – Language Realization

```python
query = " ".join(tokens)
```

Example output:

> `"metallic granular deep evolving ambient texture"`

---

## 8. Query Mutation (Drift Mechanism)

Do **not** generate queries from scratch every time. Instead:

```
query(t+1) = mutate(query(t))
```

### Mutation Methods

| Method             | Example                                |
| ------------------ | -------------------------------------- |
| Replace one token  | `"metallic"` → `"industrial"`          |
| Add one token      | append `"field recording"`             |
| Remove one token   | drop a random token                    |
| Swap token order   | shuffle two adjacent tokens            |

### Mutation Probability

```python
mutation_rate = 0.3 ~ 0.7
```

---

## 9. Query Memory

```python
recent_queries = deque(maxlen=50)
```

### Avoid Repetition

Reject a query if:

- Identical to a recent query
- High token overlap (> 70%)

---

## 10. Failure Feedback

Track query performance:

```python
query_feedback = {
    query: {
        "results_count": int,
        "accepted_assets": int,
        "avg_quality": float,
    }
}
```

### Adjust Behavior

- **Poor queries** → reduce weight of their tokens
- **Good queries** → reinforce tokens

---

## 11. Source Adapter Interface

```python
class SourceAdapter:
    def search(self, query: str) -> list[SearchResult]:
        pass

    def download(self, result: SearchResult) -> file_path:
        pass
```

### Example: Freesound Adapter

```python
def search(self, query):
    return freesound_api.search(
        text=query,
        duration_min=3,
        duration_max=120,
        tags=["ambient", "texture"],
    )
```

---

## 12. Integration with Ingest Pipeline

```
query → search → download → segment → auto-tag → staging_queue
```

---

## 13. Scheduling Query Generation

Do **not** generate queries continuously.

### Trigger Conditions

- Every N minutes
- When cluster imbalance detected
- When drift focus changes
- When ingestion falls below threshold

### Example

```python
if time_since_last_query > 300:
    generate_query()
```

---

## 14. Cross-Cluster Metonymy (Critical)

Allow semantic leakage:

```python
if random() < 0.4:
    inject term from unrelated cluster
```

Example output:

> `"water metallic granular texture"`

This creates:

- Semantic drift
- Unexpected sound discovery
- Non-linear evolution

---

## 15. Configuration

```python
QUERY_CONFIG = {
    "base_terms": 2,
    "cross_terms": 1,
    "state_terms": 1,
    "noise_terms": 1,
    "mutation_rate": 0.5,
    "max_query_length": 8,
}
```

---

## 16. Minimal Implementation Plan

1. Implement `SEMANTIC_MAP`
2. Implement `generate_query(desire_state)`
3. Implement `mutate_query(previous_query)`
4. Add `recent_queries` memory
5. Connect to one source (Freesound)
6. Connect to ingest pipeline

---

## 17. Success Criteria

The system is successful when:

- Queries are non-repeating
- Queries evolve over time
- New types of sounds appear in library
- System discovers unexpected material
- Semantic drift is observable

---

## 18. Final Definition

> This module gives the system the ability to speak to the world in order to transform itself.

---

## 19. One-Line Summary

> Build a drifting language generator that converts desire into discoverable sound.


