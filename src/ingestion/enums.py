from enum import Enum


class SourceName(str, Enum):
    freesound = "freesound"
    internet_archive = "internet_archive"
    wikimedia = "wikimedia"


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class CandidateStatus(str, Enum):
    discovered = "discovered"
    filtered_out = "filtered_out"
    downloaded = "downloaded"
    analyzed = "analyzed"
    approved = "approved"
    rejected = "rejected"


class ApprovalStatus(str, Enum):
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
    archived = "archived"


class TagType(str, Enum):
    source = "source"
    ontology = "ontology"
    model = "model"
    curator = "curator"
    becoming = "becoming"


class ReviewActionType(str, Enum):
    approve = "approve"
    reject = "reject"
    retag = "retag"
    rescore = "rescore"
    mark_rare_event = "mark_rare_event"
    mark_pulse = "mark_pulse"
    mark_drift = "mark_drift"
