"""
Database-backed audio library for the Becoming engine.

Replaces the JSON manifest approach. Reads approved assets directly
from the SQLite database, maps them to SoundFragments with roles,
and provides them to the engine.
"""

import os
import sqlite3
from typing import Optional

from .roles import Role, SoundFragment, assign_role


DB_PATH = os.path.join("library", "becoming.db")


class SoundLibrary:
    """
    Loads approved audio assets from the database and maps them
    to SoundFragments with engine roles.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.fragments: dict[str, SoundFragment] = {}
        self._db: Optional[sqlite3.Connection] = None

    def load(self):
        """Load all approved assets from the database."""
        self._db = sqlite3.connect(self.db_path)
        self._db.row_factory = sqlite3.Row

        assets = self._db.execute("""
            SELECT id, local_id, normalized_file_path, duration_seconds,
                   quality_score, world_fit_score, drift_fit_score, pulse_fit_score
            FROM audio_assets
            WHERE normalized_file_path IS NOT NULL
        """).fetchall()

        loaded = 0
        for asset in assets:
            npath = asset["normalized_file_path"]
            if not npath or not os.path.isfile(npath):
                print(f"[library] skipping {asset['local_id']}: file not found at {npath}")
                continue

            # Get tags
            curator_tags = self._get_tags(asset["id"], "curator_review")
            model_tags = self._get_tags(asset["id"], "ollama_auto_tag")
            source_tags = self._get_tags(asset["id"], "source_metadata")
            all_tags = curator_tags + model_tags + source_tags

            # Get analysis features
            features = self._get_features(asset["id"])

            # Assign role
            role = assign_role(
                curator_tags=curator_tags,
                model_tags=model_tags,
                duration=asset["duration_seconds"],
                drift_fit=asset["drift_fit_score"] or 0.0,
                pulse_fit=asset["pulse_fit_score"] or 0.0,
            )

            # Determine loopability
            loopable = (
                asset["duration_seconds"] > 20.0
                and role in (Role.GROUND, Role.TEXTURE)
            )

            # Compute energy/density from features
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
                tags=list(set(all_tags)),  # deduplicate
                quality_score=asset["quality_score"] or 0.0,
                world_fit_score=asset["world_fit_score"] or 0.0,
                drift_fit_score=asset["drift_fit_score"] or 0.0,
                pulse_fit_score=asset["pulse_fit_score"] or 0.0,
                spectral_centroid=features.get("spectral_centroid_mean", 0.0),
                tempo=features.get("tempo", 0.0),
                tonal_confidence=features.get("tonal_confidence", 0.0),
            )
            self.fragments[frag.id] = frag
            loaded += 1

        print(f"[library] loaded {loaded} fragments from database")
        self._print_role_summary()

    def _get_tags(self, asset_id: int, source_method: str) -> list[str]:
        rows = self._db.execute("""
            SELECT t.tag_text FROM asset_tags at2
            JOIN tags t ON at2.tag_id = t.id
            WHERE at2.asset_id = ? AND at2.source_method = ?
        """, (asset_id, source_method)).fetchall()
        return [r["tag_text"] for r in rows]

    def _get_features(self, asset_id: int) -> dict:
        row = self._db.execute(
            "SELECT * FROM analysis_features WHERE asset_id = ?",
            (asset_id,)
        ).fetchone()
        if row is None:
            return {}
        return {k: row[k] for k in row.keys() if row[k] is not None}

    def _compute_energy(self, features: dict, asset) -> float:
        """Compute energy level 0-1 from features."""
        # Use spectral centroid + loudness as energy proxy
        centroid = features.get("spectral_centroid_mean", 1000.0)
        rms = features.get("rms", 0.0) if "rms" in features else 0.5
        # Normalize: centroid 0-5000 → 0-1, rms roughly 0-0.5 → 0-1
        energy = min(1.0, centroid / 5000.0) * 0.6 + min(1.0, rms * 2.0) * 0.4
        return max(0.0, min(1.0, energy))

    def _compute_density(self, features: dict, asset) -> float:
        """Compute density level 0-1 from features."""
        bandwidth = features.get("spectral_bandwidth_mean", 2000.0)
        # Wider bandwidth = higher density
        density = min(1.0, bandwidth / 4000.0)
        return max(0.0, min(1.0, density))

    def _print_role_summary(self):
        counts = {r: 0 for r in Role}
        for frag in self.fragments.values():
            counts[frag.role] += 1
        parts = [f"{r.value}={c}" for r, c in counts.items()]
        print(f"[library] roles: {', '.join(parts)}")

    def get_by_role(self, role: Role) -> list[SoundFragment]:
        return [f for f in self.fragments.values() if f.role == role]

    def get(self, fragment_id: str) -> Optional[SoundFragment]:
        return self.fragments.get(fragment_id)

    def all_fragments(self) -> list[SoundFragment]:
        return list(self.fragments.values())

    def summary(self) -> dict[str, int]:
        counts = {r.value: 0 for r in Role}
        for frag in self.fragments.values():
            counts[frag.role.value] += 1
        return counts
