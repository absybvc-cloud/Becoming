#!/usr/bin/env python3
"""
Balance Shapes — target distribution shapes for Becoming.

Instead of always targeting a uniform distribution, the system pursues
a time-varying "shape" that defines what "balanced" means right now.

Shapes are dicts mapping cluster_name → weight multiplier (avg = 1.0).
"""

from __future__ import annotations

import math
from typing import Optional


# ── Built-in Shape Definitions ──────────────────────────────────────────────

def _uniform(clusters: list[str]) -> dict[str, float]:
    return {c: 1.0 for c in clusters}


def _convergent(clusters: list[str], focus: str) -> dict[str, float]:
    """One cluster dominates, others recede."""
    shape = {c: 0.6 for c in clusters}
    shape[focus] = 2.5
    # Neighbors get a mild boost (adjacent in sorted order as proxy)
    sc = sorted(clusters)
    if focus in sc:
        idx = sc.index(focus)
        for offset in (-1, 1):
            ni = idx + offset
            if 0 <= ni < len(sc):
                shape[sc[ni]] = 1.2
    return _normalize(shape)


def _bipolar(clusters: list[str], pole_a: str, pole_b: str) -> dict[str, float]:
    """Two opposing poles, hollow middle."""
    shape = {c: 0.5 for c in clusters}
    shape[pole_a] = 2.0
    shape[pole_b] = 2.0
    return _normalize(shape)


def _cascade(clusters: list[str], ranking: list[str]) -> dict[str, float]:
    """Descending gradient from most to least desired."""
    n = len(ranking)
    shape = {}
    for i, c in enumerate(ranking):
        shape[c] = 2.0 - (1.5 * i / max(1, n - 1))  # 2.0 → 0.5
    # Include any clusters not in ranking
    for c in clusters:
        if c not in shape:
            shape[c] = 0.5
    return _normalize(shape)


def _hollow(clusters: list[str], suppress: list[str]) -> dict[str, float]:
    """Periphery heavy, center suppressed."""
    shape = {c: 1.5 for c in clusters}
    for c in suppress:
        if c in shape:
            shape[c] = 0.4
    return _normalize(shape)


def _surge(clusters: list[str]) -> dict[str, float]:
    """Everything amplified — maximum acquisition."""
    return {c: 1.5 for c in clusters}


def _drought(clusters: list[str]) -> dict[str, float]:
    """Everything suppressed — minimal acquisition."""
    return {c: 0.3 for c in clusters}


def _normalize(shape: dict[str, float]) -> dict[str, float]:
    """Normalize so average weight = 1.0."""
    if not shape:
        return shape
    avg = sum(shape.values()) / len(shape)
    if avg == 0:
        return {k: 1.0 for k in shape}
    return {k: v / avg for k, v in shape.items()}


# ── Shape Functions ─────────────────────────────────────────────────────────

def compute_target_shape(desires: dict[str, float]) -> dict[str, float]:
    """
    Convert drift engine desire weights into a normalized target shape.

    Average weight will be 1.0. A desire_weight of 3.0 when average is 1.5
    becomes a shape weight of 2.0.
    """
    if not desires:
        return {}
    return _normalize(dict(desires))


def blend_shapes(a: dict[str, float], b: dict[str, float], alpha: float) -> dict[str, float]:
    """
    Blend two shapes: result = alpha * a + (1-alpha) * b.

    alpha=1.0 → fully shape a
    alpha=0.0 → fully shape b
    """
    alpha = max(0.0, min(1.0, alpha))
    all_keys = set(a) | set(b)
    result = {}
    for k in all_keys:
        va = a.get(k, 1.0)
        vb = b.get(k, 1.0)
        result[k] = alpha * va + (1.0 - alpha) * vb
    return result


def shape_divergence(actual_counts: dict[str, int], target_shape: dict[str, float]) -> float:
    """
    Jensen-Shannon divergence between actual distribution and target shape.

    Returns 0.0 (identical) to 1.0 (maximally different).
    """
    clusters = sorted(set(actual_counts) | set(target_shape))
    if not clusters:
        return 0.0

    # Actual distribution (normalized)
    total_actual = sum(actual_counts.get(c, 0) for c in clusters)
    if total_actual == 0:
        return 1.0

    p = []  # actual
    q = []  # target
    total_shape = sum(target_shape.get(c, 1.0) for c in clusters)

    for c in clusters:
        p.append(actual_counts.get(c, 0) / total_actual)
        q.append(target_shape.get(c, 1.0) / total_shape)

    # JS divergence = 0.5 * KL(p||m) + 0.5 * KL(q||m) where m = (p+q)/2
    m = [(pi + qi) / 2.0 for pi, qi in zip(p, q)]

    def kl(a_dist, b_dist):
        s = 0.0
        for ai, bi in zip(a_dist, b_dist):
            if ai > 0 and bi > 0:
                s += ai * math.log2(ai / bi)
        return s

    jsd = 0.5 * kl(p, m) + 0.5 * kl(q, m)
    # JSD is bounded [0, 1] for log base 2
    return min(1.0, jsd)


def shape_score(actual_counts: dict[str, int], target_shape: dict[str, float]) -> float:
    """Balance score relative to the target shape. 1.0 = perfect match."""
    return 1.0 - shape_divergence(actual_counts, target_shape)


def name_shape(shape: dict[str, float], clusters: Optional[list[str]] = None) -> str:
    """
    Find the best-matching built-in shape name, or return "drifting".

    Uses divergence between the given shape and each built-in template.
    """
    if not shape:
        return "uniform"

    if clusters is None:
        clusters = sorted(shape.keys())

    # Check uniform
    vals = list(shape.values())
    if vals and max(vals) - min(vals) < 0.15:
        return "uniform"

    # Check surge / drought by average
    avg = sum(vals) / len(vals) if vals else 1.0
    if avg > 1.3:
        return "surge"
    if avg < 0.5:
        return "drought"

    # Check convergent: one cluster >> others
    sorted_vals = sorted(vals, reverse=True)
    if len(sorted_vals) >= 2 and sorted_vals[0] > 1.8 and sorted_vals[1] < 1.5:
        focus = max(shape, key=shape.get)
        return f"convergent ({focus})"

    # Check bipolar: two high, rest low
    if len(sorted_vals) >= 3 and sorted_vals[0] > 1.5 and sorted_vals[1] > 1.5 and sorted_vals[2] < 1.0:
        poles = sorted(shape, key=shape.get, reverse=True)[:2]
        return f"bipolar ({poles[0]}+{poles[1]})"

    # Check hollow: some suppressed below 0.6
    suppressed = [c for c, v in shape.items() if v < 0.6]
    if len(suppressed) >= 2:
        return "hollow"

    # Check cascade: monotonic descending spread
    if len(sorted_vals) >= 4:
        spread = sorted_vals[0] - sorted_vals[-1]
        if spread > 1.0:
            return "cascade"

    return "drifting"
