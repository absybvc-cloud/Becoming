# Real-Time Interaction System — Camera + Gesture Control

**Becoming Engine — Embodied Control Layer**

---

## 1. Purpose

Enable real-time interaction between user and Becoming using:

- Facial expression
- Hand gestures
- Continuous parameter control

This system must:

- Be low latency
- Not interrupt runtime
- Modulate both audio and behavior layers

---

## 2. Architecture

```
Camera Input
      ↓
Perception Module
      ↓
Feature Extraction
      ↓
Control Mapping
      ↓
Shared Control State
      ↓
Runtime Engine
      ↓
Audio Backend
```

---

## 3. Control Layers

### 3.1 Audio Control (Fast)

```python
audio_control = {
    "master_gain": float,
    "lowpass": float,
    "highpass": float,
    "reverb": float,
    "distortion": float,
    "stereo_spread": float,
}
```

### 3.2 Behavior Control (Slow)

```python
behavior_control = {
    "strain": float,
    "saturation": float,
    "heat": float,
    "time_scale": float,
}
```

---

## 4. Perception Module

Use:

- MediaPipe Face Mesh
- MediaPipe Hands

### Extract Features

```python
features = {
    "mouth_openness": float,
    "eye_openness": float,
    "head_tilt": float,
    "hand_x": float,
    "hand_y": float,
    "hand_velocity": float,
    "hand_distance": float,
}
```

---

## 5. Mapping Functions

### Face → Behavior

```python
strain = mouth_openness
saturation = eye_openness
```

### Hands → Audio

```python
lowpass = hand_y
highpass = 1 - hand_y
reverb = hand_distance
```

### Motion → Heat

```python
heat = hand_velocity
```

---

## 6. Smoothing

Apply exponential smoothing:

```python
value = α * prev + (1 - α) * input
```

---

## 7. Runtime Integration

Runtime reads:

```python
control_state = {
    "audio": audio_control,
    "behavior": behavior_control,
}
```

### Apply to Engine

- `audio_control` → audio backend
- `behavior_control` → scheduler + drift + layer params

---

## 8. Audio Backend Integration

Must support:

```python
set_master_gain(value)
set_filter(lowpass, highpass)
set_reverb(amount)
set_distortion(amount)
```

---

## 9. Update Loop

Run at:

- 30–60 FPS perception loop

---

## 10. Safety

- Clamp all values (0–1)
- Fallback to default if no detection
- **NEVER** block runtime loop

---

## 11. Minimal Implementation Plan

1. Integrate camera feed
2. Add MediaPipe detection
3. Extract features
4. Implement mapping
5. Add smoothing
6. Connect to `control_state`
7. Connect to runtime

---

## 12. Success Criteria

- System responds smoothly to movement
- No jitter or spikes
- Audio reacts instantly
- Behavior shifts gradually
- Interaction feels continuous

---

## 13. Final Definition

> This module transforms Becoming into a system that can be shaped by human presence.

---

## 14. One-Line Summary

> A real-time embodied interface where movement becomes sound.