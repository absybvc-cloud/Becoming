"""
Active Pool + Staging Queue — Hot Ingest Runtime

Two-buffer system for safe, live integration of new audio assets.

Runtime reads ONLY from the Active Pool.
Background processes write ONLY to the Staging Queue.
Merge happens ONLY at safe points in the scheduler cycle.
"""

import os
import sqlite3
import threading
from typing import Optional

from .roles import Role, SoundFragment, assign_role
from .vectors import (
    SemanticVector, RoleVector,
    build_semantic_vector_from_tags, build_role_vector, assign_cluster,
)

DB_PATH = os.path.join("library", "becoming.db")

# Minimum activation criteria (§6 of Hot Ingest Runtime spec)
MIN_DURATION = 0.5
WARMUP_CYCLES = 8
WARMUP_WEIGHT = 0.5


class ActivePool:
    """
    Runtime-safe in-memory pool of sound fragments.

    The scheduler reads ONLY from this pool.
    New assets enter through the staging queue and are merged
    at safe points without interrupting playback.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

        # ── Active runtime data (read by scheduler) ──
        self._fragments: dict[str, SoundFragment] = {}
        self._vectors: dict[str, SemanticVector] = {}
        self._role_vectors: dict[str, RoleVector] = {}
        self._clusters: dict[str, str] = {}

        # ── Staging queue (written by background, merged at safe points) ──
        self._staging: list[dict] = []
        self._staging_lock = threading.Lock()

        # ── Dirty metadata (tag/role changes pending refresh) ──
        self._metadata_dirty: set[int] = set()
        self._dirty_lock = threading.Lock()

        # ── Warmup tracking (newly merged assets get reduced weight) ──
        self._warmup_remaining: dict[str, int] = {}

        # ── Merge stats ──
        self.last_merge_count = 0
        self.total_merged = 0

    # ── Initial load from SoundLibrary ──────────────────────────────────

    def load_from_library(self, library) -> None:
        """Populate active pool from an already-loaded SoundLibrary."""
        self._fragments = dict(library.fragments)
        self._vectors = dict(library.vectors)
        self._role_vectors = dict(library.role_vectors)
        self._clusters = dict(library.clusters)
        print(f"[active-pool] loaded {len(self._fragments)} fragments from library")

    # ── Read API (used by conductor/scheduler — same as SoundLibrary) ──

    def get(self, fragment_id: str) -> Optional[SoundFragment]:
        return self._fragments.get(fragment_id)

    def all_fragments(self) -> list[SoundFragment]:
        return list(self._fragments.values())

    def get_by_role(self, role: Role) -> list[SoundFragment]:
        return [f for f in self._fragments.values() if f.role == role]

    def get_vector(self, fragment_id: str) -> Optional[SemanticVector]:
        return self._vectors.get(fragment_id)

    def get_role_vector(self, fragment_id: str) -> Optional[RoleVector]:
        return self._role_vectors.get(fragment_id)

    def get_cluster(self, fragment_id: str) -> Optional[str]:
        return self._clusters.get(fragment_id)

    def get_candidates(self) -> list[tuple[SoundFragment, SemanticVector, RoleVector]]:
        out = []
        for fid, frag in self._fragments.items():
            svec = self._vectors.get(fid)
            rvec = self._role_vectors.get(fid)
            if svec and rvec:
                out.append((frag, svec, rvec))
        return out

    @property
    def fragment_count(self) -> int:
        return len(self._fragments)

    def summary(self) -> dict[str, int]:
        counts = {r.value: 0 for r in Role}
        for frag in self._fragments.values():
            counts[frag.role.value] += 1
        return counts

    # ── Warmup weight modifier ──────────────────────────────────────────

    def warmup_weight(self, fragment_id: str) -> float:
        """Return weight multiplier: 1.0 for established, < 1.0 for newly merged."""
        remaining = self._warmup_remaining.get(fragment_id, 0)
        if remaining <= 0:
            return 1.0
        return WARMUP_WEIGHT

    def tick_warmup(self) -> None:
        """Decrement warmup counters. Call once per scheduler tick."""
        expired = []
        for fid, remaining in self._warmup_remaining.items():
            self._warmup_remaining[fid] = remaining - 1
            if remaining - 1 <= 0:
                expired.append(fid)
        for fid in expired:
            del self._warmup_remaining[fid]

    # ── Staging Queue (written by background processes) ─────────────────

    def stage_asset(self, asset_id: int) -> None:
        """
        Queue a database asset_id for merge into the active pool.
        Called by background ingest/auto-tag/rebalance processes.
        Thread-safe.
        """
        with self._staging_lock:
            self._staging.append({"asset_id": asset_id})

    def staging_size(self) -> int:
        with self._staging_lock:
            return len(self._staging)

    # ── Dirty Metadata (tag/role changes) ───────────────────────────────

    def mark_dirty(self, asset_id: int) -> None:
        """Mark an asset's metadata as needing refresh. Thread-safe."""
        with self._dirty_lock:
            self._metadata_dirty.add(asset_id)

    def dirty_count(self) -> int:
        with self._dirty_lock:
            return len(self._metadata_dirty)

    # ── Merge (called ONLY at safe points by conductor) ─────────────────

    def merge_staging(self) -> int:
        """
        Merge staged assets into the active pool.
        Returns number of assets merged.
        Must be called at a safe point (between scheduler decisions).
        """
        with self._staging_lock:
            if not self._staging:
                return 0
            to_merge = list(self._staging)
            self._staging.clear()

        merged = 0
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row

        try:
            for item in to_merge:
                frag = self._load_fragment(db, item["asset_id"])
                if frag is None:
                    continue
                # Validate activation criteria
                if not self._validate(frag):
                    print(f"[active-pool] quarantined asset {item['asset_id']}: failed validation")
                    continue
                # Add to active pool
                self._fragments[frag.id] = frag
                self._warmup_remaining[frag.id] = WARMUP_CYCLES
                merged += 1
        finally:
            db.close()

        if merged > 0:
            self.last_merge_count = merged
            self.total_merged += merged
            print(f"[active-pool] merged {merged} new assets (total: {len(self._fragments)})")

        return merged

    def refresh_dirty_metadata(self) -> int:
        """
        Refresh tags/roles for dirty assets from DB.
        Returns number refreshed.
        Must be called at a safe point.
        """
        with self._dirty_lock:
            if not self._metadata_dirty:
                return 0
            to_refresh = set(self._metadata_dirty)
            self._metadata_dirty.clear()

        refreshed = 0
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row

        try:
            for asset_id in to_refresh:
                # Find existing fragment by asset_id
                existing_fid = None
                for fid, frag in self._fragments.items():
                    if frag.asset_id == asset_id:
                        existing_fid = fid
                        break
                if not existing_fid:
                    continue

                updated = self._load_fragment(db, asset_id)
                if updated is None:
                    continue

                self._fragments[updated.id] = updated
                refreshed += 1
        finally:
            db.close()

        if refreshed > 0:
            print(f"[active-pool] refreshed metadata for {refreshed} assets")

        return refreshed

    # ── Internal: load a single fragment from DB ────────────────────────

    def _load_fragment(self, db: sqlite3.Connection, asset_id: int) -> Optional[SoundFragment]:
        """Load a single asset from the database and build a SoundFragment."""
        asset = db.execute("""
            SELECT id, local_id, normalized_file_path, duration_seconds,
                   quality_score, world_fit_score, drift_fit_score, pulse_fit_score
            FROM audio_assets
            WHERE id = ? AND normalized_file_path IS NOT NULL
        """, (asset_id,)).fetchone()

        if not asset:
            return None

        npath = asset["normalized_file_path"]
        if not npath or not os.path.isfile(npath):
            return None

        # Get tags
        curator_tags = self._get_tags(db, asset_id, "curator_review")
        model_tags = self._get_tags(db, asset_id, "ollama_auto_tag")
        source_tags = self._get_tags(db, asset_id, "source_metadata")
        all_tags = curator_tags + model_tags + source_tags

        # Get analysis features
        features = self._get_features(db, asset_id)

        # Assign role
        role = assign_role(
            curator_tags=curator_tags,
            model_tags=model_tags,
            duration=asset["duration_seconds"],
            drift_fit=asset["drift_fit_score"] or 0.0,
            pulse_fit=asset["pulse_fit_score"] or 0.0,
        )

        loopable = (
            asset["duration_seconds"] > 20.0
            and role in (Role.GROUND, Role.TEXTURE)
        )

        energy = self._compute_energy(features, asset)
        density = self._compute_density(features, asset)

        frag = SoundFragment(
            id=asset["local_id"],
            asset_id=asset["id"],
            role=role,
            file_path=npath,
            duration=asset["duration_seconds"],
            energy=energy,
            density=density,
            loopable=loopable,
            tags=list(set(all_tags)),
            quality_score=asset["quality_score"] or 0.0,
            world_fit_score=asset["world_fit_score"] or 0.0,
            drift_fit_score=asset["drift_fit_score"] or 0.0,
            pulse_fit_score=asset["pulse_fit_score"] or 0.0,
            spectral_centroid=features.get("spectral_centroid_mean", 0.0),
            tempo=features.get("tempo", 0.0),
            tonal_confidence=features.get("tonal_confidence", 0.0),
        )

        # Build vectors and cluster
        svec = build_semantic_vector_from_tags(curator_tags, model_tags, source_tags)
        rvec = build_role_vector(frag)
        cluster = assign_cluster(frag)

        self._vectors[frag.id] = svec
        self._role_vectors[frag.id] = rvec
        self._clusters[frag.id] = cluster

        return frag

    # ── Discover + ingest new DB assets not yet in the pool ───────────────

    def ingest_new_from_db(self) -> int:
        """
        Scan the database for approved assets not yet in the active pool.
        Load and validate each one, adding it with warmup weight.
        Returns number of new assets ingested.
        Thread-safe (acquires staging lock).
        """
        known_asset_ids = {f.asset_id for f in self._fragments.values()}

        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        ingested = 0

        try:
            rows = db.execute("""
                SELECT id FROM audio_assets
                WHERE normalized_file_path IS NOT NULL
            """).fetchall()

            for row in rows:
                aid = row["id"]
                if aid in known_asset_ids:
                    continue
                frag = self._load_fragment(db, aid)
                if frag is None:
                    continue
                if not self._validate(frag):
                    continue
                self._fragments[frag.id] = frag
                self._warmup_remaining[frag.id] = WARMUP_CYCLES
                ingested += 1
        finally:
            db.close()

        if ingested > 0:
            self.total_merged += ingested
            print(f"[active-pool] ingested {ingested} new assets from DB (total: {len(self._fragments)})")

        return ingested

    # ── Validation (§6: Minimum Activation Criteria) ────────────────────

    @staticmethod
    def _validate(frag: SoundFragment) -> bool:
        if not os.path.isfile(frag.file_path):
            return False
        if frag.duration < MIN_DURATION:
            return False
        if frag.role is None:
            return False
        if not frag.tags:
            return False
        return True

    # ── Helpers (mirrored from SoundLibrary) ────────────────────────────

    @staticmethod
    def _get_tags(db: sqlite3.Connection, asset_id: int, source_method: str) -> list[str]:
        rows = db.execute("""
            SELECT t.tag_text FROM asset_tags at2
            JOIN tags t ON at2.tag_id = t.id
            WHERE at2.asset_id = ? AND at2.source_method = ?
        """, (asset_id, source_method)).fetchall()
        return [r["tag_text"] for r in rows]

    @staticmethod
    def _get_features(db: sqlite3.Connection, asset_id: int) -> dict:
        row = db.execute(
            "SELECT * FROM analysis_features WHERE asset_id = ?",
            (asset_id,)
        ).fetchone()
        if row is None:
            return {}
        return {k: row[k] for k in row.keys() if row[k] is not None}

    @staticmethod
    def _compute_energy(features: dict, asset) -> float:
        centroid = features.get("spectral_centroid_mean", 1000.0)
        rms = features.get("rms", 0.0) if "rms" in features else 0.5
        energy = min(1.0, centroid / 5000.0) * 0.6 + min(1.0, rms * 2.0) * 0.4
        return max(0.0, min(1.0, energy))

    @staticmethod
    def _compute_density(features: dict, asset) -> float:
        bandwidth = features.get("spectral_bandwidth_mean", 2000.0)
        density = min(1.0, bandwidth / 4000.0)
        return max(0.0, min(1.0, density))
