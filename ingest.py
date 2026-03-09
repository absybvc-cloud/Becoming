#!/usr/bin/env python3
"""
CLI to run the Becoming audio ingestion pipeline.

Usage:
    python ingest.py --query "ambient drone" --source freesound --limit 10
    python ingest.py --query "field recording rain" --source internet_archive --limit 5
    python ingest.py --export-manifest
    python ingest.py --review <asset_id> --approve
    python ingest.py --review <asset_id> --reject --notes "too much speech"
"""

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from src.ingestion.database import Database
from src.ingestion.models import PipelineConfigModel
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.sources.freesound import FreesoundConnector
from src.ingestion.sources.internet_archive import InternetArchiveConnector
from src.ingestion.sources.wikimedia import WikimediaConnector

MANIFEST_OUT = os.path.join("assets", "library", "manifest.json")
DB_PATH = os.path.join("library", "becoming.db")


def build_pipeline() -> IngestionPipeline:
    config = PipelineConfigModel(
        database_url=DB_PATH,
        raw_dir="library/audio_raw",
        normalized_dir="library/audio_normalized",
        embeddings_dir="library/embeddings",
        spectrogram_dir="library/spectrograms",
        waveform_dir="library/waveforms",
        rejected_dir="library/rejected",
        review_required=True,
    )
    db = Database(DB_PATH)
    db.connect()

    pipeline = IngestionPipeline(config=config, db=db)

    freesound_key = os.getenv("FREESOUND_API_KEY", "")
    if freesound_key:
        pipeline.register_source(FreesoundConnector(api_key=freesound_key))
    else:
        print("[ingest] WARNING: FREESOUND_API_KEY not set — freesound source disabled")

    pipeline.register_source(InternetArchiveConnector())
    pipeline.register_source(WikimediaConnector())

    return pipeline


def main():
    parser = argparse.ArgumentParser(description="Becoming audio ingestion pipeline")
    parser.add_argument("--query", type=str, help="Search query")
    parser.add_argument("--source", type=str, choices=["freesound", "internet_archive", "wikimedia"],
                        help="Source to search")
    parser.add_argument("--limit", type=int, default=20, help="Max results to fetch")
    parser.add_argument("--export-manifest", action="store_true",
                        help="Export approved assets to manifest.json")
    parser.add_argument("--review", type=int, metavar="ASSET_ID",
                        help="Review an asset by ID")
    parser.add_argument("--approve", action="store_true", help="Approve the asset")
    parser.add_argument("--reject", action="store_true", help="Reject the asset")
    parser.add_argument("--notes", type=str, default="", help="Notes for review action")
    parser.add_argument("--reviewer", type=str, default="curator", help="Reviewer name")

    args = parser.parse_args()

    pipeline = build_pipeline()

    if args.export_manifest:
        pipeline.export_manifest(MANIFEST_OUT)
        return

    if args.review is not None:
        if not args.approve and not args.reject:
            print("ERROR: --review requires --approve or --reject")
            sys.exit(1)
        pipeline.review(
            asset_id=args.review,
            approve=args.approve,
            reviewer=args.reviewer,
            notes=args.notes,
        )
        return

    if not args.query or not args.source:
        parser.print_help()
        sys.exit(1)

    pipeline.run(query=args.query, source_name=args.source, limit=args.limit)


if __name__ == "__main__":
    main()
