# Scheduler

The scheduler controls fragment playback.

## Responsibilities

- manage active layers
- maintain density targets
- schedule new fragments
- stop fragments when expired

## Scheduler Loop

every second:

check layer availability

if layer available:
    select fragment
    start playback