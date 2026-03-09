from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReviewAsset:
    asset_id: int
    local_id: str
    source_name: str
    duration_seconds: float
    normalized_file_path: str
    source_tags: list[str] = field(default_factory=list)
    model_tags: list[str] = field(default_factory=list)
    world_fit_score: Optional[float] = None
    pulse_fit_score: Optional[float] = None
    drift_fit_score: Optional[float] = None
    quality_score: Optional[float] = None
    approval_status: Optional[str] = None
    title: Optional[str] = None
    creator: Optional[str] = None
    silence_ratio: Optional[float] = None
    rms: Optional[float] = None


@dataclass
class ReviewRecord:
    asset_id: int
    decision: str          # keep | maybe | reject | skip
    role: str              # pulse | drift | both | event | none
    becoming_tags: list[str] = field(default_factory=list)
    notes: str = ""
    reviewed_at: str = ""
