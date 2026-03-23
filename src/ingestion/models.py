from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator

from .enums import (
    SourceName, CandidateStatus, ApprovalStatus,
    TagType, ReviewActionType,
)


class SourceSearchRequest(BaseModel):
    query: str
    source_name: str
    limit: int
    filters: dict[str, Any] = {}
    page: int = 1
    created_at: Optional[datetime] = None

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must be non-empty")
        return v

    @field_validator("source_name")
    @classmethod
    def valid_source(cls, v: str) -> str:
        SourceName(v)
        return v

    @field_validator("limit")
    @classmethod
    def limit_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("limit must be > 0")
        return v


class SourceSearchResult(BaseModel):
    source_name: str
    source_item_id: str
    source_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    creator: Optional[str] = None
    license: Optional[str] = None
    attribution_required: Optional[bool] = None
    commercial_use_allowed: Optional[bool] = None
    derivative_use_allowed: Optional[bool] = None
    duration_seconds: Optional[float] = None
    original_format: Optional[str] = None
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    source_tags: list[str] = []
    raw_metadata: dict[str, Any]


class CandidateItemModel(BaseModel):
    ingestion_job_id: int
    source_name: str
    source_item_id: str
    source_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    creator: Optional[str] = None
    license: Optional[str] = None
    attribution_required: Optional[bool] = None
    commercial_use_allowed: Optional[bool] = None
    derivative_use_allowed: Optional[bool] = None
    duration_seconds: Optional[float] = None
    original_format: Optional[str] = None
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    source_tags: list[str] = []
    raw_metadata: dict[str, Any]
    candidate_score: Optional[float] = None
    candidate_status: str = CandidateStatus.discovered.value

    @field_validator("candidate_status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        CandidateStatus(v)
        return v


class AudioAssetModel(BaseModel):
    candidate_item_id: int
    local_id: str
    checksum_sha256: str
    raw_file_path: str
    normalized_file_path: str
    waveform_path: Optional[str] = None
    spectrogram_path: Optional[str] = None
    sample_rate: int
    channels: int
    duration_seconds: float
    loudness_lufs: Optional[float] = None
    peak_db: Optional[float] = None
    silence_ratio: Optional[float] = None
    rms: Optional[float] = None
    clipping_ratio: Optional[float] = None
    quality_score: Optional[float] = None
    world_fit_score: Optional[float] = None
    pulse_fit_score: Optional[float] = None
    drift_fit_score: Optional[float] = None
    approval_status: str = ApprovalStatus.pending_review.value
    rejection_reason: Optional[str] = None

    @field_validator("approval_status")
    @classmethod
    def valid_approval(cls, v: str) -> str:
        ApprovalStatus(v)
        return v

    @field_validator("sample_rate")
    @classmethod
    def sr_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("sample_rate must be > 0")
        return v

    @field_validator("channels")
    @classmethod
    def channels_valid(cls, v: int) -> int:
        if v not in (1, 2):
            raise ValueError("channels must be 1 or 2")
        return v

    @field_validator("duration_seconds")
    @classmethod
    def duration_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("duration_seconds must be > 0")
        return v


class TagPredictionModel(BaseModel):
    tag_text: str
    tag_type: str
    confidence: Optional[float] = None
    source_method: str

    @field_validator("tag_text")
    @classmethod
    def tag_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("tag_text must be non-empty")
        return v

    @field_validator("tag_type")
    @classmethod
    def valid_tag_type(cls, v: str) -> str:
        TagType(v)
        return v


class EmbeddingResultModel(BaseModel):
    asset_id: int
    embedding_model: str
    embedding_dim: int
    embedding_path: str

    @field_validator("embedding_dim")
    @classmethod
    def dim_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("embedding_dim must be > 0")
        return v


class ReviewActionModel(BaseModel):
    asset_id: int
    action_type: str
    reviewer: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("action_type")
    @classmethod
    def valid_action(cls, v: str) -> str:
        ReviewActionType(v)
        return v


class PipelineConfigModel(BaseModel):
    database_url: str = "library/becoming.db"
    raw_dir: str = "library/audio_raw"
    normalized_dir: str = "library/audio_normalized"
    embeddings_dir: str = "library/embeddings"
    spectrogram_dir: str = "library/spectrograms"
    waveform_dir: str = "library/waveforms"
    rejected_dir: str = "library/rejected"
    target_sample_rate: int = 44100
    target_channels: int = 2
    target_format: str = "wav"
    default_limit: int = 50
    min_duration_sec: float = 3.0
    max_duration_sec: float = 300.0
    allowed_sources: list[str] = ["freesound", "internet_archive", "wikimedia"]
    max_silence_ratio: float = 0.6
    min_rms: float = 0.01
    clipping_threshold: float = 0.99
    min_world_fit_score: float = 0.2
    duplicate_similarity_threshold: float = 0.95
    review_required: bool = True
    use_panns: bool = False
    use_clap: bool = False
