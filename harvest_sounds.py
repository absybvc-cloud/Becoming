#!/usr/bin/env python3
"""
Auto-harvest sounds for Becoming.

Runs a batch of predefined search queries across configured sources
to continuously grow the sound library.

Usage:
    python harvest_sounds.py                     # run all default queries
    python harvest_sounds.py --queries ambient   # single query
    python harvest_sounds.py --source freesound  # specific source only
    python harvest_sounds.py --limit 5           # per-query limit
    python harvest_sounds.py --dry-run           # preview without downloading
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from src.ingestion.database import Database
from src.ingestion.models import PipelineConfigModel
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.sources.freesound import FreesoundConnector
from src.ingestion.sources.internet_archive import InternetArchiveConnector
from src.ingestion.sources.wikimedia import WikimediaConnector

# ── Search Queries ──────────────────────────────────────────────────────────
# Curated queries aligned with Becoming's sonic world.
# Categories: drone, texture, field_recording, rhythm, tonal, noise_event
HARVEST_QUERIES = [
    # Drones & ambient
    {"query": "ambient drone", "category": "drone"},
    {"query": "synthesizer pad", "category": "drone"},
    {"query": "organ sustain", "category": "drone"},
    {"query": "singing bowl resonance", "category": "drone"},
    {"query": "deep bass hum", "category": "drone"},
    # Textures
    {"query": "granular texture", "category": "texture"},
    {"query": "tape hiss noise", "category": "texture"},
    {"query": "analog static", "category": "texture"},
    {"query": "wind noise texture", "category": "texture"},
    {"query": "underwater ambience", "category": "texture"},
    # Field recordings
    {"query": "rain recording", "category": "field_recording"},
    {"query": "forest ambience birds", "category": "field_recording"},
    {"query": "ocean waves shore", "category": "field_recording"},
    {"query": "city traffic distant", "category": "field_recording"},
    {"query": "industrial factory ambient", "category": "field_recording"},
    # Rhythmic / pulse
    {"query": "percussion loop", "category": "rhythm"},
    {"query": "metallic rhythm", "category": "rhythm"},
    {"query": "heartbeat pulse", "category": "rhythm"},
    # Tonal
    {"query": "piano single note sustain", "category": "tonal"},
    {"query": "bells resonance", "category": "tonal"},
    {"query": "chime ring", "category": "tonal"},
    {"query": "harmonic overtones", "category": "tonal"},
    # Noise events (rare)
    {"query": "thunder rumble", "category": "noise_event"},
    {"query": "metal impact crash", "category": "noise_event"},
    {"query": "glass shatter", "category": "noise_event"},
]

DB_PATH = os.path.join("library", "becoming.db")
HARVEST_LOG = os.path.join("library", "harvest_log.jsonl")
DEFAULT_SOURCES = ["freesound", "internet_archive", "wikimedia"]


def build_pipeline(auto_tag: bool = False) -> IngestionPipeline:
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

    pipeline = IngestionPipeline(config=config, db=db, auto_tag=auto_tag)

    freesound_key = os.getenv("FREESOUND_API_KEY", "")
    if freesound_key:
        pipeline.register_source(FreesoundConnector(api_key=freesound_key))
    else:
        print("[harvest] WARNING: FREESOUND_API_KEY not set — freesound disabled")

    pipeline.register_source(InternetArchiveConnector())
    pipeline.register_source(WikimediaConnector())

    return pipeline


def log_harvest(entry: dict):
    """Append a harvest result to the log file."""
    Path(HARVEST_LOG).parent.mkdir(parents=True, exist_ok=True)
    with open(HARVEST_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def run_harvest(
    queries: list[dict],
    sources: list[str],
    limit_per_query: int,
    dry_run: bool = False,
    auto_tag: bool = False,
):
    if dry_run:
        print("[harvest] DRY RUN — no downloads will occur\n")
        for q in queries:
            for src in sources:
                print(f"  would search: '{q['query']}' on {src} (limit={limit_per_query})")
        print(f"\n[harvest] {len(queries)} queries × {len(sources)} sources = {len(queries) * len(sources)} searches")
        return

    pipeline = build_pipeline(auto_tag=auto_tag)
    available_sources = list(pipeline._connectors.keys())

    total_ingested = 0
    total_searches = 0
    ts_start = datetime.now(timezone.utc).isoformat()

    for q in queries:
        query_text = q["query"]
        category = q.get("category", "unknown")

        for source in sources:
            if source not in available_sources:
                continue

            total_searches += 1
            print(f"\n{'='*60}")
            print(f"[harvest] query='{query_text}' source={source} category={category}")
            print(f"{'='*60}")

            try:
                count = pipeline.run(query=query_text, source_name=source, limit=limit_per_query)
                total_ingested += count
                log_harvest({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "query": query_text,
                    "source": source,
                    "category": category,
                    "limit": limit_per_query,
                    "ingested": count,
                    "status": "ok",
                })
            except Exception as e:
                print(f"[harvest] ERROR: {e}")
                log_harvest({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "query": query_text,
                    "source": source,
                    "category": category,
                    "limit": limit_per_query,
                    "ingested": 0,
                    "status": "error",
                    "error": str(e),
                })

    print(f"\n{'='*60}")
    print(f"[harvest] COMPLETE")
    print(f"  searches: {total_searches}")
    print(f"  ingested: {total_ingested}")
    print(f"  started:  {ts_start}")
    print(f"  finished: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Becoming auto-harvest pipeline")
    parser.add_argument("--queries", nargs="+", help="Specific queries (overrides defaults)")
    parser.add_argument("--source", type=str, choices=DEFAULT_SOURCES,
                        help="Single source to use (default: all available)")
    parser.add_argument("--limit", type=int, default=10,
                        help="Max results per query per source (default: 10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview queries without downloading")
    parser.add_argument("--category", type=str,
                        help="Only run queries matching this category")
    parser.add_argument("--auto-tag", action="store_true",
                        help="Run LLM auto-tagging on each ingested asset")
    args = parser.parse_args()

    # Build query list
    if args.queries:
        queries = [{"query": q, "category": "custom"} for q in args.queries]
    else:
        queries = HARVEST_QUERIES

    if args.category:
        queries = [q for q in queries if q.get("category") == args.category]
        if not queries:
            print(f"[harvest] no queries match category '{args.category}'")
            sys.exit(1)

    # Build source list
    sources = [args.source] if args.source else DEFAULT_SOURCES

    print(f"[harvest] {len(queries)} queries × {len(sources)} sources, limit={args.limit}/query")
    if args.auto_tag:
        print("[harvest] auto-tag enabled — each sound will be LLM-tagged on ingest")
    run_harvest(queries, sources, args.limit, dry_run=args.dry_run, auto_tag=args.auto_tag)


if __name__ == "__main__":
    main()
