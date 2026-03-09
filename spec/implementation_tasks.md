# Implementation Tasks
## For Becoming Audio Ingestion Engine
### Version 0.1

This document breaks the repository into concrete implementation tasks that can be executed by a coding agent.

The goal is to minimize ambiguity and allow sequential development.

---

# 1. General Instructions

Build the repository incrementally.

Priorities:

1. correctness
2. observability
3. maintainability
4. extensibility

For MVP:
- prefer simple implementations
- avoid premature optimization
- keep modules small
- write tests for critical paths

---

# 2. Milestone Overview

## Milestone 1
Repository skeleton + config + DB

## Milestone 2
Freesound search adapter

## Milestone 3
Download + normalization pipeline

## Milestone 4
Tagging + ontology mapping

## Milestone 5
Embeddings + scoring

## Milestone 6
Review workflow + CLI completion

## Milestone 7
Internet Archive adapter

---

# 3. Task Group A — Repository Bootstrap

## A1. Create folder structure

Create:

- src/
- tests/
- data/
- library/

Subfolders according to repo spec.

Deliverable:
- all directories exist
- imports resolve

## A2. Create requirements.txt

Add core dependencies:

- requests
- pydantic
- sqlalchemy
- pyyaml
- python-dotenv
- typer
- tqdm
- librosa
- soundfile
- numpy
- scipy

Add comments or optional section for:
- torch
- CLAP
- PANNs

Deliverable:
- dependencies install cleanly

## A3. Create config loading

Implement:
- `.env` loader
- `config.yaml` loader
- validated config object via Pydantic

Files:
- `src/utils/config.py`

Deliverable:
- config loads from disk
- secrets load from env

---

# 4. Task Group B — Database Layer

## B1. Create DB connection module

File:
- `src/db/connection.py`

Implement:
- SQLite engine creation
- session factory
- helper for session scope

Deliverable:
- app can open DB session

## B2. Create ORM models

File:
- `src/db/schema.py`

Implement ORM models for:
- Source
- IngestionJob
- CandidateItem
- AudioAsset
- Tag
- AssetTag
- Embedding
- AnalysisFeature
- ReviewAction

Deliverable:
- schema matches spec

## B3. Create init-db command

Files:
- `src/cli/commands.py`
- `src/main.py`

Implement:
- `init-db` CLI command
- create tables
- optionally seed sources table

Deliverable:
- running init-db creates schema

## B4. Create repository helpers

File:
- `src/db/repositories.py`

Implement helpers for:
- create ingestion job
- upsert candidate item
- create audio asset
- add tags
- list pending review
- update approval status

Deliverable:
- reusable DB access layer

---

# 5. Task Group C — Core Domain Models

## C1. Create Pydantic models

Files:
- `src/models/domain_models.py` or similar

Implement:
- SourceSearchRequest
- SourceSearchResult
- CandidateItemModel
- AudioAssetModel
- TagPredictionModel
- EmbeddingResultModel
- ReviewActionModel
- PipelineConfigModel

Deliverable:
- validated transport models for all pipeline stages

## C2. Create enums

Implement enums for:
- SourceName
- JobStatus
- CandidateStatus
- ApprovalStatus
- TagType
- ReviewActionType

Deliverable:
- all statuses centralized

---

# 6. Task Group D — Utilities

## D1. Logging utility

File:
- `src/utils/logging.py`

Implement:
- structured logger
- per-module logger names
- log file output in `data/logs/`

Deliverable:
- consistent logs for pipelines

## D2. Hashing utility

File:
- `src/utils/hashing.py`

Implement:
- sha256 for files
- short hash helper for IDs

Deliverable:
- checksum generation

## D3. Validation helpers

File:
- `src/utils/validation.py`

Implement:
- file exists
- URL looks valid
- duration range checks
- score range checks

Deliverable:
- reusable validation helpers

## D4. Time helper

File:
- `src/utils/time.py`

Implement:
- UTC now as ISO 8601 string

Deliverable:
- timestamp consistency

---

# 7. Task Group E — Storage Layer

## E1. Path builder

File:
- `src/storage/path_builder.py`

Implement functions to create stable paths for:
- raw audio
- normalized audio
- embeddings
- waveforms
- spectrograms
- rejected audio

Deliverable:
- deterministic relative paths

## E2. File store

File:
- `src/storage/file_store.py`

Implement:
- ensure directories exist
- copy/move file
- save bytes to path
- safe overwrite handling

Deliverable:
- centralized filesystem logic

---

# 8. Task Group F — Adapter Base

## F1. Create adapter base class

File:
- `src/adapters/base.py`

Implement abstract methods:
- search()
- fetch_metadata()
- download()
- normalize_metadata()

Deliverable:
- standard adapter contract

---

# 9. Task Group G — Freesound Adapter

## G1. Implement Freesound API client

File:
- `src/adapters/freesound_adapter.py`

Implement:
- auth header handling
- search request
- result parsing
- metadata normalization
- download or preview fetch logic as supported by chosen API path

Deliverable:
- returns `SourceSearchResult` items

## G2. Freesound metadata normalization

Normalize:
- source item id
- title
- description
- creator
- license
- tags
- duration
- preview URL / download URL if available

Deliverable:
- adapter outputs consistent result objects

## G3. Freesound search tests

File:
- `tests/test_adapters.py`

Test:
- search returns normalized objects
- required fields are present

Deliverable:
- passing adapter test

---

# 10. Task Group H — Search Pipeline

## H1. Implement search pipeline service

File:
- `src/pipeline/search_pipeline.py`

Responsibilities:
- create ingestion job
- call adapter search
- score candidates with initial heuristic
- save candidate items to DB

Deliverable:
- search command writes candidate rows

## H2. Implement initial candidate scoring

Heuristic inputs:
- metadata completeness
- duration in preferred range
- license presence
- tag overlap with query tokens

Deliverable:
- numeric candidate_score

---

# 11. Task Group I — Download Pipeline

## I1. Implement download pipeline

File:
- `src/pipeline/download_pipeline.py`

Responsibilities:
- select discovered candidates
- download audio files
- save raw file
- compute checksum
- update candidate status

Deliverable:
- raw files appear in `library/audio_raw/...`

## I2. Add failure handling

Handle:
- network errors
- missing URL
- zero-byte file
- duplicate checksum

Deliverable:
- failures logged without crashing whole batch

---

# 12. Task Group J — Audio Conversion and Analysis

## J1. Implement conversion utilities

File:
- `src/audio/conversion.py`

Implement:
- normalize audio to wav mono target sample rate
- wrapper around ffmpeg or soundfile/librosa pipeline

Deliverable:
- raw file converts successfully

## J2. Implement analysis utilities

File:
- `src/audio/analysis.py`

Implement:
- duration
- RMS
- peak dB
- silence ratio
- spectral centroid mean
- bandwidth mean
- zero crossing rate mean
- optional tempo estimate

Deliverable:
- metrics computed for normalized file

## J3. Save waveform and spectrogram images

Implement:
- waveform preview PNG
- spectrogram preview PNG

Deliverable:
- artifacts saved in library folders

---

# 13. Task Group K — Normalize Pipeline

## K1. Implement normalize pipeline

File:
- `src/pipeline/normalize_pipeline.py`

Responsibilities:
- select downloaded candidates
- convert to normalized audio
- compute analysis metrics
- create audio asset row
- update candidate status to analyzed

Deliverable:
- normalized wav + DB asset row

## K2. Add auto-reject checks

Reject or flag if:
- too short
- too long
- too silent
- unreadable
- corrupted

Deliverable:
- basic quality gate

---

# 14. Task Group L — Ontology and Tag Mapping

## L1. Create ontology loader

Files:
- `src/metadata/ontology.py`
- `data/ontology/...`

Implement:
- load ontology mapping file
- expose simple lookup helpers

Deliverable:
- ontology tags accessible

## L2. Create tag mapper

File:
- `src/metadata/tag_mapper.py`

Implement:
- normalize source tags
- lowercase / deduplicate
- map common terms to ontology tags

Deliverable:
- source tags become normalized tags

---

# 15. Task Group M — PANNs Tagger

## M1. Implement model wrapper

File:
- `src/models/panns_tagger.py`

Responsibilities:
- load pretrained model once
- run inference on normalized audio
- return clip-level tag predictions with confidence

Deliverable:
- list of `TagPredictionModel`

## M2. Implement tagging pipeline

File:
- `src/pipeline/tagging_pipeline.py`

Responsibilities:
- run source tag normalization
- run PANNs tagger
- write tags to `tags` and `asset_tags`

Deliverable:
- analyzed assets gain source/model/ontology tags

---

# 16. Task Group N — CLAP Embeddings

## N1. Implement CLAP embedder wrapper

File:
- `src/models/clap_embedder.py`

Responsibilities:
- load model
- generate audio embedding
- optionally generate text embeddings for prompt bank

Deliverable:
- `.npy` embedding files saved

## N2. Implement embedding pipeline

File:
- `src/pipeline/embedding_pipeline.py`

Responsibilities:
- generate embedding for each asset
- save vector to disk
- write embedding record to DB

Deliverable:
- embeddings table populated

---

# 17. Task Group O — Prompt Bank and Scoring

## O1. Create Becoming prompt bank

Files:
- `src/metadata/prompts.py`
- `data/prompts/becoming_prompts.yaml`

Implement loading for prompts:
- pulse
- drift
- becoming

Deliverable:
- prompt groups available in code

## O2. Implement scoring pipeline

File:
- `src/pipeline/scoring_pipeline.py`

Compute:
- quality_score
- pulse_fit_score
- drift_fit_score
- world_fit_score

Suggested inputs:
- audio features
- source tags
- model tags
- CLAP similarity to prompts

Deliverable:
- score fields written to DB

## O3. Add duplicate similarity check

Use:
- checksum exact match
- embedding cosine similarity for near duplicates

Deliverable:
- duplicate candidates flagged

---

# 18. Task Group P — Review Workflow

## P1. Implement review-list command

List assets with:
- pending_review status
- scores
- top tags
- file paths

Deliverable:
- curation queue view in terminal

## P2. Implement approve command

Actions:
- set approval_status = approved
- create review_action row

Deliverable:
- asset can be promoted

## P3. Implement reject command

Actions:
- set approval_status = rejected
- store rejection reason
- create review_action row

Deliverable:
- rejected assets tracked

## P4. Optional retag/rescore commands

Later addition.

---

# 19. Task Group Q — CLI Commands

## Q1. Build CLI entrypoint

Use `typer`.

Commands:
- init-db
- search
- download
- normalize
- tag
- embed
- score
- review-list
- approve
- reject
- pipeline

Deliverable:
- all commands callable via `python -m src.main`

## Q2. Implement pipeline command

Run sequence:
- search
- download
- normalize
- tag
- embed
- score

Deliverable:
- single command executes full MVP flow

---

# 20. Task Group R — Tests

## R1. DB tests

Test:
- schema creation
- insert / fetch roundtrip
- unique constraints

## R2. Adapter tests

Test:
- normalized result shape
- required metadata fields

## R3. Audio tests

Test:
- conversion succeeds
- analysis metrics computed

## R4. Pipeline smoke test

Test:
- small query
- 1–3 files
- full pipeline without crash

Deliverable:
- basic confidence in end-to-end flow

---

# 21. Task Group S — Documentation

## S1. Write README

Include:
- setup
- env vars
- CLI examples
- source policy
- model requirements

## S2. Write developer notes

Document:
- module boundaries
- known limitations
- future roadmap

---

# 22. Definition of Done for MVP

MVP is complete when all of the following are true:

1. `init-db` creates working SQLite schema
2. Freesound search stores candidate items
3. download pipeline fetches raw audio
4. normalize pipeline creates standard wav files
5. tagging pipeline writes source + model tags
6. embedding pipeline saves CLAP embeddings
7. scoring pipeline computes world-fit scores
8. review commands approve/reject assets
9. full pipeline command works on a sample query
10. provenance and license metadata are preserved

---

# 23. Suggested Build Order for Code Agent

Strict recommended order:

1. bootstrap repo
2. config loader
3. DB schema
4. CLI init-db
5. Freesound adapter
6. search pipeline
7. download pipeline
8. conversion + analysis
9. normalize pipeline
10. ontology + tag mapper
11. PANNs wrapper
12. tagging pipeline
13. CLAP wrapper
14. embedding pipeline
15. prompt bank
16. scoring pipeline
17. review commands
18. tests
19. README

Do not start with CLAP or PANNs before search/download/normalize are working.

---

# 24. Final Note

This repository should be built as an ingestion and semantic indexing engine, not as an indiscriminate scraper.

The objective is not maximum quantity of sounds.

The objective is to construct a traceable, searchable, and artistically usable sound ecology for Becoming.