#!/usr/bin/env python3
"""
Auto-tag audio assets using a local LLM via Ollama.

Reads untagged or under-tagged assets from the database, builds a prompt
from audio features + source metadata, and asks the LLM to generate
semantic tags for the Becoming sound library.

Usage:
    python auto_tag.py                          # tag all untagged assets
    python auto_tag.py --asset-id 42            # tag a specific asset
    python auto_tag.py --retag                  # re-tag assets that already have model tags
    python auto_tag.py --model qwen3-coder:30b  # use a specific model
    python auto_tag.py --dry-run                # preview prompts without calling LLM
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

from src.ingestion.database import Database
from src.ingestion.enums import TagType

DB_PATH = os.path.join("library", "becoming.db")
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = "qwen3-coder:30b"

# ── Becoming Ontology ───────────────────────────────────────────────────────
# Tags the LLM should choose from (it can also suggest new ones)
BECOMING_ONTOLOGY = {
    "sonic_character": [
        "drone", "texture", "tonal", "noise", "rhythmic", "harmonic",
        "percussive", "resonant", "granular", "melodic", "atonal",
        "distorted", "clean", "saturated", "hollow", "dense",
    ],
    "environment": [
        "nature", "urban", "industrial", "underwater", "interior",
        "exterior", "cave", "forest", "ocean", "rain", "wind", "silence",
    ],
    "mood": [
        "meditative", "tense", "serene", "dark", "bright", "mysterious",
        "ominous", "delicate", "aggressive", "floating", "grounding",
    ],
    "becoming_role": [
        "pulse_material", "drift_material", "transition", "rare_event",
        "background_layer", "foreground_element", "ritual_sound",
    ],
    "source_type": [
        "field_recording", "synthesizer", "acoustic_instrument",
        "voice", "found_sound", "electronic", "processed",
    ],
}


def get_db() -> Database:
    db = Database(DB_PATH)
    db.connect()
    return db


def get_untagged_assets(db: Database, retag: bool = False) -> list[dict]:
    """Get assets that need model-generated tags."""
    if retag:
        # Get all non-rejected assets
        rows = db.conn.execute(
            "SELECT id, local_id, normalized_file_path, duration_seconds, "
            "quality_score, world_fit_score, pulse_fit_score, drift_fit_score "
            "FROM audio_assets WHERE approval_status != 'rejected'"
        ).fetchall()
    else:
        # Get assets without any model-generated tags
        rows = db.conn.execute(
            "SELECT a.id, a.local_id, a.normalized_file_path, a.duration_seconds, "
            "a.quality_score, a.world_fit_score, a.pulse_fit_score, a.drift_fit_score "
            "FROM audio_assets a "
            "WHERE a.approval_status != 'rejected' "
            "AND a.id NOT IN ("
            "  SELECT DISTINCT at2.asset_id FROM asset_tags at2 "
            "  JOIN tags t ON at2.tag_id = t.id "
            "  WHERE t.tag_type = 'model'"
            ")"
        ).fetchall()

    assets = []
    for row in rows:
        asset = dict(row)
        # Get source tags
        source_tags = db.conn.execute(
            "SELECT t.tag_text FROM asset_tags at "
            "JOIN tags t ON at.tag_id = t.id "
            "WHERE at.asset_id = ? AND t.tag_type = 'source'",
            (asset["id"],)
        ).fetchall()
        asset["source_tags"] = [r["tag_text"] for r in source_tags]

        # Get analysis features
        features = db.conn.execute(
            "SELECT * FROM analysis_features WHERE asset_id = ?",
            (asset["id"],)
        ).fetchone()
        if features:
            asset["features"] = dict(features)
        else:
            asset["features"] = {}

        # Get candidate metadata (title, description)
        candidate = db.conn.execute(
            "SELECT c.title, c.description, c.source_name "
            "FROM candidate_items c "
            "JOIN audio_assets a ON a.candidate_item_id = c.id "
            "WHERE a.id = ?",
            (asset["id"],)
        ).fetchone()
        if candidate:
            asset["title"] = candidate["title"]
            asset["description"] = candidate["description"]
            asset["source_name"] = candidate["source_name"]

        assets.append(asset)

    return assets


def build_prompt(asset: dict) -> str:
    """Build a tagging prompt for the LLM."""
    ontology_text = ""
    for category, tags in BECOMING_ONTOLOGY.items():
        ontology_text += f"  {category}: {', '.join(tags)}\n"

    features = asset.get("features", {})
    feature_text = ""
    for key in ["spectral_centroid_mean", "spectral_bandwidth_mean",
                 "zero_crossing_rate_mean", "tempo_estimate",
                 "tonal_confidence", "speech_probability",
                 "music_probability", "noise_probability"]:
        val = features.get(key)
        if val is not None:
            feature_text += f"  {key}: {val:.4f}\n"

    prompt = f"""You are a sound curator for "Becoming", an endless generative music album.
Your task: analyze the following audio asset and assign semantic tags.

ASSET INFO:
  local_id: {asset.get('local_id', 'unknown')}
  title: {asset.get('title', 'untitled')}
  description: {asset.get('description', 'none')[:300] if asset.get('description') else 'none'}
  source: {asset.get('source_name', 'unknown')}
  duration: {asset.get('duration_seconds', 0):.1f}s
  source_tags: {', '.join(asset.get('source_tags', [])) or 'none'}

SCORES:
  quality: {asset.get('quality_score', 0):.2f}
  world_fit: {asset.get('world_fit_score', 0):.2f}
  pulse_fit: {asset.get('pulse_fit_score', 0):.2f}
  drift_fit: {asset.get('drift_fit_score', 0):.2f}

AUDIO FEATURES:
{feature_text or '  (none available)'}

TAG ONTOLOGY (prefer these, but you may add new tags if needed):
{ontology_text}

INSTRUCTIONS:
1. Select 3-8 tags from the ontology that best describe this sound
2. Assign a confidence score (0.0-1.0) for each tag
3. Suggest a "becoming_role" (how this sound fits in the generative system)
4. Write a one-line description of the sound's character

Respond ONLY with valid JSON in this exact format:
{{
  "tags": [
    {{"tag": "drone", "category": "sonic_character", "confidence": 0.9}},
    {{"tag": "meditative", "category": "mood", "confidence": 0.7}}
  ],
  "becoming_role": "drift_material",
  "description": "A warm low-frequency drone with subtle harmonic overtones"
}}"""

    return prompt


def call_ollama(prompt: str, model: str) -> dict | None:
    """Call local Ollama instance for tag generation."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 512,
                },
            },
            timeout=120,
        )
        resp.raise_for_status()
        raw_text = resp.json().get("response", "")

        # Extract JSON from response (handle markdown code blocks)
        text = raw_text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        # Find the outermost JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]

        return json.loads(text)

    except requests.exceptions.ConnectionError:
        print(f"[auto_tag] ERROR: cannot connect to Ollama at {OLLAMA_BASE}")
        print(f"[auto_tag] Make sure Ollama is running: ollama serve")
        return None
    except json.JSONDecodeError as e:
        print(f"[auto_tag] ERROR: failed to parse LLM response as JSON: {e}")
        print(f"[auto_tag] raw response: {raw_text[:300]}")
        return None
    except Exception as e:
        print(f"[auto_tag] ERROR: Ollama call failed: {e}")
        return None


def apply_tags(db: Database, asset_id: int, result: dict):
    """Store LLM-generated tags in the database."""
    tags = result.get("tags", [])
    for tag_entry in tags:
        tag_text = tag_entry.get("tag", "").strip().lower()
        confidence = tag_entry.get("confidence", 0.5)
        if not tag_text:
            continue

        # Validate confidence range
        confidence = max(0.0, min(1.0, float(confidence)))

        tag_id = db.get_or_create_tag(tag_text, TagType.model)
        db.add_asset_tag(asset_id, tag_id, source_method="ollama_auto_tag", confidence=confidence)

    # Also store the becoming_role as a tag
    role = result.get("becoming_role", "").strip().lower()
    if role:
        tag_id = db.get_or_create_tag(role, TagType.model)
        db.add_asset_tag(asset_id, tag_id, source_method="ollama_auto_tag", confidence=0.8)

    print(f"[auto_tag] stored {len(tags)} tags + role='{role}' for asset {asset_id}")


def main():
    parser = argparse.ArgumentParser(description="Becoming auto-tagger (LLM via Ollama)")
    parser.add_argument("--asset-id", type=int, help="Tag a specific asset by ID")
    parser.add_argument("--retag", action="store_true",
                        help="Re-tag assets that already have model tags")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help=f"Ollama model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print prompts without calling LLM")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max assets to tag (0 = all)")
    args = parser.parse_args()

    db = get_db()

    if args.asset_id:
        # Tag a specific asset
        assets = get_untagged_assets(db, retag=True)
        assets = [a for a in assets if a["id"] == args.asset_id]
        if not assets:
            print(f"[auto_tag] asset {args.asset_id} not found or rejected")
            sys.exit(1)
    else:
        assets = get_untagged_assets(db, retag=args.retag)

    if args.limit > 0:
        assets = assets[:args.limit]

    if not assets:
        print("[auto_tag] no assets to tag")
        return

    print(f"[auto_tag] {len(assets)} assets to tag using model='{args.model}'")

    tagged = 0
    failed = 0

    for asset in assets:
        print(f"\n[auto_tag] processing asset {asset['id']} ({asset.get('local_id', '?')})")

        prompt = build_prompt(asset)

        if args.dry_run:
            print(f"  PROMPT ({len(prompt)} chars):")
            print("  " + prompt[:200].replace("\n", "\n  ") + "...")
            continue

        result = call_ollama(prompt, args.model)
        if result is None:
            failed += 1
            continue

        apply_tags(db, asset["id"], result)
        tagged += 1

    print(f"\n[auto_tag] DONE: {tagged} tagged, {failed} failed, {len(assets)} total")


if __name__ == "__main__":
    main()
