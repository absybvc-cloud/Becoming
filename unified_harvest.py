#!/usr/bin/env python3
"""
Unified Harvest Engine — Adaptive Library Expansion for Becoming.

Merges deficit-driven rebalance with desire-driven query generation
into a single system that balances the library while continuously
destabilizing it through intelligent search.

Modes:
    balance — pure deficit-driven, minimal drift
    drift   — pure desire-driven, high mutation
    hybrid  — blend both (default)

Usage:
    python unified_harvest.py                          # hybrid mode
    python unified_harvest.py --mode balance            # pure rebalance
    python unified_harvest.py --mode drift              # pure drift
    python unified_harvest.py --dry-run                 # preview plan
    python unified_harvest.py --max-queries 6 --limit 8 # tuning
"""

from __future__ import annotations

import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from balance import analyze_balance, get_db
from harvest_sounds import build_pipeline, log_harvest
from query_generator import (
    QueryGenerator, QueryConfig, DesireState, SEMANTIC_MAP,
)
from src.engine.vectors import CLUSTER_DEFS

# Sources that use full-text search (need shorter queries)
_FULLTEXT_SOURCES = {"internet_archive", "wikimedia"}


def _shorten_query(query: str, max_words: int = 2) -> str:
    """Trim a long poetic query to its core words for full-text search APIs."""
    # Remove common filler words, keep the most distinctive terms
    _FILLER = {
        "a", "an", "the", "of", "in", "on", "and", "or", "with", "for",
        "to", "from", "by", "into", "through", "between", "at", "its",
        "slow", "soft", "gentle", "abstract", "evolving", "gradual",
        "endless", "wandering", "floating", "background",
    }
    words = [w for w in query.lower().split() if w not in _FILLER]
    if not words:
        words = query.split()[:max_words]
    return " ".join(words[:max_words])


# ── Configuration ───────────────────────────────────────────────────────────

MODES = ("balance", "hybrid", "drift")

@dataclass
class HarvestConfig:
    mode: str = "hybrid"
    max_queries: int = 9
    target_total: int = 50           # total sounds to ingest into DB
    intensity: float = 0.5          # 0–1, scales how aggressively to fill
    drift_amount: float = 0.3       # 0–1, semantic mutation strength
    auto_tag: bool = True
    max_rounds: int = 10
    target_score: float = 0.98
    stale_limit: int = 3

    @property
    def limit_per_query(self) -> int:
        """Derive per-query limit from total target and query count.
        Over-request by 2× to account for dupes/filters."""
        return max(5, math.ceil(self.target_total * 2 / max(1, self.max_queries)))

    # Scoring weights (mode-dependent defaults applied in _mode_weights)
    deficit_weight: float = 1.0
    novelty_weight: float = 0.4
    fatigue_weight: float = 0.3
    drift_bias: float = 0.1


def _mode_weights(cfg: HarvestConfig) -> HarvestConfig:
    """Adjust scoring weights based on mode."""
    if cfg.mode == "balance":
        cfg.deficit_weight = 1.0
        cfg.novelty_weight = 0.1
        cfg.fatigue_weight = 0.1
        cfg.drift_bias = 0.0
        cfg.drift_amount = 0.05
    elif cfg.mode == "drift":
        cfg.deficit_weight = 0.2
        cfg.novelty_weight = 0.8
        cfg.fatigue_weight = 0.5
        cfg.drift_bias = 0.4
        cfg.drift_amount = 0.8
    # hybrid keeps user-supplied or default values
    return cfg


# ── Harvest State (persists across rounds) ──────────────────────────────────

@dataclass
class FocusState:
    """Temporary obsession with a single cluster."""
    active: bool = False
    cluster: str | None = None
    started_at: float = 0.0
    duration: float = 0.0
    intensity: float = 1.0
    cooldown_until: float = 0.0  # timestamp when re-focus is allowed


@dataclass
class CollapseState:
    """Forced reset — suppresses the dominant cluster."""
    active: bool = False
    triggered_at: float = 0.0
    duration: float = 0.0
    target_cluster: str | None = None


@dataclass
class HarvestState:
    """Tracks novelty and fatigue across harvest cycles."""
    last_harvested: dict[str, float] = field(default_factory=dict)   # cluster → timestamp
    harvest_counts: dict[str, int] = field(default_factory=dict)     # cluster → recent count
    total_ingested: int = 0
    round_num: int = 0
    stop_requested: bool = False

    # Focus / Collapse / Saturation
    focus: FocusState = field(default_factory=FocusState)
    collapse: CollapseState = field(default_factory=CollapseState)
    saturation: dict[str, float] = field(default_factory=dict)       # cluster → 0.0–1.0

    def record_harvest(self, cluster: str, count: int):
        self.last_harvested[cluster] = time.time()
        self.harvest_counts[cluster] = self.harvest_counts.get(cluster, 0) + count
        self.total_ingested += count

    def novelty_score(self, cluster: str) -> float:
        """Higher score for clusters not recently harvested."""
        last = self.last_harvested.get(cluster, 0.0)
        if last == 0.0:
            return 1.0
        elapsed = time.time() - last
        return min(1.0, elapsed / 3600.0)  # saturates at 1h

    def fatigue_score(self, cluster: str) -> float:
        """Higher score for clusters harvested many times recently."""
        count = self.harvest_counts.get(cluster, 0)
        return min(1.0, count / 30.0)  # saturates at 30 harvests


def _print(msg: str = ""):
    print(msg, flush=True)


# ── Focus / Collapse / Saturation ───────────────────────────────────────────

def activate_focus(
    state: HarvestState,
    scores: dict[str, float],
    force: bool = False,
) -> None:
    """Enter focus mode — lock onto a single cluster with amplified intensity."""
    now = time.time()
    if state.focus.active and not force:
        return
    if now < state.focus.cooldown_until and not force:
        _print("[focus] still in cooldown")
        return

    # Weighted sample from cluster scores
    candidates = list(scores.keys())
    weights = [max(0.01, scores.get(c, 0)) for c in candidates]
    cluster = random.choices(candidates, weights=weights, k=1)[0]

    state.focus.active = True
    state.focus.cluster = cluster
    state.focus.started_at = now
    state.focus.duration = random.uniform(600, 1800)
    state.focus.intensity = random.uniform(2.0, 4.0)
    _print(f"[focus] cluster={cluster} intensity={state.focus.intensity:.1f} duration={state.focus.duration:.0f}s")


def _end_focus(state: HarvestState) -> None:
    """Deactivate focus and enter cooldown."""
    _print(f"[focus] ended (cluster={state.focus.cluster})")
    state.focus.active = False
    state.focus.cooldown_until = time.time() + random.uniform(300, 900)


def update_saturation(
    state: HarvestState,
    report: dict,
) -> None:
    """Recompute per-cluster saturation from presence, usage, and dominance."""
    clusters = report.get("clusters", {})
    total = max(1, report.get("total", 1))
    max_count = max((c.get("count", 0) for c in clusters.values()), default=1) or 1

    for name, info in clusters.items():
        normalized_presence = info.get("count", 0) / total
        recent_usage = min(1.0, state.harvest_counts.get(name, 0) / 30.0)
        dominance = info.get("count", 0) / max_count
        sat = 0.4 * normalized_presence + 0.4 * recent_usage + 0.2 * dominance
        state.saturation[name] = round(min(1.0, sat), 3)

    # Log top saturated clusters
    top = sorted(state.saturation.items(), key=lambda x: -x[1])[:3]
    parts = " ".join(f"{c}={v:.2f}" for c, v in top)
    _print(f"[saturation] {parts}")


def trigger_collapse(state: HarvestState, cluster: str | None = None) -> None:
    """Force collapse on a cluster (or the current focus / dominant)."""
    target = cluster
    if not target and state.focus.active:
        target = state.focus.cluster
    if not target and state.saturation:
        target = max(state.saturation, key=state.saturation.get)
    if not target:
        _print("[collapse] no target — skipped")
        return

    state.collapse.active = True
    state.collapse.triggered_at = time.time()
    state.collapse.duration = random.uniform(60, 240)
    state.collapse.target_cluster = target
    state.focus.active = False
    _print(f"[collapse] triggered_by={target} duration={state.collapse.duration:.0f}s")


def _check_focus_collapse_lifecycle(state: HarvestState) -> None:
    """Tick lifecycle: auto-end focus/collapse when their duration expires,
    and auto-trigger collapse when saturation exceeds threshold."""
    now = time.time()

    # Focus expiry
    if state.focus.active and now > state.focus.started_at + state.focus.duration:
        _end_focus(state)

    # Collapse expiry
    if state.collapse.active and now > state.collapse.triggered_at + state.collapse.duration:
        _print("[collapse] ended")
        state.collapse.active = False

    # Auto-collapse if focused cluster is saturated
    if state.focus.active and state.focus.cluster:
        sat = state.saturation.get(state.focus.cluster, 0.0)
        if sat > 0.75:
            _print(f"[collapse] auto — {state.focus.cluster} saturation={sat:.2f}")
            trigger_collapse(state, state.focus.cluster)


# ── Deficit Analysis (spec §6) ──────────────────────────────────────────────

def compute_deficits(report: dict) -> dict[str, float]:
    """
    Normalized deficit scores from a balance report.
    Returns {cluster: 0.0–1.0} where 1.0 = most underrepresented.
    """
    clusters = report.get("clusters", {})
    raw = {c: max(0.0, float(d.get("deficit", 0))) for c, d in clusters.items()}
    total = sum(raw.values())
    if total == 0:
        return {c: 0.0 for c in raw}
    return {c: v / total for c, v in raw.items()}


# ── Cluster Scoring (spec §7) ───────────────────────────────────────────────

def score_clusters(
    deficits: dict[str, float],
    state: HarvestState,
    cfg: HarvestConfig,
) -> dict[str, float]:
    """
    Compute a composite score per cluster blending:
      deficit × deficit_weight
    + novelty × novelty_weight
    - fatigue × fatigue_weight
    + drift_bias (random walk)
    + focus boost / collapse suppression
    """
    scores: dict[str, float] = {}
    for cluster in deficits:
        deficit = deficits[cluster]
        novelty = state.novelty_score(cluster)
        fatigue = state.fatigue_score(cluster)
        drift = cfg.drift_bias * random.uniform(-0.5, 0.5)

        score = (
            cfg.deficit_weight * deficit
            + cfg.novelty_weight * novelty
            - cfg.fatigue_weight * fatigue
            + drift
        )

        # Focus: amplify the focused cluster
        if state.focus.active and cluster == state.focus.cluster:
            score *= state.focus.intensity

        # Collapse: suppress the target cluster
        if state.collapse.active and cluster == state.collapse.target_cluster:
            score *= 0.1

        scores[cluster] = max(0.0, score)

    return scores


# ── Cluster Selection (spec §8) ─────────────────────────────────────────────

def select_clusters(
    scores: dict[str, float],
    k: int,
) -> list[str]:
    """
    Weighted sample of k clusters from scores.
    Clusters with score 0 are excluded unless all are 0.
    """
    candidates = [c for c, s in scores.items() if s > 0]
    if not candidates:
        candidates = list(scores.keys())
    weights = [scores.get(c, 0.01) for c in candidates]
    # Allow duplicates only via random.choices (high-deficit clusters can repeat)
    selected = random.choices(candidates, weights=weights, k=min(k, len(candidates) * 2))
    return selected


# ── Plan Builder (spec §10) ─────────────────────────────────────────────────

def build_harvest_plan(
    report: dict,
    scores: dict[str, float],
    cfg: HarvestConfig,
    state: HarvestState | None = None,
) -> list[dict]:
    """
    Build a harvest plan: select clusters, generate queries, set target counts.

    Returns list of {
        "cluster": str,
        "query": str,
        "target_count": int,
        "priority": float,
    }
    """
    clusters_info = report.get("clusters", {})
    total_score = sum(scores.values()) or 1.0

    # Select which clusters to harvest this round
    selected = select_clusters(scores, k=cfg.max_queries)

    # Build query generator with drift-tuned config
    qg_config = QueryConfig(
        mutation_rate=0.3 + cfg.drift_amount * 0.5,  # 0.3–0.8
        cross_cluster_probability=0.2 + cfg.drift_amount * 0.4,  # 0.2–0.6
    )
    qg = QueryGenerator(config=qg_config)

    plan: list[dict] = []
    for cluster in selected:
        deficit = clusters_info.get(cluster, {}).get("deficit", 0)
        priority = scores.get(cluster, 0.0) / total_score

        # Target count: use full per-query limit, priority only boosts
        base = cfg.limit_per_query
        target_count = max(5, round(base * (0.5 + 0.5 * priority / max(0.01, max(scores.values()) / total_score))))

        # Focus: boost target count for focused cluster
        if state and state.focus.active and cluster == state.focus.cluster:
            target_count = round(target_count * random.uniform(1.5, 2.5))

        # Collapse: reduce target count globally during collapse
        if state and state.collapse.active:
            target_count = max(3, round(target_count * 0.5))

        # Generate a desire state for this cluster
        desire = DesireState(
            focus_cluster=cluster,
            state="drifting",
            tension=cfg.intensity,
            density=0.5,
            desires=scores,
            phase="drift" if cfg.mode == "drift" else "stabilize",
        )

        # Pass focus/collapse context to the query generator
        if state and state.collapse.active:
            desire.phase = "collapse"
            if state.collapse.target_cluster:
                desire.fatigue[state.collapse.target_cluster] = 1.0
        if state and state.focus.active and state.focus.cluster:
            desire.focus_cluster = state.focus.cluster

        query = qg.generate(desire)

        plan.append({
            "cluster": cluster,
            "query": query,
            "target_count": target_count,
            "priority": round(priority, 3),
        })

    return plan


# ── Execution Engine (spec §11) ─────────────────────────────────────────────

def run_unified_harvest(
    cfg: HarvestConfig | None = None,
    state: HarvestState | None = None,
) -> HarvestState:
    """
    Main entry point.  Analyse → score → plan → harvest → repeat.
    Returns the final HarvestState.
    """
    if cfg is None:
        cfg = HarvestConfig()
    cfg = _mode_weights(cfg)

    if state is None:
        state = HarvestState()

    db = get_db()
    pipeline = build_pipeline(auto_tag=cfg.auto_tag)
    available_sources = list(pipeline._connectors.keys())
    stale_streak = 0

    for round_num in range(1, cfg.max_rounds + 1):
        if state.stop_requested:
            _print("[harvest] stopped by user")
            break

        state.round_num = round_num

        # ── Analyse ─────────────────────────────────────────────────
        report = analyze_balance(db)
        balance = report["balance_score"]

        _print(f"\n{'='*60}")
        _print(f"  ROUND {round_num}/{cfg.max_rounds}  |  mode={cfg.mode}  |  score={balance:.1%}  |  total={report['total']}")
        _print(f"  target: {cfg.target_total} sounds  |  ingested so far: {state.total_ingested}")
        _print(f"{'='*60}")

        if state.total_ingested >= cfg.target_total:
            _print(f"[harvest] ✓ reached target ({state.total_ingested}/{cfg.target_total}) — done!")
            break

        if balance >= cfg.target_score and cfg.mode != "drift":
            _print(f"[harvest] ✓ score {balance:.1%} >= {cfg.target_score:.0%} — done!")
            break

        # ── Score + Plan ────────────────────────────────────────────
        deficits = compute_deficits(report)

        # Focus/collapse lifecycle tick
        _check_focus_collapse_lifecycle(state)
        update_saturation(state, report)

        # Auto-activate focus in drift / hybrid modes
        if not state.focus.active and not state.collapse.active:
            if cfg.mode == "drift":
                activate_focus(state, deficits, force=False)
            elif cfg.mode == "hybrid" and random.random() < cfg.drift_amount:
                activate_focus(state, deficits, force=False)

        scores = score_clusters(deficits, state, cfg)
        plan = build_harvest_plan(report, scores, cfg, state=state)

        if not plan:
            _print("[harvest] no clusters need attention — done!")
            break

        # Log the plan
        cluster_set = sorted(set(p["cluster"] for p in plan))
        _print(f"  mode={cfg.mode}")
        _print(f"  selected_clusters={cluster_set}")
        for p in plan:
            _print(f"    [{p['cluster']}] \"{p['query']}\" target={p['target_count']} pri={p['priority']}")

        # ── Execute ─────────────────────────────────────────────────
        round_ingested = 0
        remaining = cfg.target_total - state.total_ingested
        for i, task in enumerate(plan, 1):
            if state.stop_requested:
                _print("[harvest] stopped mid-round")
                break
            if state.total_ingested >= cfg.target_total:
                _print(f"[harvest] ✓ reached target ({state.total_ingested}/{cfg.target_total})")
                break

            cluster = task["cluster"]
            query_text = task["query"]
            limit = min(task["target_count"], cfg.target_total - state.total_ingested)

            for source in available_sources:
                if state.stop_requested:
                    break

                # Shorten query for full-text search APIs
                q = _shorten_query(query_text) if source in _FULLTEXT_SOURCES else query_text
                _print(f"  ({i}/{len(plan)}) [{cluster}] '{q}' via {source} limit={limit}")
                try:
                    count = pipeline.run(
                        query=q, source_name=source,
                        limit=limit, page=round_num,
                    )
                    round_ingested += count
                    state.record_harvest(cluster, count)
                    if count > 0:
                        _print(f"    ✓ +{count}")
                    log_harvest({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "query": query_text,
                        "source": source,
                        "cluster_target": cluster,
                        "limit": limit,
                        "page": round_num,
                        "ingested": count,
                        "status": "ok",
                        "trigger": f"unified_{cfg.mode}",
                    })
                except Exception as e:
                    _print(f"    ERROR: {e}")
                    log_harvest({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "query": query_text,
                        "source": source,
                        "cluster_target": cluster,
                        "limit": limit,
                        "page": round_num,
                        "ingested": 0,
                        "status": "error",
                        "error": str(e),
                        "trigger": f"unified_{cfg.mode}",
                    })

        _print(f"\n  round {round_num}: +{round_ingested} this round, {state.total_ingested} total")

        if round_ingested == 0:
            stale_streak += 1
            _print(f"  (stale {stale_streak}/{cfg.stale_limit})")
            if stale_streak >= cfg.stale_limit:
                _print("[harvest] sources exhausted — stopping")
                break
        else:
            stale_streak = 0

    # ── Final report ────────────────────────────────────────────────
    _print(f"\n{'='*60}")
    _print(f"  UNIFIED HARVEST COMPLETE — {state.total_ingested} sounds ingested")
    _print(f"{'='*60}")
    from balance import print_balance_report
    report = analyze_balance(db)
    print_balance_report(report)

    return state


# ── Dry-Run Preview ─────────────────────────────────────────────────────────

def preview_plan(cfg: HarvestConfig | None = None, state: HarvestState | None = None):
    """Show what would happen without downloading anything."""
    if cfg is None:
        cfg = HarvestConfig()
    cfg = _mode_weights(cfg)
    if state is None:
        state = HarvestState()

    db = get_db()
    report = analyze_balance(db)
    deficits = compute_deficits(report)
    scores = score_clusters(deficits, state, cfg)
    plan = build_harvest_plan(report, scores, cfg, state=state)

    _print(f"\n{'='*60}")
    _print(f"  DRY RUN — mode={cfg.mode}  score={report['balance_score']:.1%}  total={report['total']}  target={cfg.target_total}")
    _print(f"{'='*60}")

    if not plan:
        _print("  nothing to harvest")
        return

    _print(f"  {len(plan)} queries across {len(set(p['cluster'] for p in plan))} clusters\n")
    for i, p in enumerate(plan, 1):
        _print(f"  {i:>2}. [{p['cluster']:<20s}] \"{p['query']}\"  target={p['target_count']}  pri={p['priority']}")

    _print(f"\n{'='*60}\n")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Becoming unified harvest engine")
    parser.add_argument("--mode", choices=MODES, default="hybrid")
    parser.add_argument("--max-queries", type=int, default=9)
    parser.add_argument("--limit", type=int, default=50,
                        help="total sounds to ingest into DB")
    parser.add_argument("--intensity", type=float, default=0.5)
    parser.add_argument("--drift", type=float, default=0.3)
    parser.add_argument("--max-rounds", type=int, default=5)
    parser.add_argument("--auto-tag", action="store_true", default=True)
    parser.add_argument("--no-auto-tag", dest="auto_tag", action="store_false")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--focus", action="store_true",
                        help="force-activate focus mode")
    parser.add_argument("--collapse", action="store_true",
                        help="force-trigger collapse")
    args = parser.parse_args()

    cfg = HarvestConfig(
        mode=args.mode,
        max_queries=args.max_queries,
        target_total=args.limit,
        intensity=args.intensity,
        drift_amount=args.drift,
        auto_tag=args.auto_tag,
        max_rounds=args.max_rounds,
    )

    state = HarvestState()
    if args.focus:
        cfg = _mode_weights(cfg)
        db = get_db()
        report = analyze_balance(db)
        deficits = compute_deficits(report)
        activate_focus(state, deficits, force=True)
    if args.collapse:
        trigger_collapse(state)

    if args.dry_run:
        preview_plan(cfg, state=state)
    else:
        run_unified_harvest(cfg, state=state)


if __name__ == "__main__":
    main()
