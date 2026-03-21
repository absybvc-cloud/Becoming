# Becoming Engine – Concept & Implementation Blueprint
## Phase 2 Foundation: Generative Audio Ecology Engine

---

# 1. Core Idea

This engine is NOT a sequencer.
This engine is NOT a playlist generator.

This engine is:

> A continuously evolving sound ecology  
> driven by state, memory, probability, and external perturbation.

It does not “play audio”.
It **maintains a sonic environment**.

---

# 2. System Philosophy

The system must behave like:

- weather (slow drift + sudden events)
- geology (layers + pressure + rupture)
- organism (pulse + adaptation + fatigue)
- memory (repetition + forgetting + resurfacing)

---

# 3. Fundamental Model

The system is composed of:


Sound Library → Role Mapping → State Machine → Weight Engine → Scheduler → Audio Output


---

# 4. Sound Roles (Critical Abstraction)

All audio segments MUST be mapped into system roles.

## 4.1 Roles

### Ground (Bed Layer)
- continuous
- low variation
- stabilizing

Examples:
- drift
- pad
- long field recordings

---

### Texture (Surface Layer)
- medium variation
- granular / noisy / evolving

Examples:
- texture
- noise
- environmental fragments

---

### Event (Disruption Layer)
- rare
- high contrast
- breaks continuity

Examples:
- accent
- glitch
- sharp noise
- impact

---

### Pulse (Internal Rhythm Layer)
- rhythmic or semi-rhythmic
- represents system “life”

Examples:
- pulse
- heartbeat-like material

---

# 5. System State (Global Condition)

The system operates under a current STATE.

A state defines:

- role density
- tag weighting
- event probability
- temporal behavior

---

## 5.1 Example States

### Submerged
- slow
- low contrast
- dominated by Ground + Texture
- minimal Event

---

### Tense
- higher density
- Event probability increases
- Pulse tightens

---

### Dissolved
- blurred boundaries
- long pads dominate
- low structure

---

### Rupture
- short duration
- high Event frequency
- unstable

---

## 5.2 State Properties

Each state must define:

- role_weights:
    Ground: float
    Texture: float
    Event: float
    Pulse: float

- tag_bias:
    dict[tag → weight]

- event_probability:
    float (0–1)

- max_layers:
    int

- duration_range:
    [min_sec, max_sec]

- transition_tendency:
    dict[state → probability]

---

# 6. Weight Engine (Core Logic)

The system does NOT choose sounds randomly.

It uses weighted selection:


final_weight =
base_weight
× state_weight
× tag_bias
× rarity_boost
× recency_penalty
× external_modulation


---

## 6.1 Components

### Base Weight
From sound metadata.

---

### State Weight
Defined by current system state.

---

### Tag Bias
From current state + external variables.

---

### Rarity Boost
If a sound/tag has not appeared recently:
- increase probability

---

### Recency Penalty
If used recently:
- decrease probability

---

### External Modulation
Controlled by world inputs (see section 8)

---

# 7. Scheduler (Conductor)

This is the MOST IMPORTANT module.

It decides:

- when to spawn a sound
- which role needs filling
- when to remove layers
- when to trigger events
- when to transition state

---

## 7.1 Responsibilities

- Maintain active layers
- Enforce max_layers
- Prevent overcrowding
- Handle fade in/out
- Track system density
- Avoid repetition loops

---

## 7.2 Layer Behavior

Each active layer has:

- role
- start_time
- expected_duration
- fade_in
- fade_out
- current_gain

---

# 8. External Variables (World Interface)

The engine must accept external input:


world_state = {
time_of_day,
runtime_duration,
environment_noise,
weather,
human_control,
system_history
}


---

## 8.1 Minimum Required Inputs

### Time
- affects density and brightness

---

### Tension (0–1)
- controls Event probability
- compresses Pulse

---

### Density (0–1)
- controls max layers
- controls overlap

---

### Noise Level
- increases texture/noise probability

---

### Human Bias
- manual override weighting

---

# 9. Memory System

The engine must remember:

- recently played segments
- recently used tags
- current density trend
- last event time

---

## 9.1 Effects

- avoid repetition
- create long-term variation
- enable “return” of forgotten material

---

# 10. Anti-Center Mechanism

The system must avoid stable centers.

Implement:

### Popularity Suppression
- frequently used tags → weight decreases

### Edge Promotion
- rare tags → weight increases

---

This ensures:

> the system continuously drifts away from equilibrium

---

# 11. Temporal Behavior

The system must have inertia.

No instant switching.

---

## 11.1 State Transition Rules

- states persist for a duration range
- transitions are probabilistic
- transitions have fade time

---

## 11.2 Layer Lifetimes

- each role has typical duration ranges
- ground > texture > pulse > event

---

# 12. Minimum Viable Engine (MVE)

Implement in this order:

---

## Step 1: Role Mapping
Assign each segment:
- role
- energy
- density
- loopability
- eventfulness

---

## Step 2: Simple 4-Layer Engine
Support:
- Ground
- Texture
- Event
- Pulse

---

## Step 3: State Machine
Implement 3–5 states.

---

## Step 4: Weighted Selection
Implement probability-based picking.

---

## Step 5: Scheduler
Spawn + remove sounds over time.

---

## Step 6: Memory
Track recent usage.

---

## Step 7: External Input Hook
Even if dummy values at first.

---

# 13. What NOT to Build (Important)

Do NOT:

- build a timeline sequencer
- hardcode transitions
- rely on pure randomness
- treat audio as linear composition
- optimize for “musical correctness”

---

# 14. Final Definition

This system is successful when:

- it runs continuously without looping patterns
- it evolves over long time scales
- it reacts to input variables
- it produces non-repeating structures
- it feels like a process, not a composition

---

# 15. One Sentence Summary

Build:

> a state-driven, memory-aware, probability-weighted, externally modulated sound ecology engine.

Not:

> a music generator.

---