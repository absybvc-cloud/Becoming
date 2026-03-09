# System Architecture

## Modules

AudioLibraryManager  
Loads audio fragments and metadata.

PlaybackEngine  
Handles audio playback and mixing.

Scheduler  
Controls when fragments start and stop.

StateEngine  
Controls system mood and sound categories.

MutationEngine  
Introduces structural changes.

MemorySystem  
Prevents repetition.

## Runtime Flow

1. load library
2. initialize state
3. start scheduler loop
4. generate sound layers
5. update ecosystem