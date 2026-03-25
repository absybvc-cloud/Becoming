# Becoming UI Redesign Spec
Version: v0.1
Goal: Transform the current control-panel style GUI into a shapeless, living, instrument-like interface for generative sound, drift state, and poem emergence.

---

## 1. Design Intent

The interface should no longer feel like:
- a software dashboard
- a parameter editor
- a machine admin panel

It should feel like:
- a living field
- an instrument
- a weather system
- a zone of influence rather than a panel of commands

The user should feel that they are:
- nudging
- tuning
- biasing
- entering drift
rather than clicking rigid commands.

The UI should express:
- ambiguity
- softness
- emergence
- continuity
- drift
- instability without chaos

---

## 2. Core Visual Language

### 2.1 Replace Boxes with Fields
Current UI uses many hard rectangles and borders.
Redesign should reduce visual boxing and replace it with:
- soft surfaces
- translucent layers
- blurred panels
- fading boundaries
- gradients instead of frames

### 2.2 Surface Style
Use:
- dark atmospheric background
- deep navy / black / muted blue / subtle grey
- soft glow accents
- low-contrast separation
- blur and transparency where possible

Avoid:
- bright white borders
- default OS-looking buttons
- hard container edges
- dense stacked widgets

### 2.3 Motion
All important state changes should be animated gently:
- fade
- drift
- pulse
- slow scale change
- inertia on parameter changes

No abrupt snapping unless it represents collapse or rupture.

---

## 3. Layout Philosophy

The layout should become one continuous spatial composition rather than a stack of panels.

### 3.1 Main Regions
The screen should be organized into 4 atmospheric regions:

1. **State / Influence Region**
   - top or upper-left
   - controls for shaping behavior
   - not a rigid form panel; more like a floating influence layer

2. **Drift Field**
   - center of screen
   - primary visualization region
   - shows transitions, drift activity, semantic motion, state energy

3. **Poem Field**
   - large and visually important
   - poem is not a log output; it is a living textual emergence

4. **System Trace / Whisper Layer**
   - bottom or side
   - minimal status information
   - should not dominate the interface

### 3.2 Navigation
Reduce explicit tab dependency.
Possible approaches:
- floating mode switcher
- segmented soft toggle
- collapsible side sheet
- layered focus system

If tabs remain, visually soften them:
- no heavy borders
- low-contrast active state
- smooth transitions between tabs

---

## 4. Input Panel Redesign

### 4.1 Replace Generic Sliders with Semantic Controls
Current controls:
- Initial State
- Tension
- Density
- Temperature
- Start / Stop
- runtime commands

These should become expressive influence controls.

### 4.2 Control Types

#### Initial State
Current: dropdown
Redesign:
- state selector as a cluster of soft state tokens
- each state represented as a visual mood chip or orb
- example states:
  - submerged
  - drifting
  - tense
  - rupture
  - bloom
  - hollow

Interaction:
- click to bias toward a state
- selected state glows softly
- hovering reveals its behavioral meaning

#### Tension
Current: linear slider
Redesign options:
- elastic line control
- stretched thread visualization
- horizontal control with subtle oscillation

Behavior:
- low tension = loose, floating, permissive transitions
- high tension = constrained, sharp, unstable, expect rupture

#### Density
Current: linear slider
Redesign options:
- fog/thickness control
- layered opacity control
- vertical cloud density bar

Behavior:
- low density = sparse events, silence gaps, room for emergence
- high density = compressed, crowded, clustered sound behavior

#### Temperature
Current: linear slider
Redesign options:
- radial heat dial
- glowing orb
- diffusion ring

Behavior:
- low temperature = stable, repetitive, cool continuity
- high temperature = mutation, replacement, increased drift pressure

### 4.3 Runtime Commands
Current:
- Mutate Replace
- Rare Silence
- Force State
- Apply

Redesign:
Convert commands into a "bias action strip" or "ritual actions" area.

Possible actions:
- Introduce rupture
- Invite silence
- Push drift
- Stabilize field
- Force collapse
- Re-seed cluster

These should not look like standard buttons.
Use:
- pill buttons
- floating action capsules
- icon + text
- hover descriptions

### 4.4 Input Panel Structure
Use two layers:
- **continuous influences** (tension / density / temperature / phase scale)
- **discrete interventions** (collapse / stabilize / mutate / silence)

This separation is important conceptually.

---

## 5. Drift Field Redesign

### 5.1 Purpose
The current drift area is visually empty.
It should become the main living center of the interface.

### 5.2 Minimum Viable Visualization
Implement a real-time animated field showing:
- active sound nodes
- recent transitions
- current cluster
- drift intensity
- phase state
- local motion / attraction / collapse

### 5.3 Visual Metaphors
Choose one or combine several:

#### Option A: Particle Field
- active sounds shown as particles/orbs
- transitions shown as faint trails
- new selections pulse in
- collapse pulls nodes inward
- stabilize slows motion

#### Option B: Semantic Constellation
- active clips shown as stars or points
- nearest semantic/tag links shown as thin lines
- drift phase shows path through graph

#### Option C: Fluid Noise Field
- background reacts to engine parameters
- density thickens the field
- temperature increases turbulence
- tension sharpens motion

### 5.4 State Visualization
Represent internal state without exposing raw logs:
- current cluster name appears as a floating label
- phase name appears softly: "phase: drift", "phase: pulse", "phase: rupture"
- transition countdown shown as atmospheric timer, not plain integer text

### 5.5 Interaction
Allow the user to:
- hover active nodes to see source / tags / duration
- click a node to inspect metadata
- optionally pin a node as an anchor or seed
- optionally drag a bias vector into the field

---

## 6. Poem Field Redesign

### 6.1 Principle
The poem should not appear as a plain text dump.
It should feel like it is being born from the system.

### 6.2 Remove Log-Like Presentation
Avoid:
- dense multiline block with rigid timestamps
- ordinary textbox visuals
- hard white borders

### 6.3 Poem Presentation Model
The poem area should support:
- live line emergence
- fading memory
- soft hierarchy of recency

### 6.4 Rendering Behavior
Newest line:
- brightest
- sharpest
- may type in progressively

Recent lines:
- visible, slightly faded

Older lines:
- drift downward or fade into background
- optionally become ghost text

### 6.5 Timestamps
Do not place timestamps inline as the dominant visual element.
Options:
- small faint left gutter timestamps
- hover-to-reveal metadata
- optional debug overlay

### 6.6 Typography
Use more expressive typography.
Recommended directions:
- soft serif for lyrical feeling
- elegant italic for emergence
- or a restrained mono paired with soft opacity for machine-poetic ambiguity

Possible font directions:
- Spectral
- Cormorant
- IBM Plex Serif
- EB Garamond
- or an understated mono for secondary metadata only

### 6.7 Motion
Each new line can:
- type in gradually
- fade into place
- slightly drift by 1–4px over time
- pulse once when born

### 6.8 Optional Modes
Support multiple poem views:
- **Flow mode**: continuous emergence
- **Archive mode**: scrollable full history
- **Constellation mode**: poem fragments spatially arranged by theme or time

---

## 7. System Trace / Log Redesign

### 7.1 Problem
Raw logs currently dominate attention and flatten the atmosphere.

### 7.2 Solution
Split trace into two layers:

#### A. Whisper Layer (default visible)
Human-readable atmospheric status:
- submerged
- rupture building
- density holding
- pulse cluster active
- next transition nearing

#### B. Debug Layer (expandable)
Raw logs for engineering/debugging:
- hidden by default
- collapsible drawer
- monospaced
- searchable if needed

### 7.3 Behavior
The debug panel should not always occupy visible space.
Make it:
- collapsible bottom sheet
- side drawer
- modal inspector
- keyboard-toggle overlay

---

## 8. Button and Control Styling

### 8.1 Buttons
Replace default button look with:
- soft pill or capsule buttons
- low-contrast fill
- subtle glow on hover
- no harsh bevels

### 8.2 States
Buttons should visibly communicate:
- available
- active
- latched
- dangerous
- transitional

Example:
- Start Engine becomes a glowing active state indicator once running
- Stop Engine becomes visible but not visually dominant
- Collapse action gets warning styling but still elegant

### 8.3 Sliders / Continuous Inputs
Use custom styling:
- thicker tracks
- soft glow at thumb
- no default OS widget appearance
- animated fill response

---

## 9. Color System

### 9.1 Palette Direction
Base:
- black-blue
- deep navy
- midnight grey
- muted indigo

Accent families:
- cool cyan for stable flow
- pale gold for poem birth
- soft ember/red for rupture or collapse
- violet for drift
- mist white for metadata

### 9.2 Semantic Color Mapping
- submerged = blue-black / cool cyan
- drifting = violet / mist
- tension = amber to ember
- collapse = dim red / blackened glow
- stabilize = pale silver / cool white
- poem emergence = warm ivory / faint gold

### 9.3 Avoid
- saturated neon everywhere
- full white panel borders
- rainbow-by-default tag colors

---

## 10. Typography System

Use at least 3 text roles:

### 10.1 Atmospheric Headings
- bold or semi-bold
- minimal
- low count
- large enough to guide without boxing sections

### 10.2 Poem Text
- expressive, elegant, readable
- larger line spacing
- generous margins

### 10.3 Metadata / Debug
- smaller
- monospaced if needed
- reduced opacity
- never compete visually with poem text

---

## 11. Interaction Model

### 11.1 Primary Gestures
- hover = reveal context
- click = intervene
- drag = bias force
- hold = stronger intervention
- right click or long press = inspect source / tags / semantic neighborhood

### 11.2 Continuous Influence
Parameter changes should animate and ease over time.
Do not instantly jump all visuals.

### 11.3 State Change Language
Avoid technical-only labels.
Pair each control with poetic-readable language.

Example:
- Temperature → Heat
- Density → Saturation
- Tension → Strain
- Force State → Bias Toward
- Rare Silence → Invite Silence

---

## 12. Recommended Screen Structure (Practical)

### Top Bar
Contains:
- system title
- engine state
- mode selector
- library access
- debug toggle

### Left / Upper Influence Layer
Contains:
- state selector
- tension
- density
- heat
- phase duration / tempo scaling

### Center Drift Field
Contains:
- animated semantic / sound state field
- current cluster indicator
- active node motion
- interaction targets

### Right or Lower Poem Field
Contains:
- living poem display
- live emergence
- archive toggle
- cadence interval control

### Hidden / Expandable Trace Layer
Contains:
- raw logs
- engine internals
- event history
- diagnostics

---

## 13. MVP Redesign Priorities

If rebuilding incrementally, do this in order:

### Priority 1
Restyle the whole UI:
- remove borders
- improve spacing
- new typography
- better buttons
- unified color palette

### Priority 2
Redesign poem display:
- fade old lines
- highlight new line
- remove dominant timestamps
- use expressive typography

### Priority 3
Implement drift field visualization:
- particles or semantic node motion
- state label
- transition trails

### Priority 4
Replace sliders with custom-styled semantic controls

### Priority 5
Move logs into collapsible debug drawer and add whisper summary

---

## 14. Technical Recommendations

### If using Python GUI
Preferred:
- PySide6 / Qt Quick (QML) for animation + custom rendering

Possible:
- PyQt + custom paint widgets
- DearPyGui for prototyping
- pygame only for experimental visual layer, not full app structure

### If rebuilding as web UI
Preferred:
- React + Framer Motion + Tailwind
- Tauri for desktop shell
- Canvas/WebGL layer for drift field

### Rendering Notes
Use:
- opacity animation
- blur
- gradient layers
- animated transforms
- lightweight particle system

---

## 15. Success Criteria

The redesign succeeds when:
- the interface feels like an instrument, not an admin console
- the poem feels alive
- the user can sense system state before reading raw text
- the drift field makes semantic movement visible
- controls feel like influence, not command
- the whole application feels shapeless, continuous, and atmospheric

---

## 16. Future Extensions

Possible later additions:
- gesture-based control
- audio-reactive UI surfaces
- semantic zoom into clip/tag neighborhoods
- timeline replay of state evolution
- multiple visual skins by engine state
- record "sessions" as performable UI compositions