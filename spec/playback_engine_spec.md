# Playback Engine

Handles audio playback.

## Requirements

- play multiple audio fragments simultaneously
- crossfade transitions
- gain control
- stereo output

## Recommended Libraries

sounddevice  
numpy  
librosa

## Basic API

play(fragment)

stop(fragment)

crossfade(fragmentA, fragmentB)