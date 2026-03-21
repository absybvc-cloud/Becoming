#!/usr/bin/env python3
"""
Library balance analyzer and auto-rebalance harvester for Becoming.

Scans cluster distribution, identifies under-represented clusters,
and triggers targeted harvest queries to fill gaps.

Usage:
    python balance.py                    # analyze current balance
    python balance.py --rebalance        # analyze + auto-harvest to fill gaps
    python balance.py --rebalance --limit 5   # limit per rebalance query
    python balance.py --auto-tag         # also LLM-tag newly harvested sounds
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


def analyze_balance(db: Database) -> dict:
    """
    Analyze library balance and return a report dict.

    Returns:
        {
            "total": int,
            "clusters": {name: {"count": int, "pct": float, "deficit": int}},
            "entropy": float,
            "max_entropy": float,
            "balance_score": float,   # 0-1, 1 = perfectly balanced
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
            "underrepresented": [],
        }

    # Ideal: equal distribution across clusters
    ideal_per_cluster = total / n_clusters

    # Per-cluster stats
    cluster_stats = {}
    for name, assets in active_clusters.items():
        count = len(assets)
        pct = count / total * 100 if total > 0 else 0.0
        deficit = max(0, round(ideal_per_cluster - count))
        cluster_stats[name] = {"count": count, "pct": pct, "deficit": deficit}

    # Shannon entropy of distribution (higher = more diverse)
    entropy = 0.0
    for name, assets in active_clusters.items():
        p = len(assets) / total if total > 0 else 0.0
        if p > 0:
            entropy -= p * math.log2(p)

    max_entropy = math.log2(n_clusters) if n_clusters > 0 else 0.0
    balance_score = entropy / max_entropy if max_entropy > 0 else 0.0

    # Find underrepresented clusters (< 60% of ideal)
    threshold = ideal_per_cluster * 0.6
    underrepresented = []
    for name in sorted(cluster_stats, key=lambda n: cluster_stats[n]["count"]):
        count = cluster_stats[name]["count"]
        if count < threshold:
            underrepresented.append({
                "cluster": name,
                "count": count,
                "deficit": cluster_stats[name]["deficit"],
            })

    return {
        "total": total,
        "clusters": cluster_stats,
        "entropy": entropy,
        "max_entropy": max_entropy,
        "balance_score": balance_score,
        "underrepresented": underrepresented,
    }


def print_balance_report(report: dict):
    """Pretty-print the balance report."""
    print(f"\n{'='*60}")
    print(f"  LIBRARY BALANCE REPORT")
    print(f"{'='*60}")
    print(f"  Total assets: {report['total']}")
    print(f"  Entropy:      {report['entropy']:.3f} / {report['max_entropy']:.3f}")
    print(f"  Balance:      {report['balance_score']:.1%}")
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


def compute_rebalance_plan(report: dict, limit_per_query: int = 5) -> list[dict]:
    """
    Given a balance report, compute which queries to run and how many
    results to fetch from each.

    Returns list of {"query": str, "category": str, "cluster": str, "limit": int}
    """
    plan = []

    for item in report.get("underrepresented", []):
        cluster = item["cluster"]
        deficit = item["deficit"]
        queries = CLUSTER_QUERIES.get(cluster, [])
        if not queries:
            continue

        # Distribute deficit evenly across queries for this cluster
        per_query = max(1, math.ceil(deficit / len(queries)))
        # Cap at the given limit
        per_query = min(per_query, limit_per_query)

        for q in queries:
            plan.append({
                "query": q["query"],
                "category": q["category"],
                "cluster": cluster,
                "limit": per_query,
            })

    return plan


def run_rebalance(
    plan: list[dict],
    auto_tag: bool = False,
    dry_run: bool = False,
):
    """Execute the rebalance plan by running harvest queries."""
    if not plan:
        print("[rebalance] nothing to do — library is balanced")
        return

    if dry_run:
        print("[rebalance] DRY RUN — planned queries:\n")
        for entry in plan:
            print(f"  cluster={entry['cluster']:<20s} query='{entry['query']}'  limit={entry['limit']}")
        print(f"\n[rebalance] total queries: {len(plan)}")
        return

    # Import harvest machinery
    from harvest_sounds import build_pipeline, log_harvest, DEFAULT_SOURCES
    from datetime import datetime, timezone

    pipeline = build_pipeline(auto_tag=auto_tag)
    available_sources = list(pipeline._connectors.keys())

    total_ingested = 0
    total_queries = 0

    for entry in plan:
        cluster = entry["cluster"]
        query_text = entry["query"]
        limit = entry["limit"]

        for source in available_sources:
            total_queries += 1
            print(f"\n[rebalance] cluster={cluster} query='{query_text}' source={source} limit={limit}")

            try:
                count = pipeline.run(query=query_text, source_name=source, limit=limit)
                total_ingested += count
                log_harvest({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "query": query_text,
                    "source": source,
                    "category": entry["category"],
                    "cluster_target": cluster,
                    "limit": limit,
                    "ingested": count,
                    "status": "ok",
                    "trigger": "rebalance",
                })
            except Exception as e:
                print(f"[rebalance] ERROR: {e}")
                log_harvest({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "query": query_text,
                    "source": source,
                    "category": entry["category"],
                    "cluster_target": cluster,
                    "limit": limit,
                    "ingested": 0,
                    "status": "error",
                    "error": str(e),
                    "trigger": "rebalance",
                })

    print(f"\n{'='*60}")
    print(f"[rebalance] COMPLETE")
    print(f"  queries run:   {total_queries}")
    print(f"  total ingested: {total_ingested}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Becoming library balance analyzer")
    parser.add_argument("--rebalance", action="store_true",
                        help="Auto-harvest to fill underrepresented clusters")
    parser.add_argument("--limit", type=int, default=5,
                        help="Max results per rebalance query per source (default: 5)")
    parser.add_argument("--auto-tag", action="store_true",
                        help="LLM-tag newly harvested sounds")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show plan without downloading")
    args = parser.parse_args()

    db = get_db()
    report = analyze_balance(db)
    print_balance_report(report)

    if args.rebalance:
        plan = compute_rebalance_plan(report, limit_per_query=args.limit)
        if args.dry_run:
            run_rebalance(plan, dry_run=True)
        else:
            if plan:
                print(f"[rebalance] executing {len(plan)} targeted queries...")
                if args.auto_tag:
                    print("[rebalance] auto-tag enabled")
            run_rebalance(plan, auto_tag=args.auto_tag, dry_run=False)

            # Re-analyze after rebalance
            print("\n[rebalance] post-harvest balance:")
            report2 = analyze_balance(db)
            print_balance_report(report2)


if __name__ == "__main__":
    main()
