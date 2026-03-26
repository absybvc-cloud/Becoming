# Hot Ingest Runtime – Minimal Safe Live Integration

**Becoming Engine – Phase 2 Foundation**

---

## 1. Purpose

Enable the engine to:

- Continuously ingest new audio
- Attach tags and roles
- Safely inject new assets into runtime
- **Without** interrupting current playback
- **Without** corrupting system state

This is a simplified alternative to full snapshot architecture.

---

## 2. Core Design Principle

**Do not** allow runtime to directly read the mutable library.

Instead:

> Runtime reads from a stable **Active Pool**.  
> Background processes write into a **Staging Queue**.  
> Merge happens only at **safe boundaries**.

---

## 3. System Components

```
Library DB (full storage)
        ↓
Staging Queue (new validated assets)
        ↓
Active Pool (runtime readable)
        ↓
Scheduler (selection + playback)
```

---

## 4. Data Structures

### 4.1 Active Pool

In-memory structure used by runtime:

```python
active_pool = {
    asset_id: {
        "path": str,
        "role": str,
        "tags": list[str],
        "duration": float,
        "energy": float,
        "density": float,
        "last_used": float,
        "usage_count": int,
        "metadata_version": int,
    }
}
```

### 4.2 Staging Queue

Temporary holding area:

```python
staging_queue = [
    {
        "asset_id": ...,
        "path": ...,
        "role": ...,
        "tags": ...,
        "duration": ...,
        "energy": ...,
        "density": ...,
    }
]
```

### 4.3 Dirty Metadata Set

```python
metadata_dirty = set()  # asset_id values
```

Used when tags or roles are modified at runtime.

---

## 5. Asset Lifecycle (Simplified)

```
downloaded → normalized → segmented → auto_tagged → (optional) reviewed → staging_queue → active_pool
```

---

## 6. Minimum Activation Criteria

An asset can enter the Active Pool **only** if:

- File exists on disk
- `duration > 0.5s`
- Role is assigned
- At least 1 tag exists

---

## 7. Runtime Loop Integration

### 7.1 Main Loop Structure

```python
while engine_running:
    scheduler_tick()

    if safe_point():
        merge_staging_queue()

    if safe_point():
        refresh_dirty_metadata()

    sleep(tick_interval)
```

### 7.2 Safe Point Definition

A **safe point** is when:

- **Not** currently selecting new sounds
- **Not** mid-crossfade
- **Not** updating active layers

Recommended timing:

- End of scheduler tick
- Before next spawn cycle

---

## 8. Merge Logic

### 8.1 Merge Function

```python
def merge_staging_queue():
    if not staging_queue:
        return

    for asset in staging_queue:
        active_pool[asset.asset_id] = asset

    staging_queue.clear()
    rebuild_indices()
```

### 8.2 Rebuild Indices

Must update:

- Cluster counts
- Role distribution
- Tag lookup
- Selection weights (optional lazy update)

---

## 9. Metadata Update (Hot Tag Update)

### 9.1 When Tags Change

**Do not** modify `active_pool` immediately. Instead:

```python
metadata_dirty.add(asset_id)
```

### 9.2 Refresh Logic

```python
def refresh_dirty_metadata():
    for asset_id in metadata_dirty:
        updated = load_from_db(asset_id)
        active_pool[asset_id].tags = updated.tags
        active_pool[asset_id].role = updated.role
        active_pool[asset_id].metadata_version += 1

    metadata_dirty.clear()
```

---

## 10. Scheduler Constraints

### 10.1 Selection Must Use Active Pool Only

```python
candidates = active_pool.values()
```

### 10.2 New Assets Only Affect Future

- Do **not** interrupt active layers
- Do **not** re-evaluate currently playing sounds
- Only affect the next selection cycle

---

## 11. Concurrency Rules

### 11.1 Allowed Parallelism

- Ingest (download)
- Segmentation
- Auto-tagging
- Review edits
- Rebalance calculation

### 11.2 Forbidden Direct Access

These **must not** touch `active_pool`:

- Ingest pipeline
- Auto-tag
- Rebalance
- Drift

They must only:

1. Write to DB
2. Push to `staging_queue`

---

## 12. Error Handling

### 12.1 Invalid Asset

If an asset fails validation:

```python
asset_state = "quarantined"
```

**Do not** push to `staging_queue`.

### 12.2 Merge Failure

If merge fails:

- Skip asset
- Log error
- Continue system

---

## 13. Optional Enhancements (Later)

### 13.1 Batch Merge Strategy

- Merge every N seconds, or
- When staging size exceeds a threshold

### 13.2 Soft Activation

New assets enter with lower weight:

```python
new_asset_weight *= 0.5  # for first N cycles
```

### 13.3 Warmup Delay

Delay usage of new assets:

```python
activation_delay = 10  # to 30 seconds
```

---

## 14. Minimal Implementation Plan

| Step | Task |
|------|------|
| 1 | Implement `staging_queue` |
| 2 | Implement `active_pool` |
| 3 | Implement `merge_staging_queue()` |
| 4 | Integrate into scheduler loop |
| 5 | Add `metadata_dirty` system |
| 6 | Test live ingestion during playback |

---

## 15. Success Criteria

System is correct when:

- New sounds appear gradually during runtime
- No crashes during ingestion
- Playback is uninterrupted
- Tags can update without breaking selection
- System remains stable over long runs

---

## 16. Final Definition

This system enables **safe, incremental, real-time evolution of the sound library** without requiring a full snapshot rebuild.

---

## 17. One-Line Summary

> Build a two-buffer live ingestion system using `active_pool` + `staging_queue` + safe merge.