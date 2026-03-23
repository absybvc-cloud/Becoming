import json
import os
from pathlib import Path

from .database import Database, generate_local_id
from .enums import JobStatus, CandidateStatus, ApprovalStatus, TagType, ReviewActionType
from .models import PipelineConfigModel, SourceSearchRequest
from .normalizer import download_file, compute_checksum, normalize_audio, compute_loudness_features
from .analyzer import extract_features, score_quality, score_world_fit, score_pulse_fit, score_drift_fit
from .sources.base import BaseSourceConnector


class IngestionPipeline:
    def __init__(self, config: PipelineConfigModel, db: Database, auto_tag: bool = False):
        self.config = config
        self.db = db
        self.auto_tag = auto_tag
        self._connectors: dict[str, BaseSourceConnector] = {}

    def register_source(self, connector: BaseSourceConnector):
        self._connectors[connector.source_name] = connector
        print(f"[pipeline] registered source: {connector.source_name}")

    def run(self, query: str, source_name: str, limit: int = None, page: int = 1) -> int:
        """
        Full pipeline: search → filter → download → normalize → analyze → store.
        Returns number of assets successfully ingested.
        """
        limit = limit or self.config.default_limit

        if source_name not in self._connectors:
            raise ValueError(f"No connector registered for source: {source_name}")
        if source_name not in self.config.allowed_sources:
            raise ValueError(f"Source not allowed: {source_name}")

        connector = self._connectors[source_name]

        # create job
        job_id = self.db.create_job(query, source_name, limit)
        self.db.update_job_status(job_id, JobStatus.running)
        print(f"[pipeline] job {job_id} started | query='{query}' source={source_name} page={page}")

        ingested = 0
        try:
            request = SourceSearchRequest(query=query, source_name=source_name, limit=limit, page=page, filters={
                "min_duration": self.config.min_duration_sec,
                "max_duration": self.config.max_duration_sec,
            })
            results = connector.search(request)

            for result in results:
                try:
                    ok = self._process_candidate(job_id, result)
                    if ok:
                        ingested += 1
                except Exception as e:
                    print(f"[pipeline] error processing {result.source_item_id}: {e}")

            self.db.update_job_status(job_id, JobStatus.completed, notes=f"{ingested} assets ingested")
            print(f"[pipeline] job {job_id} completed | {ingested}/{len(results)} ingested")

        except Exception as e:
            self.db.update_job_status(job_id, JobStatus.failed, notes=str(e))
            print(f"[pipeline] job {job_id} failed: {e}")

        return ingested

    def _process_candidate(self, job_id: int, result) -> bool:
        # filter by duration
        dur = result.duration_seconds
        if dur is not None:
            if dur < self.config.min_duration_sec or dur > self.config.max_duration_sec:
                self._store_candidate(job_id, result, CandidateStatus.filtered_out)
                return False

        if not result.download_url:
            self._store_candidate(job_id, result, CandidateStatus.filtered_out)
            return False

        candidate_id = self._store_candidate(job_id, result, CandidateStatus.discovered)

        # Skip if this source item was already downloaded before
        existing = self.db.conn.execute(
            "SELECT a.id FROM audio_assets a "
            "JOIN candidate_items c ON a.candidate_item_id = c.id "
            "WHERE c.source_name = ? AND c.source_item_id = ?",
            (result.source_name, result.source_item_id),
        ).fetchone()
        if existing:
            self.db.update_candidate_status(candidate_id, CandidateStatus.filtered_out)
            return False

        # download
        raw_path = os.path.join(
            self.config.raw_dir, result.source_name,
            f"{result.source_item_id}.{result.original_format or 'mp3'}"
        )
        api_key = getattr(self._connectors.get(result.source_name), "api_key", "")
        ok = download_file(result.download_url, raw_path, api_key=api_key)
        if not ok:
            self.db.update_candidate_status(candidate_id, CandidateStatus.filtered_out)
            return False

        self.db.update_candidate_status(candidate_id, CandidateStatus.downloaded)

        # checksum
        checksum = compute_checksum(raw_path)
        local_id = generate_local_id(result.source_name, result.source_item_id, checksum)

        # normalize
        norm_path = os.path.join(
            self.config.normalized_dir, result.source_name, f"{local_id}.wav"
        )
        try:
            props = normalize_audio(
                raw_path, norm_path,
                target_sr=self.config.target_sample_rate,
                target_channels=self.config.target_channels,
            )
        except Exception as e:
            print(f"[pipeline] normalize failed for {local_id}: {e}")
            self.db.update_candidate_status(candidate_id, CandidateStatus.filtered_out)
            return False

        # loudness
        loudness = compute_loudness_features(norm_path)

        # quality filter
        quality = score_quality(loudness, props["duration_seconds"], self.config.model_dump())
        if quality < 0.4:
            print(f"[pipeline] low quality ({quality}) — rejecting {local_id}")
            self.db.update_candidate_status(candidate_id, CandidateStatus.rejected)
            return False

        # features
        self.db.update_candidate_status(candidate_id, CandidateStatus.analyzed)
        features = extract_features(norm_path)

        world_fit = score_world_fit(features, loudness)
        if world_fit < self.config.min_world_fit_score:
            print(f"[pipeline] low world fit ({world_fit}) — rejecting {local_id}")
            self.db.update_candidate_status(candidate_id, CandidateStatus.rejected)
            return False

        pulse_fit = score_pulse_fit(features)
        drift_fit = score_drift_fit(features, loudness)

        # store asset
        asset_data = {
            "candidate_item_id": candidate_id,
            "local_id": local_id,
            "checksum_sha256": checksum,
            "raw_file_path": raw_path,
            "normalized_file_path": norm_path,
            "waveform_path": None,
            "spectrogram_path": None,
            **props,
            **loudness,
            "quality_score": quality,
            "world_fit_score": world_fit,
            "pulse_fit_score": pulse_fit,
            "drift_fit_score": drift_fit,
            "approval_status": (
                ApprovalStatus.approved.value
                if not self.config.review_required
                else ApprovalStatus.pending_review.value
            ),
            "rejection_reason": None,
        }
        asset_id = self.db.insert_asset(asset_data)
        self.db.upsert_features(asset_id, features)

        # store source tags
        for tag_text in (result.source_tags or []):
            tag_id = self.db.get_or_create_tag(tag_text, TagType.source)
            self.db.add_asset_tag(asset_id, tag_id, source_method="source_metadata")

        self.db.update_candidate_status(candidate_id, CandidateStatus.approved)

        approval = "auto-approved" if not self.config.review_required else "pending review"
        print(f"[pipeline] ✓ {local_id} | quality={quality} world_fit={world_fit} | {approval}")

        # Auto-tag immediately if enabled
        if self.auto_tag:
            self._auto_tag_asset(asset_id)

        return True

    def _auto_tag_asset(self, asset_id: int):
        """Run LLM auto-tagging on a single asset immediately after ingest."""
        try:
            # Import here to avoid circular dependency and keep auto_tag optional
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
            from auto_tag import get_untagged_assets, build_prompt, call_ollama, apply_tags, DEFAULT_MODEL

            assets = get_untagged_assets(self.db, retag=False)
            asset = next((a for a in assets if a["id"] == asset_id), None)
            if not asset:
                return
            prompt = build_prompt(asset)
            result = call_ollama(prompt, DEFAULT_MODEL)
            if result:
                apply_tags(self.db, asset_id, result)
        except Exception as e:
            print(f"[pipeline] auto-tag failed for asset {asset_id}: {e}")

    def _store_candidate(self, job_id: int, result, status: CandidateStatus) -> int:
        data = {
            "ingestion_job_id": job_id,
            "source_name": result.source_name,
            "source_item_id": result.source_item_id,
            "source_url": result.source_url,
            "title": result.title,
            "description": result.description,
            "creator": result.creator,
            "license": result.license,
            "attribution_required": result.attribution_required,
            "commercial_use_allowed": result.commercial_use_allowed,
            "derivative_use_allowed": result.derivative_use_allowed,
            "duration_seconds": result.duration_seconds,
            "original_format": result.original_format,
            "download_url": result.download_url,
            "preview_url": result.preview_url,
            "source_tags_json": json.dumps(result.source_tags),
            "raw_metadata_json": json.dumps(result.raw_metadata),
            "candidate_score": None,
            "candidate_status": status.value,
        }
        return self.db.upsert_candidate(data)

    def review(self, asset_id: int, approve: bool, reviewer: str = "", notes: str = ""):
        """Manually approve or reject a pending asset."""
        if approve:
            self.db.update_asset_status(asset_id, ApprovalStatus.approved)
            self.db.add_review_action(asset_id, ReviewActionType.approve, reviewer, notes)
            print(f"[pipeline] asset {asset_id} approved by {reviewer or 'system'}")
        else:
            self.db.update_asset_status(asset_id, ApprovalStatus.rejected, reason=notes)
            self.db.add_review_action(asset_id, ReviewActionType.reject, reviewer, notes)
            print(f"[pipeline] asset {asset_id} rejected: {notes}")

    def export_manifest(self, out_path: str):
        """Export all approved assets as a manifest.json for the AudioLibraryManager."""
        rows = self.db.get_approved_assets()
        entries = []
        for row in rows:
            entries.append({
                "id": row["local_id"],
                "category": "drone",  # curator assigns category via review
                "file_path": row["normalized_file_path"],
                "duration": row["duration_seconds"],
                "energy_level": max(1, min(10, int((row["world_fit_score"] or 0.5) * 10))),
                "density_level": 5,
                "loopable": row["duration_seconds"] > 10,
                "cooldown": 120,
                "tags": [],
            })
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(entries, f, indent=2)
        print(f"[pipeline] exported {len(entries)} approved assets to {out_path}")
