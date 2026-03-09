# Schema and Data Models
## For Becoming Audio Ingestion Engine
### Version 0.1

This document defines the database schema, Python data models, enums, and validation rules for the audio ingestion and semantic indexing system.

The goal is to make storage and model design unambiguous for implementation.

---

# 1. Design Principles

The schema must support:

- source provenance tracking
- candidate discovery before approval
- normalized audio storage
- multi-layer tagging
- embedding storage
- review workflow
- quality and world-fit scoring

The schema should prefer:

- explicit status fields
- append-only review history
- filesystem paths stored in DB
- normalized tags via many-to-many mappings

Use SQLite for MVP.

---

# 2. Core Entities

The main entities are:

1. Source
2. IngestionJob
3. CandidateItem
4. AudioAsset
5. Tag
6. AssetTag
7. Embedding
8. AnalysisFeature
9. ReviewAction

---

# 3. Enums

## 3.1 SourceName

Allowed values:

- freesound
- internet_archive
- wikimedia

---

## 3.2 JobStatus

Allowed values:

- pending
- running
- completed
- failed

---

## 3.3 CandidateStatus

Allowed values:

- discovered
- filtered_out
- downloaded
- analyzed
- approved
- rejected

---

## 3.4 ApprovalStatus

Allowed values:

- pending_review
- approved
- rejected
- archived

---

## 3.5 TagType

Allowed values:

- source
- ontology
- model
- curator
- becoming

---

## 3.6 ReviewActionType

Allowed values:

- approve
- reject
- retag
- rescore
- mark_rare_event
- mark_pulse
- mark_drift

---

# 4. Database Tables

---

# 4.1 Table: sources

Purpose:
Store supported source systems.

Fields:

- `id` INTEGER PRIMARY KEY
- `name` TEXT NOT NULL UNIQUE
- `enabled` BOOLEAN NOT NULL DEFAULT 1
- `created_at` TEXT NOT NULL

Constraints:
- `name` must be one of SourceName values

Example rows:
- freesound
- internet_archive
- wikimedia

---

# 4.2 Table: ingestion_jobs

Purpose:
Track one search / ingestion request.

Fields:

- `id` INTEGER PRIMARY KEY
- `query_text` TEXT NOT NULL
- `source_name` TEXT NOT NULL
- `requested_limit` INTEGER NOT NULL
- `status` TEXT NOT NULL
- `notes` TEXT
- `created_at` TEXT NOT NULL
- `started_at` TEXT
- `finished_at` TEXT

Constraints:
- `status` must be one of JobStatus
- `requested_limit` must be > 0

Indexes:
- index on `source_name`
- index on `status`
- index on `created_at`

---

# 4.3 Table: candidate_items

Purpose:
Store source metadata before promotion into the local library.

Fields:

- `id` INTEGER PRIMARY KEY
- `ingestion_job_id` INTEGER NOT NULL
- `source_name` TEXT NOT NULL
- `source_item_id` TEXT NOT NULL
- `source_url` TEXT
- `title` TEXT
- `description` TEXT
- `creator` TEXT
- `license` TEXT
- `attribution_required` BOOLEAN
- `commercial_use_allowed` BOOLEAN
- `derivative_use_allowed` BOOLEAN
- `duration_seconds` REAL
- `original_format` TEXT
- `download_url` TEXT
- `preview_url` TEXT
- `source_tags_json` TEXT
- `raw_metadata_json` TEXT NOT NULL
- `candidate_score` REAL
- `candidate_status` TEXT NOT NULL
- `downloaded_at` TEXT
- `created_at` TEXT NOT NULL

Foreign keys:
- `ingestion_job_id` references `ingestion_jobs(id)`

Constraints:
- `candidate_status` must be one of CandidateStatus

Uniqueness:
- unique on (`source_name`, `source_item_id`)

Indexes:
- index on `ingestion_job_id`
- index on `candidate_status`
- index on `source_name`

---

# 4.4 Table: audio_assets

Purpose:
Store downloaded and normalized local audio assets.

Fields:

- `id` INTEGER PRIMARY KEY
- `candidate_item_id` INTEGER NOT NULL
- `local_id` TEXT NOT NULL UNIQUE
- `checksum_sha256` TEXT NOT NULL UNIQUE
- `raw_file_path` TEXT NOT NULL
- `normalized_file_path` TEXT NOT NULL
- `waveform_path` TEXT
- `spectrogram_path` TEXT
- `sample_rate` INTEGER NOT NULL
- `channels` INTEGER NOT NULL
- `duration_seconds` REAL NOT NULL
- `loudness_lufs` REAL
- `peak_db` REAL
- `silence_ratio` REAL
- `rms` REAL
- `clipping_ratio` REAL
- `quality_score` REAL
- `world_fit_score` REAL
- `pulse_fit_score` REAL
- `drift_fit_score` REAL
- `approval_status` TEXT NOT NULL
- `rejection_reason` TEXT
- `ingestion_timestamp` TEXT NOT NULL
- `created_at` TEXT NOT NULL
- `updated_at` TEXT NOT NULL

Foreign keys:
- `candidate_item_id` references `candidate_items(id)`

Constraints:
- `approval_status` must be one of ApprovalStatus
- `sample_rate` > 0
- `channels` in {1, 2}
- `duration_seconds` > 0
- score fields should be between 0.0 and 1.0 when present

Indexes:
- index on `approval_status`
- index on `world_fit_score`
- index on `candidate_item_id`

---

# 4.5 Table: tags

Purpose:
Store normalized tag vocabulary.

Fields:

- `id` INTEGER PRIMARY KEY
- `tag_text` TEXT NOT NULL
- `tag_type` TEXT NOT NULL
- `description` TEXT
- `created_at` TEXT NOT NULL

Constraints:
- `tag_type` must be one of TagType

Uniqueness:
- unique on (`tag_text`, `tag_type`)

Indexes:
- index on `tag_text`
- index on `tag_type`

---

# 4.6 Table: asset_tags

Purpose:
Map tags to audio assets with confidence and provenance.

Fields:

- `id` INTEGER PRIMARY KEY
- `asset_id` INTEGER NOT NULL
- `tag_id` INTEGER NOT NULL
- `confidence` REAL
- `source_method` TEXT NOT NULL
- `created_at` TEXT NOT NULL

Foreign keys:
- `asset_id` references `audio_assets(id)`
- `tag_id` references `tags(id)`

Constraints:
- `confidence` between 0.0 and 1.0 when present

Uniqueness:
- unique on (`asset_id`, `tag_id`, `source_method`)

Indexes:
- index on `asset_id`
- index on `tag_id`

---

# 4.7 Table: embeddings

Purpose:
Store embedding metadata and location.

Fields:

- `id` INTEGER PRIMARY KEY
- `asset_id` INTEGER NOT NULL
- `embedding_model` TEXT NOT NULL
- `embedding_dim` INTEGER NOT NULL
- `embedding_path` TEXT NOT NULL
- `created_at` TEXT NOT NULL

Foreign keys:
- `asset_id` references `audio_assets(id)`

Uniqueness:
- unique on (`asset_id`, `embedding_model`)

Indexes:
- index on `asset_id`
- index on `embedding_model`

---

# 4.8 Table: analysis_features

Purpose:
Store extracted numeric audio features.

Fields:

- `id` INTEGER PRIMARY KEY
- `asset_id` INTEGER NOT NULL
- `spectral_centroid_mean` REAL
- `spectral_bandwidth_mean` REAL
- `zero_crossing_rate_mean` REAL
- `tempo_estimate` REAL
- `tonal_confidence` REAL
- `speech_probability` REAL
- `music_probability` REAL
- `noise_probability` REAL
- `created_at` TEXT NOT NULL

Foreign keys:
- `asset_id` references `audio_assets(id)`

Uniqueness:
- unique on (`asset_id`)

Indexes:
- index on `asset_id`

---

# 4.9 Table: review_actions

Purpose:
Store human review history.

Fields:

- `id` INTEGER PRIMARY KEY
- `asset_id` INTEGER NOT NULL
- `action_type` TEXT NOT NULL
- `reviewer` TEXT
- `notes` TEXT
- `created_at` TEXT NOT NULL

Foreign keys:
- `asset_id` references `audio_assets(id)`

Constraints:
- `action_type` must be one of ReviewActionType

Indexes:
- index on `asset_id`
- index on `action_type`
- index on `created_at`

---

# 5. Python Domain Models

Use Pydantic models for validation and transport between modules.

---

# 5.1 SourceSearchRequest

Fields:

- `query: str`
- `source_name: str`
- `limit: int`
- `filters: dict[str, Any] = {}`
- `created_at: datetime | None`

Validation:
- query must be non-empty
- source_name must be a valid SourceName
- limit must be > 0

---

# 5.2 SourceSearchResult

Fields:

- `source_name: str`
- `source_item_id: str`
- `source_url: str | None`
- `title: str | None`
- `description: str | None`
- `creator: str | None`
- `license: str | None`
- `attribution_required: bool | None`
- `commercial_use_allowed: bool | None`
- `derivative_use_allowed: bool | None`
- `duration_seconds: float | None`
- `original_format: str | None`
- `download_url: str | None`
- `preview_url: str | None`
- `source_tags: list[str] = []`
- `raw_metadata: dict[str, Any]`

Validation:
- source_name required
- source_item_id required
- raw_metadata required

---

# 5.3 CandidateItemModel

Fields:

- `ingestion_job_id: int`
- `source_name: str`
- `source_item_id: str`
- `source_url: str | None`
- `title: str | None`
- `description: str | None`
- `creator: str | None`
- `license: str | None`
- `attribution_required: bool | None`
- `commercial_use_allowed: bool | None`
- `derivative_use_allowed: bool | None`
- `duration_seconds: float | None`
- `original_format: str | None`
- `download_url: str | None`
- `preview_url: str | None`
- `source_tags: list[str]`
- `raw_metadata: dict[str, Any]`
- `candidate_score: float | None`
- `candidate_status: str`

Validation:
- candidate_status must be CandidateStatus

---

# 5.4 AudioAssetModel

Fields:

- `candidate_item_id: int`
- `local_id: str`
- `checksum_sha256: str`
- `raw_file_path: str`
- `normalized_file_path: str`
- `waveform_path: str | None`
- `spectrogram_path: str | None`
- `sample_rate: int`
- `channels: int`
- `duration_seconds: float`
- `loudness_lufs: float | None`
- `peak_db: float | None`
- `silence_ratio: float | None`
- `rms: float | None`
- `clipping_ratio: float | None`
- `quality_score: float | None`
- `world_fit_score: float | None`
- `pulse_fit_score: float | None`
- `drift_fit_score: float | None`
- `approval_status: str`
- `rejection_reason: str | None`

Validation:
- approval_status must be ApprovalStatus
- local_id required
- checksum required

---

# 5.5 TagPredictionModel

Fields:

- `tag_text: str`
- `tag_type: str`
- `confidence: float | None`
- `source_method: str`

Validation:
- tag_type must be TagType
- tag_text must be non-empty

---

# 5.6 EmbeddingResultModel

Fields:

- `asset_id: int`
- `embedding_model: str`
- `embedding_dim: int`
- `embedding_path: str`

Validation:
- embedding_dim > 0

---

# 5.7 ReviewActionModel

Fields:

- `asset_id: int`
- `action_type: str`
- `reviewer: str | None`
- `notes: str | None`

Validation:
- action_type must be ReviewActionType

---

# 5.8 PipelineConfigModel

Fields:

- `database_url: str`
- `raw_dir: str`
- `normalized_dir: str`
- `embeddings_dir: str`
- `spectrogram_dir: str`
- `waveform_dir: str`
- `rejected_dir: str`
- `target_sample_rate: int`
- `target_channels: int`
- `target_format: str`
- `default_limit: int`
- `min_duration_sec: float`
- `max_duration_sec: float`
- `allowed_sources: list[str]`
- `max_silence_ratio: float`
- `min_rms: float`
- `clipping_threshold: float`
- `min_world_fit_score: float`
- `duplicate_similarity_threshold: float`
- `review_required: bool`
- `use_panns: bool`
- `use_clap: bool`

---

# 6. Validation Rules

## Required Global Rules

1. Every stored audio asset must link back to one candidate item.
2. Every candidate item must link back to one ingestion job.
3. Every audio asset must retain source provenance indirectly through candidate item.
4. No audio asset may be stored without checksum.
5. No approved audio asset may lack normalized file path.
6. Every embedding row must have an on-disk embedding file.
7. Review actions must never be deleted from history.

---

# 7. Local ID Generation Rule

Generate `local_id` deterministically:

Suggested pattern:

`{source_name}_{source_item_id}_{short_hash}`

Where:
- `short_hash` is first 8 characters of sha256 of source_name + source_item_id + checksum

Example:
- `freesound_123456_ab12cd34`

---

# 8. Timestamp Rules

All timestamps should be stored in ISO 8601 UTC strings.

Recommended fields:
- `created_at`
- `updated_at`
- `ingestion_timestamp`
- `downloaded_at`
- `started_at`
- `finished_at`

---

# 9. File Path Rules

All paths stored in DB should be relative project paths if possible.

Examples:
- `library/audio_raw/freesound/freesound_123456_ab12cd34.mp3`
- `library/audio_normalized/freesound/freesound_123456_ab12cd34.wav`
- `library/embeddings/clap/freesound_123456_ab12cd34.npy`

Avoid storing absolute machine-specific paths in DB.

---

# 10. Promotion Rule

An asset may be promoted into the main Becoming library only when:

- normalized file exists
- checksum exists
- quality score has been computed
- world-fit score has been computed
- approval_status = approved

---

# 11. Rejection Rule

If rejected, keep:

- source metadata
- checksums
- rejection reason
- review history

Rejected files may be moved to `library/rejected/`, but provenance must not be lost.

---

# 12. Final Intent

This schema is designed to preserve:

- legality
- provenance
- artistic curation
- semantic retrieval
- future extensibility

It is not only a storage schema.
It is the memory system of the Becoming sound ecology.