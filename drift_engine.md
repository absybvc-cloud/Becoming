# Drift Engine – Desire & Imbalance System

## Becoming Phase 2 Core Module

---

# 1. Purpose

The Drift Engine introduces **structured imbalance** into the system.

While Rebalance enforces statistical equilibrium, Drift Engine:

> Actively distorts equilibrium to create directional evolution.

This system transforms the library from a static balanced dataset into a:

> Self-modifying, desire-driven sound ecology.

---

# 2. Core Principle

Do NOT break balance randomly.

Instead:

> Continuously redefine what “balance” means.

---

# 3. High-Level Architecture


Library Stats → Drift Engine → Modified Targets → Rebalance → Updated Library


Drift Engine sits BETWEEN:

- analysis (balance)
- action (rebalance/download)

---

# 4. Cluster State Extension

Each cluster must maintain extended attributes:

```python
cluster = {
    count: int,
    target_count: int,
    balance_score: float,

    desire_weight: float,
    lack_score: float,
    novelty_score: float,
    fatigue_score: float,

    drift_bias: float,
    focus_boost: float,

    last_used_timestamp: float,
    recent_usage: float
}

#  5. Desire Weight Model

Core equation:

desire_weight =
    base_balance_weight
  + lack_score
  + novelty_score
  - fatigue_score
  + drift_bias
  + focus_boost
``` id="desire_formula"

---

## 5.1 Components

### Base Balance Weight
From existing rebalance logic.

---

### Lack Score
Measures structural absence:

```text
lack_score = max(0, expected_presence - actual_presence)
Novelty Score

Boost rarely used clusters:

novelty_score ∝ time_since_last_used
Fatigue Score

Suppress overused clusters:

fatigue_score ∝ recent_usage_frequency
Drift Bias

Long-term directional drift:

drift_bias += slow random walk OR external influence
Focus Boost

Temporary obsession:

if cluster == current_focus:
    focus_boost = high_value

# 6. Drift Phases

The system cycles through phases:

Phase A: Stabilize
Rebalance dominates
desire_weight ≈ neutral
Phase B: Drift
Drift Engine modifies targets
imbalance grows
Phase C: Saturation
dominant clusters overload system
fatigue spikes
Phase D: Collapse
forced redistribution
rapid suppression of dominant clusters
Phase E: Reconfiguration
new equilibrium emerges
new focus may be selected
# 7. Focus Mechanism (Desire Center)

At intervals:

select cluster as desire_focus

Duration:

10–30 minutes (configurable)

Effect:

multiply desire_weight
increase ingestion probability
increase playback probability
# 8. Target Mutation (Critical Step)

Replace static rebalance target:

target_count = uniform_distribution

With:

target_count = base_target × desire_weight

This means:

The system does not break balance.
It mutates balance itself.

# 9. Anti-Center Mechanism

Prevent dominance from stabilizing.

## 9.1 Popularity Suppression
if recent_usage > threshold:
    desire_weight *= suppression_factor
## 9.2 Edge Promotion
if cluster is rare:
    desire_weight *= boost_factor

# 10. Memory System

Track:

last_used_timestamp
rolling usage window (e.g., last 30 min)
last focus cluster
cluster dominance duration

## 10.1 Effects
prevents repetition
enables resurfacing
creates long-term structure

# 11. External Modulation

Drift Engine must accept:

world_state = {
    time_of_day,
    runtime_duration,
    tension,
    density,
    noise_level,
    human_bias
}

## 11.1 Effects
Variable	Effect
tension	increases event clusters
density	increases max layers
noise_level	boosts texture/noise
time_of_day	shifts tonal balance
human_bias	direct weight override

# 12. Temporal Smoothing (Inertia)

Avoid abrupt changes:

desire(t+1) = α * desire(t) + (1-α) * new_value

Where:

α ≈ 0.8–0.95
# 13. Integration with Rebalance

Rebalance must use mutated targets:

rebalance_target = drift_engine_output

Rebalance still:

downloads missing assets
fills gaps

BUT:

gaps are now dynamically defined

# 14. UI Extensions

Enhance cluster panel with:

## 14.1 Desire Indicators

For each cluster display:

desire_weight
fatigue_score
novelty_score
focus flag

## 14.2 Visual Encoding
Red → high desire / suppressed
Blue → fatigued / overused
Gold → current focus

## 14.3 Controls

Add:

[Enter Drift Mode]
[Inject Mutation]
[Force Collapse]

# 15. Minimal Implementation Plan
Step 1

Add new cluster fields.

Step 2

Implement desire_weight calculation.

Step 3

Modify rebalance target logic.

Step 4

Add focus mechanism.

Step 5

Add memory tracking.

Step 6

Add phase transitions.

Step 7

Connect external variables.

# 16. Success Criteria

System is correct when:

balance continuously shifts over time
no cluster dominates permanently
rare clusters emerge naturally
system develops long-term evolution
behavior is non-repeating
# 17. Final Definition

This module transforms the system into:

A desire-driven, self-imbalancing, continuously evolving structure.

# 18. One-Line Summary

Build:

a system that creates imbalance, believes in it, and then escapes it.