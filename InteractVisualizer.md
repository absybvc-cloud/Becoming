# Interact Visualizer — Real-Time Perception Feedback UI

**Becoming Engine — Gesture + Expression Debug Interface**

---

## 1. Purpose

Create a real-time visualization panel that shows:

- What the system detects from camera input
- How those signals are mapped to control parameters
- What effects are applied to the engine

This UI must:

- Update at 30–60 FPS
- Be low-latency
- Be visually intuitive
- Be tightly integrated with existing INTERACT toggle

---

## 2. Placement

Add a floating panel:

- **Position:** right side overlay OR bottom-right floating window
- **Visibility:** only when camera is ON

---

## 3. Layout

### 3.1 Camera View

Display:

- Live webcam feed
- Overlay landmarks (face mesh + hand skeleton)

### 3.2 Face Signals Panel

Show real-time values:

```
FACE

mouth_openness   [||||||||----] 0.62
eye_openness     [|||||-------] 0.41
head_tilt        [||||--------] 0.35
```

### 3.3 Hand Signals Panel

```
HANDS

hand_y           [|||||||-----] 0.55
hand_distance    [||||||||----] 0.68
hand_velocity    [|||---------] 0.22
finger_spread    [||||||------] 0.47
```

---

## 4. Mapping Visualization (CRITICAL)

Show how signals map to parameters.

### Flow Representation

```
mouth_openness → strain  → 0.62
hand_y         → lowpass → 0.55
hand_distance  → reverb  → 0.68
hand_velocity  → heat    → 0.22
```

### UI Format

```
[INPUT]   → [PARAM]    → [VALUE]

mouth     → strain     → 0.62
hand_y    → lowpass    → 0.55
velocity  → heat       → 0.22
```

---

## 5. Effect Output Panel

Display final engine values.

### Audio

```
AUDIO

gain        [|||||||-----]
lowpass     [||||||------]
reverb      [||||||||----]
distortion  [||----------]
spread      [||||--------]
```

### Behavior

```
BEHAVIOR

strain      [||||||||----]
saturation  [|||||-------]
heat        [|||---------]
time_scale  [||||--------]
```

---

## 6. Visual Feedback Enhancements

### 6.1 Highlight Active Signals

If value changes rapidly:

- Flash or glow
- Color shift

### 6.2 Dominant Control Indicator

Show which input is currently strongest:

```
ACTIVE DRIVER: hand_distance → reverb
```

### 6.3 Threshold Markers

Add markers:

- Low / mid / high zones

---

## 7. Smoothing Display

Show both:

- `raw_value`
- `smoothed_value`

Optional toggle:

- Show/hide raw

---

## 8. Interaction Modes

### Mode 1: Debug

- Show all values
- Show raw + smoothed
- Show mapping

### Mode 2: Minimal

- Only show bars
- No numbers

---

## 9. Integration with Engine

### Data Source

Visualizer reads from:

```python
control_state = {
    "features": {...},
    "audio": {...},
    "behavior": {...},
}
```

### Update Loop

- Subscribe to perception thread
- Update UI every frame

---

## 10. Performance Constraints

- Must not block runtime
- Must not block perception thread
- Use async UI update

---

## 11. Optional Extensions

### 11.1 Gesture Recognition Labels

```
gesture: "open hand"
gesture: "fast motion"
```

### 11.2 Heat Map Overlay

- Show areas of movement intensity

### 11.3 History Trail

- Last 5 seconds movement graph

---

## 12. Minimal Implementation Plan

1. Add visualizer panel
2. Connect camera feed
3. Display feature values
4. Add mapping display
5. Add effect output bars
6. Add highlight logic

---

## 13. Success Criteria

- User can see their movement reflected instantly
- Mapping is understandable
- Cause-effect is visible
- Interaction feels controllable

---

## 14. Final Definition

> This UI makes Becoming interpretable as a responsive system.

---

## 15. One-Line Summary

> A real-time visual bridge between body movement and sound transformation.