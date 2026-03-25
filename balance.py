#!/usr/bin/env python3
"""
Library balance analyzer and auto-rebalance harvester for Becoming.

Scans cluster distribution, identifies under-represented clusters,
and triggers targeted harvest queries to fill gaps.

Usage:
    python balance.py                    # analyze current balance
    python balance.py --rebalance        # auto-harvest until balanced (>=95%)
    python balance.py --rebalance --auto-tag  # also LLM-tag new sounds
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Ensure project root imports work ────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.ingestion.database import Database
from src.ingestion.enums import TagType
from src.engine.vectors import CLUSTER_DEFS, _assign_cluster, _GENERIC_TAGS
from balance_shapes import compute_target_shape, shape_score, shape_divergence, name_shape

DB_PATH = os.path.join("library", "becoming.db")

# ── Cluster → harvest query mapping ────────────────────────────────────────
# Maps each cluster to targeted search queries likely to produce sounds in
# that cluster.  Used by the auto-rebalance harvester.
CLUSTER_QUERIES: dict[str, list[dict]] = {
    "dark_drift": [
        {"query": "dark ambient drone", "category": "drone"},
        {"query": "ominous low hum", "category": "drone"},
        {"query": "dark bass rumble", "category": "drone"},
    ],
    "tonal_meditative": [
        {"query": "singing bowl meditation", "category": "tonal"},
        {"query": "bells resonance harmonic", "category": "tonal"},
        {"query": "chime clean tonal", "category": "tonal"},
        {"query": "crystal bowl sustained", "category": "tonal"},
    ],
    "nature_field": [
        {"query": "forest ambience birds", "category": "field_recording"},
        {"query": "rain recording", "category": "field_recording"},
        {"query": "ocean waves shore", "category": "field_recording"},
        {"query": "creek stream water", "category": "field_recording"},
        {"query": "meadow insects soundscape", "category": "field_recording"},
        {"query": "thunder storm recording", "category": "field_recording"},
    ],
    "urban_field": [
        {"query": "city traffic distant", "category": "field_recording"},
        {"query": "urban street ambience", "category": "field_recording"},
        {"query": "train station sounds", "category": "field_recording"},
        {"query": "construction site ambient", "category": "field_recording"},
    ],
    "industrial_noise": [
        {"query": "industrial noise texture", "category": "noise_event"},
        {"query": "factory machine ambient", "category": "noise_event"},
        {"query": "metal feedback distorted", "category": "noise_event"},
        {"query": "power plant hum", "category": "noise_event"},
    ],
    "texture_evolving": [
        {"query": "granular texture evolving", "category": "texture"},
        {"query": "tape hiss analog noise", "category": "texture"},
        {"query": "shimmering texture synthetic", "category": "texture"},
        {"query": "evolving pad texture", "category": "texture"},
        {"query": "found sound texture abstract", "category": "texture"},
    ],
    "pulse_rhythm": [
        {"query": "percussion loop rhythmic", "category": "rhythm"},
        {"query": "metallic rhythm pulse", "category": "rhythm"},
        {"query": "heartbeat pulse slow", "category": "rhythm"},
        {"query": "ritual drum", "category": "rhythm"},
    ],
    "rupture_event": [
        {"query": "glass shatter impact", "category": "noise_event"},
        {"query": "glitch digital error", "category": "noise_event"},
        {"query": "metal crash impact", "category": "noise_event"},
        {"query": "electrical discharge noise", "category": "noise_event"},
    ],
    "ambient_float": [
        {"query": "ambient atmosphere floating", "category": "drone"},
        {"query": "serene background ambient", "category": "drone"},
        {"query": "delicate ambient pad", "category": "drone"},
        {"query": "ethereal floating texture", "category": "texture"},
    ],
}


def get_db() -> Database:
    db = Database(DB_PATH)
    db.connect()
    return db


def get_cluster_distribution(db: Database) -> dict[str, list[dict]]:
    """
    Assign every non-rejected asset to a cluster based on its tags.
    Returns {cluster_name: [list of asset dicts]}.
    """
    rows = db.conn.execute(
        "SELECT id, local_id FROM audio_assets WHERE approval_status != 'rejected'"
    ).fetchall()

    clusters: dict[str, list[dict]] = {name: [] for name in CLUSTER_DEFS}
    clusters["unassigned"] = []

    for row in rows:
        asset_id = row["id"]
        tag_rows = db.conn.execute(
            "SELECT t.tag_text FROM asset_tags at "
            "JOIN tags t ON at.tag_id = t.id WHERE at.asset_id = ?",
            (asset_id,),
        ).fetchall()
        tags = {r["tag_text"].lower() for r in tag_rows}

        if not tags:
            clusters["unassigned"].append(dict(row))
            continue

        cluster = _assign_cluster(tags)
        clusters[cluster].append(dict(row))

    return clusters


def analyze_balance(db: Database, target_shape: dict[str, float] | None = None) -> dict:
    """
    Analyze library balance and return a report dict.

    If target_shape is provided, compute shape_score (how close to the
    desired distribution shape) alongside classic entropy score.

    Returns:
        {
            "total": int,
            "clusters": {name: {"count": int, "pct": float, "deficit": int}},
            "entropy": float,
            "max_entropy": float,
            "balance_score": float,   # shape_score if shape provided, else entropy ratio
            "entropy_score": float,   # always the classic entropy ratio
            "shape_name": str,        # name of active shape
            "shape_weights": dict,    # the target shape weights
            "underrepresented": [{"cluster": str, "count": int, "deficit": int}],
        }
    """
    dist = get_cluster_distribution(db)
    active_clusters = {k: v for k, v in dist.items() if k != "unassigned"}

    total = sum(len(v) for v in active_clusters.values())
    n_clusters = len(active_clusters)

    if total == 0:
        return {
            "total": 0,
            "clusters": {},
            "entropy": 0.0,
            "max_entropy": 0.0,
            "balance_score": 0.0,
            "entropy_score": 0.0,
            "shape_name": "uniform",
            "shape_weights": {},
            "underrepresented": [],
        }

    # Default shape: uniform (all 1.0)
    if target_shape is None:
        target_shape = {name: 1.0 for name in active_clusters}

    # Per-cluster stats using shape-aware targets
    ideal_uniform = total / n_clusters
    cluster_stats = {}
    actual_counts = {}
    for name, assets in active_clusters.items():
        count = len(assets)
        actual_counts[name] = count
        pct = count / total * 100 if total > 0 else 0.0
        shape_w = target_shape.get(name, 1.0)
        shaped_ideal = ideal_uniform * shape_w
        deficit = max(0, round(shaped_ideal - count))
        cluster_stats[name] = {"count": count, "pct": pct, "deficit": deficit}

    # Shannon entropy
    entropy = 0.0
    for name, assets in active_clusters.items():
        p = len(assets) / total if total > 0 else 0.0
        if p > 0:
            entropy -= p * math.log2(p)

    max_entropy = math.log2(n_clusters) if n_clusters > 0 else 0.0
    entropy_score_val = entropy / max_entropy if max_entropy > 0 else 0.0

    # Shape score: how close to the target shape
    s_score = shape_score(actual_counts, target_shape)

    # Use shape score as the primary balance score
    balance = s_score

    # Find underrepresented clusters (deficit > 5)
    underrepresented = []
    for name in sorted(cluster_stats, key=lambda n: cluster_stats[n]["count"]):
        if cluster_stats[name]["deficit"] > 5:
            underrepresented.append({
                "cluster": name,
                "count": cluster_stats[name]["count"],
                "deficit": cluster_stats[name]["deficit"],
            })

    return {
        "total": total,
        "clusters": cluster_stats,
        "entropy": entropy,
        "max_entropy": max_entropy,
        "balance_score": balance,
        "entropy_score": entropy_score_val,
        "shape_name": name_shape(target_shape),
        "shape_weights": target_shape,
        "underrepresented": underrepresented,
    }


def print_balance_report(report: dict):
    """Pretty-print the balance report."""
    print(f"\n{'='*60}")
    print(f"  LIBRARY BALANCE REPORT")
    print(f"{'='*60}")
    print(f"  Total assets: {report['total']}")
    print(f"  Entropy:      {report['entropy']:.3f} / {report['max_entropy']:.3f}  ({report.get('entropy_score', 0):.1%})")
    print(f"  Shape:        {report.get('shape_name', 'uniform')}")
    print(f"  Shape score:  {report['balance_score']:.1%}")
    print()

    # Sort by count descending
    for name in sorted(report["clusters"], key=lambda n: -report["clusters"][n]["count"]):
        s = report["clusters"][name]
        bar_len = int(s["pct"] / 2)  # 50 chars = 100%
        bar = "█" * bar_len
        deficit_str = f"  (need +{s['deficit']})" if s["deficit"] > 0 else ""
        print(f"  {name:<20s} {s['count']:>4d}  {s['pct']:5.1f}%  {bar}{deficit_str}")

    if report["underrepresented"]:
        print(f"\n  ⚠  Under-represented clusters:")
        for item in report["underrepresented"]:
            print(f"     {item['cluster']}: {item['count']} sounds (need +{item['deficit']} to reach balanced)")
    else:
        print(f"\n  ✓  All clusters are reasonably balanced")

    print(f"{'='*60}\n")


def compute_rebalance_plan(report: dict, target_shape: dict[str, float] | None = None) -> list[dict]:
    """
    Given a balance report, compute which queries to run.

    Uses the shape-aware deficits already in the report (computed from
    target_shape in analyze_balance). If target_shape is additionally
    provided here, recompute targets explicitly.

    Returns list of {"query": str, "category": str, "cluster": str, "limit": int}
    """
    plan = []
    clusters = report.get("clusters", {})
    total = report.get("total", 0)
    n_clusters = len(clusters)
    if n_clusters == 0:
        return plan

    uniform_ideal = total / n_clusters

    for name in sorted(clusters, key=lambda n: clusters[n]["count"]):
        count = clusters[name]["count"]
        if target_shape:
            shape_w = target_shape.get(name, 1.0)
            target = uniform_ideal * shape_w
            deficit = round(target - count)
        else:
            deficit = clusters[name].get("deficit", 0)
        if deficit <= 0:
            continue
        queries = CLUSTER_QUERIES.get(name, [])
        if not queries:
            continue
        per_query = max(3, math.ceil(deficit / len(queries)))
        for q in queries:
            plan.append({
                "query": q["query"],
                "category": q["category"],
                "cluster": name,
                "limit": per_query,
            })

    return plan


# ── Target balance score ────────────────────────────────────────────────────
TARGET_BALANCE = 0.98          # stop when entropy ratio >= 98%
MAX_ROUNDS = 20                # absolute safety cap
STALE_ROUNDS_LIMIT = 3         # stop after N consecutive 0-ingest rounds


def _print(msg: str = ""):
    """Print with immediate flush so GUI subprocess output is live."""
    print(msg, flush=True)


def run_rebalance(auto_tag: bool = False):
    """
    Fully-autonomous rebalance loop.

    Analyse → plan → search/download/tag → repeat
    until balance >= TARGET_BALANCE or sources are exhausted.
    """
    from harvest_sounds import build_pipeline, log_harvest
    from datetime import datetime, timezone

    db = get_db()
    pipeline = build_pipeline(auto_tag=auto_tag)
    available_sources = list(pipeline._connectors.keys())

    total_ingested = 0
    stale_streak = 0           # consecutive rounds with 0 new sounds

    for round_num in range(1, MAX_ROUNDS + 1):
        # ── analyse ─────────────────────────────────────────────────
        report = analyze_balance(db)
        balance = report["balance_score"]

        _print(f"\n{'='*60}")
        _print(f"  ROUND {round_num}/{MAX_ROUNDS}  |  shape={report.get('shape_name', 'uniform')}  |  score={balance:.1%}  |  total={report['total']}")
        _print(f"{'='*60}")

        if balance >= TARGET_BALANCE:
            _print(f"[rebalance] ✓ shape score {balance:.1%} >= {TARGET_BALANCE:.0%} target — done!")
            break

        plan = compute_rebalance_plan(report)
        if not plan:
            _print("[rebalance] ✓ all clusters at or above ideal — done!")
            break

        # Show what we're targeting this round
        seen_clusters: dict[str, int] = {}
        for entry in plan:
            seen_clusters[entry["cluster"]] = seen_clusters.get(entry["cluster"], 0) + entry["limit"]
        for cluster, total_need in seen_clusters.items():
            c = report["clusters"][cluster]
            _print(f"  → {cluster}: {c['count']} now, targeting +{total_need}")

        # ── harvest ─────────────────────────────────────────────────
        round_ingested = 0
        for entry in plan:
            cluster = entry["cluster"]
            query_text = entry["query"]
            limit = entry["limit"]

            for source in available_sources:
                _print(f"  [{cluster}] '{query_text}' via {source} (limit={limit}, page={round_num})")

                try:
                    count = pipeline.run(
                        query=query_text, source_name=source,
                        limit=limit, page=round_num,
                    )
                    round_ingested += count
                    if count > 0:
                        _print(f"    ✓ +{count} new sounds")
                    log_harvest({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "query": query_text,
                        "source": source,
                        "category": entry["category"],
                        "cluster_target": cluster,
                        "limit": limit,
                        "page": round_num,
                        "ingested": count,
                        "status": "ok",
                        "trigger": "rebalance",
                    })
                except Exception as e:
                    _print(f"    ERROR: {e}")
                    log_harvest({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "query": query_text,
                        "source": source,
                        "category": entry["category"],
                        "cluster_target": cluster,
                        "limit": limit,
                        "page": round_num,
                        "ingested": 0,
                        "status": "error",
                        "error": str(e),
                        "trigger": "rebalance",
                    })

        total_ingested += round_ingested
        _print(f"\n  round {round_num}: +{round_ingested} this round, {total_ingested} total")

        # Track stale rounds — but keep going for a few rounds because
        # the next page might have fresh results
        if round_ingested == 0:
            stale_streak += 1
            _print(f"  (stale round {stale_streak}/{STALE_ROUNDS_LIMIT})")
            if stale_streak >= STALE_ROUNDS_LIMIT:
                _print("[rebalance] sources exhausted — stopping")
                break
        else:
            stale_streak = 0

    # ── final report ────────────────────────────────────────────────
    _print(f"\n{'='*60}")
    _print(f"  REBALANCE COMPLETE — {total_ingested} new sounds ingested")
    _print(f"{'='*60}")
    report = analyze_balance(db)
    print_balance_report(report)


def main():
    parser = argparse.ArgumentParser(description="Becoming library balance analyzer")
    parser.add_argument("--rebalance", action="store_true",
                        help="Auto-harvest to fill underrepresented clusters until balanced")
    parser.add_argument("--auto-tag", action="store_true",
                        help="LLM-tag newly harvested sounds")
    args = parser.parse_args()

    if not args.rebalance:
        db = get_db()
        report = analyze_balance(db)
        print_balance_report(report)
        return

    run_rebalance(auto_tag=args.auto_tag)


if __name__ == "__main__":
    main()
