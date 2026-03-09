# Review Tool Specification
## Becoming Audio Library Review Tool
Version: 0.2

This document defines the functional and technical requirements for a local audio review tool used to listen to collected sounds and assign curation metadata.

The tool is designed to work with the output of the audio ingestion pipeline.

---

# 1. Goal

The review tool must allow a user to:

- load collected audio assets
- play audio locally
- inspect metadata
- assign review decisions
- assign role tags
- assign custom tags
- store results in database or manifest

---

# 2. Input Data Sources

The review tool must support two input sources.

## Option A: SQLite Database

Preferred input source.

Load assets from the `audio_assets` table.

Default filter:


approval_status = "pending_review"


## Option B: manifest.json

Fallback if database is not available.

Load list of assets from `manifest.json`.

Each record must include:

- asset_id or local_id
- normalized_file_path
- source_name
- duration
- tags

---

# 3. Asset Fields Required for Review

Each asset object must contain the following fields.

Required:


asset_id
local_id
normalized_file_path
duration_seconds
source_name


Optional but recommended:


title
source_tags
model_tags
world_fit_score
pulse_fit_score
drift_fit_score
approval_status


---

# 4. Review Decision Types

The tool must support the following decisions.


keep
maybe
reject
skip


Meaning:

| Decision | Result |
|--------|--------|
| keep | asset is approved for curated library |
| maybe | asset remains pending for later review |
| reject | asset marked unusable |
| skip | no change |

---

# 5. Role Assignment

Each asset may optionally receive a role tag.

Allowed roles:


pulse
drift
both
event
none


Definitions:

| Role | Usage |
|-----|------|
| pulse | rhythmic layer |
| drift | ambient layer |
| both | usable in both contexts |
| event | rare event sound |
| none | no role assigned |

---

# 6. Becoming Tags

The tool must allow arbitrary tag assignment.

Example tags:


metallic
organic
machine
foggy
urban
night
industrial
drone
ambient
harsh
soft
wide
lofi
electric
granular


Tags must be stored as:


list[str]


---

# 7. Metadata Display

Before playback the tool should print metadata.

Example output:


Asset: freesound_123456_ab12cd34
Source: freesound
Duration: 14.2s
Path: library/audio_normalized/freesound_123456_ab12cd34.wav
Source tags: drone, ambience
Model tags: machinery, hum
World fit: 0.74
Pulse fit: 0.41
Drift fit: 0.88
Status: pending_review


---

# 8. Playback

The review tool must support local playback of normalized audio.

### MVP Playback Method

Use system audio player.

macOS:


afplay <path>


Linux:


aplay <path>


Fallback:

Use `pydub` playback.

---

# 9. Review Interaction Flow

The review loop should follow this order.


1 load next asset
2 print metadata
3 play audio
4 prompt for decision
5 prompt for role
6 prompt for tags
7 prompt for notes
8 save result
9 move to next asset


Example terminal interaction:


Decision? [k]eep [m]aybe [r]eject [s]kip [q]uit
Role? [p]ulse [d]rift [b]oth [e]vent [n]one
Tags?

metallic foggy night
Notes?
good drift bed


---

# 10. Data Persistence

Review results must be written back to storage.

## If using SQLite

Update fields:


audio_assets.approval_status
audio_assets.updated_at


Insert review history row:


review_actions


Insert tags:


tags
asset_tags


## If using manifest

Update fields in record:


review_decision
role
becoming_tags
review_notes
reviewed_at


Output file:


reviewed_manifest.json


---

# 11. Curated Library Promotion

When decision = keep the tool should optionally promote the asset.

Recommended folder layout:


library/curated/keep/pulse/
library/curated/keep/drift/
library/curated/keep/both/
library/curated/keep/event/
library/curated/maybe/
library/curated/reject/


Promotion methods:

Preferred:


create symbolic link


Fallback:


copy file


---

# 12. CLI Interface

Basic command:


python review.py


Optional filters:


python review.py --status pending_review
python review.py --source freesound
python review.py --limit 20


Optional ordering:


--order random
--order world_fit
--order newest


Default ordering:


random


---

# 13. Suggested Module Structure


review_tool/
review.py
player.py
loader.py
writer.py
filters.py
models.py


Responsibilities:

| File | Responsibility |
|-----|---------------|
| review.py | main loop |
| player.py | audio playback |
| loader.py | load assets |
| writer.py | persist review results |
| filters.py | filtering logic |
| models.py | review data models |

---

# 14. Data Models

Example asset model:


class ReviewAsset:
asset_id: str
local_id: str
source_name: str
duration_seconds: float
normalized_file_path: str
source_tags: list[str]
model_tags: list[str]
world_fit_score: float | None
pulse_fit_score: float | None
drift_fit_score: float | None
approval_status: str | None


Example review record:


class ReviewRecord:
asset_id: str
decision: str
role: str
becoming_tags: list[str]
notes: str | None
reviewed_at: str


---

# 15. Error Handling

The tool must handle:

- missing audio file
- playback failure
- invalid metadata
- database connection failure
- malformed manifest

On error:


log error
skip asset
continue loop


---

# 16. Definition of Done

The review tool is complete when it can:

- load assets
- play audio
- collect decisions
- collect role tags
- collect custom tags
- store results
- optionally promote curated assets