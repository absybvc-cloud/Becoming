# External Audio Input Integration: Sound Card Interface

## Becoming Engine: Live Environment Interaction Module

## 1. Purpose

Integrate external audio (sound card input) into the Becoming system.

Enable:

- Real-time environmental influence
- Live audio transformation
- Recording and ingestion into library

## 2. Input Pipeline

```text
Sound Card Input
  -> Audio Buffer
  -> Feature Extraction
  -> Control Mapping
  -> Runtime Engine
```

## 3. Audio Input Module

Use:

- `sounddevice` (Python)

### Implementation

```python
stream = sd.InputStream(
    channels=2,
    samplerate=44100,
    callback=audio_callback,
)
```

## 4. Feature Extraction

Extract per frame:

```python
features = {
    "amplitude": float,
    "spectral_centroid": float,
    "noise_level": float,
    "onset_density": float,
}
```

## 5. Mapping to Control

### Behavior Mapping

```text
heat        = amplitude
strain      = noise_level
saturation  = spectral_centroid
```

### Optional Audio Mapping

```text
reverb      = amplitude
distortion  = noise_level
```

## 6. Live Layer Injection (Optional)

Create dynamic layer:

```python
live_layer = {
    "role": "texture",
    "source": "mic",
    "processing": ["granular", "delay"],
}
```

## 7. Live Sampling

### Buffer

Maintain rolling buffer:

```python
buffer = last_10_seconds_audio
```

### Slice

Every `N` seconds:

```python
slice_audio(buffer)
```

### Ingest

`slice -> save -> auto-tag -> staging_queue`

## 8. Integration Rules

- Never block runtime loop
- Run audio input in separate thread
- Use shared `control_state`
- Smooth all features

## 9. Safety

- Clamp values (`0-1`)
- Handle no-input gracefully
- Fallback to neutral state

## 10. Minimal Implementation Plan

1. Add audio input stream
2. Extract features
3. Map to `behavior_control`
4. Add smoothing
5. Test real-time influence
6. Add live sampling (optional)

## 11. Success Criteria

- System reacts to environment sound
- Speech/noise changes behavior
- No latency spikes
- Stable over long runtime

## 12. Final Definition

This module turns Becoming into a system that listens to its environment and transforms with it.

## 13. One-Line Summary

Build a live audio interface that feeds the world into the system.