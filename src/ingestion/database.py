import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .enums import (
    SourceName, JobStatus, CandidateStatus,
    ApprovalStatus, TagType, ReviewActionType,
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    enabled    BOOLEAN NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id              INTEGER PRIMARY KEY,
    query_text      TEXT NOT NULL,
    source_name     TEXT NOT NULL,
    requested_limit INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    notes           TEXT,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_source  ON ingestion_jobs(source_name);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON ingestion_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON ingestion_jobs(created_at);

CREATE TABLE IF NOT EXISTS candidate_items (
    id                     INTEGER PRIMARY KEY,
    ingestion_job_id       INTEGER NOT NULL,
    source_name            TEXT NOT NULL,
    source_item_id         TEXT NOT NULL,
    source_url             TEXT,
    title                  TEXT,
    description            TEXT,
    creator                TEXT,
    license                TEXT,
    attribution_required   BOOLEAN,
    commercial_use_allowed BOOLEAN,
    derivative_use_allowed BOOLEAN,
    duration_seconds       REAL,
    original_format        TEXT,
    download_url           TEXT,
    preview_url            TEXT,
    source_tags_json       TEXT,
    raw_metadata_json      TEXT NOT NULL,
    candidate_score        REAL,
    candidate_status       TEXT NOT NULL DEFAULT 'discovered',
    downloaded_at          TEXT,
    created_at             TEXT NOT NULL,
    FOREIGN KEY (ingestion_job_id) REFERENCES ingestion_jobs(id),
    UNIQUE (source_name, source_item_id)
);
CREATE INDEX IF NOT EXISTS idx_candidates_job    ON candidate_items(ingestion_job_id);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidate_items(candidate_status);
CREATE INDEX IF NOT EXISTS idx_candidates_source ON candidate_items(source_name);

CREATE TABLE IF NOT EXISTS audio_assets (
    id                   INTEGER PRIMARY KEY,
    candidate_item_id    INTEGER NOT NULL,
    local_id             TEXT NOT NULL UNIQUE,
    checksum_sha256      TEXT NOT NULL UNIQUE,
    raw_file_path        TEXT NOT NULL,
    normalized_file_path TEXT NOT NULL,
    waveform_path        TEXT,
    spectrogram_path     TEXT,
    sample_rate          INTEGER NOT NULL,
    channels             INTEGER NOT NULL,
    duration_seconds     REAL NOT NULL,
    loudness_lufs        REAL,
    peak_db              REAL,
    silence_ratio        REAL,
    rms                  REAL,
    clipping_ratio       REAL,
    quality_score        REAL,
    world_fit_score      REAL,
    pulse_fit_score      REAL,
    drift_fit_score      REAL,
    approval_status      TEXT NOT NULL DEFAULT 'pending_review',
    rejection_reason     TEXT,
    ingestion_timestamp  TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    FOREIGN KEY (candidate_item_id) REFERENCES candidate_items(id)
);
CREATE INDEX IF NOT EXISTS idx_assets_status    ON audio_assets(approval_status);
CREATE INDEX IF NOT EXISTS idx_assets_score     ON audio_assets(world_fit_score);
CREATE INDEX IF NOT EXISTS idx_assets_candidate ON audio_assets(candidate_item_id);

CREATE TABLE IF NOT EXISTS tags (
    id          INTEGER PRIMARY KEY,
    tag_text    TEXT NOT NULL,
    tag_type    TEXT NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE (tag_text, tag_type)
);
CREATE INDEX IF NOT EXISTS idx_tags_text ON tags(tag_text);
CREATE INDEX IF NOT EXISTS idx_tags_type ON tags(tag_type);

CREATE TABLE IF NOT EXISTS asset_tags (
    id            INTEGER PRIMARY KEY,
    asset_id      INTEGER NOT NULL,
    tag_id        INTEGER NOT NULL,
    confidence    REAL,
    source_method TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES audio_assets(id),
    FOREIGN KEY (tag_id)   REFERENCES tags(id),
    UNIQUE (asset_id, tag_id, source_method)
);
CREATE INDEX IF NOT EXISTS idx_asset_tags_asset ON asset_tags(asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_tags_tag   ON asset_tags(tag_id);

CREATE TABLE IF NOT EXISTS embeddings (
    id              INTEGER PRIMARY KEY,
    asset_id        INTEGER NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dim   INTEGER NOT NULL,
    embedding_path  TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES audio_assets(id),
    UNIQUE (asset_id, embedding_model)
);
CREATE INDEX IF NOT EXISTS idx_embeddings_asset ON embeddings(asset_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(embedding_model);

CREATE TABLE IF NOT EXISTS analysis_features (
    id                       INTEGER PRIMARY KEY,
    asset_id                 INTEGER NOT NULL UNIQUE,
    spectral_centroid_mean   REAL,
    spectral_bandwidth_mean  REAL,
    zero_crossing_rate_mean  REAL,
    tempo_estimate           REAL,
    tonal_confidence         REAL,
    speech_probability       REAL,
    music_probability        REAL,
    noise_probability        REAL,
    created_at               TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES audio_assets(id)
);
CREATE INDEX IF NOT EXISTS idx_features_asset ON analysis_features(asset_id);

CREATE TABLE IF NOT EXISTS review_actions (
    id          INTEGER PRIMARY KEY,
    asset_id    INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    reviewer    TEXT,
    notes       TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES audio_assets(id)
);
CREATE INDEX IF NOT EXISTS idx_reviews_asset  ON review_actions(asset_id);
CREATE INDEX IF NOT EXISTS idx_reviews_action ON review_actions(action_type);
CREATE INDEX IF NOT EXISTS idx_reviews_time   ON review_actions(created_at);
"""


def generate_local_id(source_name: str, source_item_id: str, checksum: str) -> str:
    raw = source_name + source_item_id + checksum
    short_hash = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"{source_name}_{source_item_id}_{short_hash}"


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._seed_sources()
        print(f"[db] connected to {self.db_path}")

    def close(self):
        if self._conn:
            self._conn.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    def _seed_sources(self):
        for name in SourceName:
            self.conn.execute(
                "INSERT OR IGNORE INTO sources (name, enabled, created_at) VALUES (?, 1, ?)",
                (name.value, utcnow()),
            )
        self.conn.commit()

    # --- ingestion_jobs ---

    def create_job(self, query: str, source_name: str, limit: int, notes: str = "") -> int:
        cur = self.conn.execute(
            """INSERT INTO ingestion_jobs
               (query_text, source_name, requested_limit, status, notes, created_at)
               VALUES (?, ?, ?, 'pending', ?, ?)""",
            (query, source_name, limit, notes, utcnow()),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_job_status(self, job_id: int, status: JobStatus, notes: str = ""):
        now = utcnow()
        fields = {"status": status.value, "notes": notes}
        if status == JobStatus.running:
            fields["started_at"] = now
        elif status in (JobStatus.completed, JobStatus.failed):
            fields["finished_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE ingestion_jobs SET {set_clause} WHERE id = ?",
            (*fields.values(), job_id),
        )
        self.conn.commit()

    # --- candidate_items ---

    def upsert_candidate(self, data: dict) -> int:
        data.setdefault("created_at", utcnow())
        data.setdefault("candidate_status", CandidateStatus.discovered.value)
        cur = self.conn.execute(
            """INSERT INTO candidate_items
               (ingestion_job_id, source_name, source_item_id, source_url, title,
                description, creator, license, attribution_required,
                commercial_use_allowed, derivative_use_allowed, duration_seconds,
                original_format, download_url, preview_url, source_tags_json,
                raw_metadata_json, candidate_score, candidate_status, created_at)
               VALUES (:ingestion_job_id, :source_name, :source_item_id, :source_url,
                       :title, :description, :creator, :license, :attribution_required,
                       :commercial_use_allowed, :derivative_use_allowed, :duration_seconds,
                       :original_format, :download_url, :preview_url, :source_tags_json,
                       :raw_metadata_json, :candidate_score, :candidate_status, :created_at)
               ON CONFLICT(source_name, source_item_id) DO UPDATE SET
                   candidate_status = excluded.candidate_status,
                   candidate_score  = excluded.candidate_score""",
            data,
        )
        self.conn.commit()
        return cur.lastrowid

    def update_candidate_status(self, candidate_id: int, status: CandidateStatus):
        self.conn.execute(
            "UPDATE candidate_items SET candidate_status = ? WHERE id = ?",
            (status.value, candidate_id),
        )
        self.conn.commit()

    # --- audio_assets ---

    def insert_asset(self, data: dict) -> int:
        now = utcnow()
        data.setdefault("created_at", now)
        data.setdefault("updated_at", now)
        data.setdefault("ingestion_timestamp", now)
        data.setdefault("approval_status", ApprovalStatus.pending_review.value)
        cur = self.conn.execute(
            """INSERT INTO audio_assets
               (candidate_item_id, local_id, checksum_sha256, raw_file_path,
                normalized_file_path, waveform_path, spectrogram_path,
                sample_rate, channels, duration_seconds, loudness_lufs,
                peak_db, silence_ratio, rms, clipping_ratio,
                quality_score, world_fit_score, pulse_fit_score, drift_fit_score,
                approval_status, rejection_reason, ingestion_timestamp, created_at, updated_at)
               VALUES (:candidate_item_id, :local_id, :checksum_sha256, :raw_file_path,
                       :normalized_file_path, :waveform_path, :spectrogram_path,
                       :sample_rate, :channels, :duration_seconds, :loudness_lufs,
                       :peak_db, :silence_ratio, :rms, :clipping_ratio,
                       :quality_score, :world_fit_score, :pulse_fit_score, :drift_fit_score,
                       :approval_status, :rejection_reason, :ingestion_timestamp,
                       :created_at, :updated_at)""",
            data,
        )
        self.conn.commit()
        return cur.lastrowid

    def update_asset_status(self, asset_id: int, status: ApprovalStatus, reason: str = ""):
        self.conn.execute(
            "UPDATE audio_assets SET approval_status = ?, rejection_reason = ?, updated_at = ? WHERE id = ?",
            (status.value, reason, utcnow(), asset_id),
        )
        self.conn.commit()

    def get_approved_assets(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM audio_assets WHERE approval_status = 'approved' ORDER BY world_fit_score DESC"
        ).fetchall()

    # --- tags ---

    def get_or_create_tag(self, tag_text: str, tag_type: TagType) -> int:
        row = self.conn.execute(
            "SELECT id FROM tags WHERE tag_text = ? AND tag_type = ?",
            (tag_text, tag_type.value),
        ).fetchone()
        if row:
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO tags (tag_text, tag_type, created_at) VALUES (?, ?, ?)",
            (tag_text, tag_type.value, utcnow()),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_asset_tag(self, asset_id: int, tag_id: int, source_method: str, confidence: float = None):
        self.conn.execute(
            """INSERT OR IGNORE INTO asset_tags (asset_id, tag_id, confidence, source_method, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (asset_id, tag_id, confidence, source_method, utcnow()),
        )
        self.conn.commit()

    # --- review_actions ---

    def add_review_action(self, asset_id: int, action_type: ReviewActionType,
                          reviewer: str = "", notes: str = ""):
        self.conn.execute(
            "INSERT INTO review_actions (asset_id, action_type, reviewer, notes, created_at) VALUES (?, ?, ?, ?, ?)",
            (asset_id, action_type.value, reviewer, notes, utcnow()),
        )
        self.conn.commit()

    # --- analysis_features ---

    def upsert_features(self, asset_id: int, features: dict):
        features["asset_id"] = asset_id
        features.setdefault("created_at", utcnow())
        self.conn.execute(
            """INSERT INTO analysis_features
               (asset_id, spectral_centroid_mean, spectral_bandwidth_mean,
                zero_crossing_rate_mean, tempo_estimate, tonal_confidence,
                speech_probability, music_probability, noise_probability, created_at)
               VALUES (:asset_id, :spectral_centroid_mean, :spectral_bandwidth_mean,
                       :zero_crossing_rate_mean, :tempo_estimate, :tonal_confidence,
                       :speech_probability, :music_probability, :noise_probability, :created_at)
               ON CONFLICT(asset_id) DO UPDATE SET
                   spectral_centroid_mean  = excluded.spectral_centroid_mean,
                   spectral_bandwidth_mean = excluded.spectral_bandwidth_mean,
                   zero_crossing_rate_mean = excluded.zero_crossing_rate_mean,
                   tempo_estimate          = excluded.tempo_estimate,
                   tonal_confidence        = excluded.tonal_confidence,
                   speech_probability      = excluded.speech_probability,
                   music_probability       = excluded.music_probability,
                   noise_probability       = excluded.noise_probability""",
            features,
        )
        self.conn.commit()

    # --- embeddings ---

    def insert_embedding(self, asset_id: int, model: str, dim: int, path: str):
        self.conn.execute(
            """INSERT OR IGNORE INTO embeddings (asset_id, embedding_model, embedding_dim, embedding_path, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (asset_id, model, dim, path, utcnow()),
        )
        self.conn.commit()
