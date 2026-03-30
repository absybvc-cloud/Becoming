"""
Query Generator – Desire → Language → Sound

Transforms internal system desire into drifting, semantically evolving
search queries. Connects: internal state → language → world → new audio.

Usage:
    # Standalone test
    python query_generator.py

    # From engine or GUI
    from query_generator import QueryGenerator
    qg = QueryGenerator()
    query = qg.generate(desire_state)
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field


# ── Semantic Map ────────────────────────────────────────────────────────────
# Curated semantic space: cluster → possible search terms.

SEMANTIC_MAP: dict[str, list[str]] = {
    "texture_evolving": [
        "granular", "shimmering", "unstable", "metallic",
        "digital decay", "glitch texture", "flowing particles",
        "morphing", "modular synthesis", "tape warble",
    ],
    "nature_field": [
        "wind", "forest", "rain", "water stream",
        "insects", "night ambience", "bird song",
        "ocean waves", "creek", "meadow",
    ],
    "dark_drift": [
        "low drone", "sub bass", "dark ambient",
        "void", "rumble", "deep hum", "ominous",
        "cavernous", "bassy resonance",
    ],
    "industrial_noise": [
        "machine", "metal", "factory",
        "mechanical noise", "grinding", "electrical hum",
        "feedback", "power plant", "ventilation",
    ],
    "rupture_event": [
        "impact", "explosion", "glitch",
        "break", "crack", "distortion",
        "shatter", "crash", "electrical discharge",
    ],
    "tonal_meditative": [
        "singing bowl", "bells", "chime",
        "harmonic", "resonance", "crystal bowl",
        "meditation tone", "sustained pitch",
    ],
    "urban_field": [
        "city traffic", "street ambience", "train station",
        "construction", "subway", "urban night",
        "distant sirens", "crowd murmur",
    ],
    "pulse_rhythm": [
        "percussion loop", "heartbeat", "drum",
        "metallic rhythm", "ritual drum", "pulse",
        "rhythmic pattern", "click track",
    ],
    "ambient_float": [
        "floating pad", "ethereal", "serene",
        "delicate ambient", "soft atmosphere",
        "gentle drift", "airy texture",
    ],
}

# ── State Semantic Modifiers ────────────────────────────────────────────────

STATE_TERMS: dict[str, list[str]] = {
    "submerged": ["distant", "underwater", "blurred", "deep", "muffled"],
    "tense":     ["tight", "pressured", "compressed", "strained", "edgy"],
    "dissolved": ["soft", "diffused", "floating", "fading", "dissolving"],
    "rupture":   ["sudden", "violent", "sharp", "abrupt", "fractured"],
    "drifting":  ["slow", "evolving", "endless", "wandering", "gradual"],
}

# ── Noise Terms (generic modifiers) ────────────────────────────────────────

NOISE_TERMS: list[str] = [
    "field recording", "ambient", "background",
    "loop", "texture", "soundscape",
    "abstract", "experimental", "found sound",
]

# ── Configuration ───────────────────────────────────────────────────────────

@dataclass
class QueryConfig:
    base_terms: int = 2
    cross_terms: int = 1
    state_terms: int = 1
    noise_terms: int = 1
    mutation_rate: float = 0.5
    max_query_length: int = 8
    memory_size: int = 50
    overlap_threshold: float = 0.70
    cross_cluster_probability: float = 0.4


# ── Desire State ────────────────────────────────────────────────────────────

@dataclass
class DesireState:
    """Snapshot of what the system currently wants."""
    focus_cluster: str
    state: str = "drifting"
    tension: float = 0.3
    density: float = 0.5
    recent_clusters: list[str] = field(default_factory=list)
    fatigue: dict[str, float] = field(default_factory=dict)
    desires: dict[str, float] = field(default_factory=dict)
    phase: str = "drift"


# ── Query Feedback ──────────────────────────────────────────────────────────

@dataclass
class QueryFeedback:
    results_count: int = 0
    accepted_assets: int = 0


# ── Query Generator ─────────────────────────────────────────────────────────

class QueryGenerator:
    """
    Generates drifting, semantically evolving search queries from system desire.

    Core principles:
    - Queries mutate over time rather than being generated from scratch
    - Cross-cluster metonymy injects unexpected combinations
    - Recent query memory prevents repetition
    - Feedback adjusts token weights
    """

    def __init__(self, config: QueryConfig | None = None):
        self.config = config or QueryConfig()
        self.recent_queries: deque[str] = deque(maxlen=self.config.memory_size)
        self._last_tokens: list[str] = []
        self._feedback: dict[str, QueryFeedback] = {}
        self._token_weights: dict[str, float] = {}  # reinforcement weights

    # ── Public API ──────────────────────────────────────────────────────

    def generate(self, desire: DesireState) -> str:
        """
        Generate a query from desire state.
        If a previous query exists, mutate it. Otherwise build fresh.
        """
        if self._last_tokens and random.random() < self.config.mutation_rate:
            tokens = self._mutate(self._last_tokens, desire)
        else:
            tokens = self._build_fresh(desire)

        query = self._realize(tokens)

        # Reject if too similar to recent queries, retry fresh
        attempts = 0
        while self._is_repetitive(query) and attempts < 5:
            tokens = self._build_fresh(desire)
            query = self._realize(tokens)
            attempts += 1

        self.recent_queries.append(query)
        self._last_tokens = tokens
        return query

    def generate_batch(self, desire: DesireState, count: int = 3) -> list[str]:
        """Generate multiple diverse queries for the same desire."""
        queries = []
        for _ in range(count):
            q = self.generate(desire)
            queries.append(q)
        return queries

    def record_feedback(self, query: str, results_count: int, accepted: int):
        """Record how well a query performed to adjust future generation."""
        self._feedback[query] = QueryFeedback(results_count, accepted)
        tokens = query.split()
        if results_count == 0 or accepted == 0:
            # Penalize tokens from poor queries
            for t in tokens:
                self._token_weights[t] = self._token_weights.get(t, 1.0) * 0.8
        elif accepted >= 2:
            # Reinforce tokens from good queries
            for t in tokens:
                self._token_weights[t] = self._token_weights.get(t, 1.0) * 1.2

    # ── Fresh Query Builder ─────────────────────────────────────────────

    def _build_fresh(self, desire: DesireState) -> list[str]:
        """Build a new query from scratch using the desire state."""
        cfg = self.config
        tokens: list[str] = []

        # Step 1: Base terms from focus cluster
        cluster = desire.focus_cluster
        if cluster in SEMANTIC_MAP:
            pool = self._weighted_sample_pool(SEMANTIC_MAP[cluster])
            tokens.extend(random.sample(pool, min(cfg.base_terms, len(pool))))

        # Step 2: Cross-cluster metonymy
        if random.random() < cfg.cross_cluster_probability:
            other_clusters = [c for c in SEMANTIC_MAP if c != cluster]
            if other_clusters:
                # Prefer clusters with high desire
                cross = self._pick_cross_cluster(other_clusters, desire)
                cross_pool = SEMANTIC_MAP[cross]
                tokens.extend(random.sample(cross_pool, min(cfg.cross_terms, len(cross_pool))))

        # Step 3: State modifier
        state = desire.state
        if state in STATE_TERMS:
            tokens.extend(random.sample(STATE_TERMS[state], min(cfg.state_terms, len(STATE_TERMS[state]))))

        # Step 4: Noise injection (0-2 terms)
        n_noise = random.randint(0, cfg.noise_terms)
        if n_noise > 0:
            tokens.extend(random.sample(NOISE_TERMS, min(n_noise, len(NOISE_TERMS))))

        # Trim to max length
        random.shuffle(tokens)
        return tokens[:cfg.max_query_length]

    # ── Mutation ────────────────────────────────────────────────────────

    def _mutate(self, tokens: list[str], desire: DesireState) -> list[str]:
        """Mutate a previous query's tokens."""
        tokens = list(tokens)  # copy
        method = random.choice(["replace", "add", "remove", "swap"])

        if method == "replace" and tokens:
            # Replace one token with a term from the focus cluster
            idx = random.randrange(len(tokens))
            cluster = desire.focus_cluster
            if cluster in SEMANTIC_MAP:
                tokens[idx] = random.choice(SEMANTIC_MAP[cluster])

        elif method == "add":
            # Add a term from cross-cluster or noise
            if random.random() < 0.5 and desire.focus_cluster in SEMANTIC_MAP:
                others = [c for c in SEMANTIC_MAP if c != desire.focus_cluster]
                if others:
                    cross = random.choice(others)
                    tokens.append(random.choice(SEMANTIC_MAP[cross]))
            else:
                tokens.append(random.choice(NOISE_TERMS))

        elif method == "remove" and len(tokens) > 2:
            tokens.pop(random.randrange(len(tokens)))

        elif method == "swap" and len(tokens) >= 2:
            i, j = random.sample(range(len(tokens)), 2)
            tokens[i], tokens[j] = tokens[j], tokens[i]

        # Trim
        return tokens[:self.config.max_query_length]

    # ── Language Realization ────────────────────────────────────────────

    def _realize(self, tokens: list[str]) -> str:
        """Join tokens into a query string."""
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for t in tokens:
            t_lower = t.lower()
            if t_lower not in seen:
                seen.add(t_lower)
                unique.append(t)
        return " ".join(unique)

    # ── Repetition Check ────────────────────────────────────────────────

    def _is_repetitive(self, query: str) -> bool:
        """Reject if identical or >70% overlap with recent queries."""
        query_tokens = set(query.lower().split())
        for recent in self.recent_queries:
            if query == recent:
                return True
            recent_tokens = set(recent.lower().split())
            if not query_tokens or not recent_tokens:
                continue
            overlap = len(query_tokens & recent_tokens) / max(len(query_tokens), len(recent_tokens))
            if overlap > self.config.overlap_threshold:
                return True
        return False

    # ── Helpers ─────────────────────────────────────────────────────────

    def _pick_cross_cluster(self, candidates: list[str], desire: DesireState) -> str:
        """Pick a cross-cluster, biased by desire weights."""
        if not desire.desires:
            return random.choice(candidates)
        # Weight by desire — high-desire clusters more likely to leak in
        weights = [max(0.1, desire.desires.get(c, 1.0)) for c in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]

    def _weighted_sample_pool(self, terms: list[str]) -> list[str]:
        """Return terms filtered/weighted by feedback history."""
        if not self._token_weights:
            return terms
        # Exclude severely penalized tokens (weight < 0.3)
        return [t for t in terms if self._token_weights.get(t, 1.0) >= 0.3]  or terms


# ── Convenience: build DesireState from live engine ─────────────────────────

def desire_from_engine(drift_engine, state_machine, world) -> DesireState:
    """
    Build a DesireState from live engine components.
    Call this from engine.py or the GUI when triggering query generation.
    """
    snap = drift_engine.snapshot()
    w = world.get()
    return DesireState(
        focus_cluster=snap.get("focus") or _pick_needy_cluster(snap.get("desires", {})),
        state=state_machine.current,
        tension=w.tension,
        density=w.density,
        recent_clusters=[],
        fatigue=snap.get("fatigue", {}),
        desires=snap.get("desires", {}),
        phase=snap.get("phase", "drift"),
    )


def desire_from_balance(report: dict) -> DesireState:
    """
    Build a DesireState from a balance report (offline / tools mode).
    Focuses on the most underrepresented cluster.
    """
    clusters = report.get("clusters", {})
    # Find cluster with highest deficit
    worst = max(clusters, key=lambda c: clusters[c].get("deficit", 0), default="texture_evolving")
    return DesireState(
        focus_cluster=worst,
        state="drifting",
        tension=0.3,
        density=0.5,
        desires={c: max(0.1, d.get("deficit", 0) + 1.0) for c, d in clusters.items()},
    )


def _pick_needy_cluster(desires: dict[str, float]) -> str:
    """Pick the cluster with highest desire weight."""
    if not desires:
        return random.choice(list(SEMANTIC_MAP.keys()))
    return max(desires, key=desires.get)


# ── Harvest Plan Generation ─────────────────────────────────────────────────

def generate_harvest_plan(
    report: dict,
    queries_per_cluster: int = 3,
    limit_per_query: int = 10,
) -> list[dict]:
    """
    Generate a dynamic harvest plan from a balance report.

    Returns list of {"query": str, "cluster": str, "limit": int}
    compatible with balance.py's rebalance loop.
    """
    qg = QueryGenerator()
    desire = desire_from_balance(report)
    plan = []

    clusters = report.get("clusters", {})
    for name in sorted(clusters, key=lambda c: clusters[c].get("deficit", 0), reverse=True):
        deficit = clusters[name].get("deficit", 0)
        if deficit <= 0:
            continue

        # Generate queries focused on this cluster
        cluster_desire = DesireState(
            focus_cluster=name,
            state=desire.state,
            tension=desire.tension,
            density=desire.density,
            desires=desire.desires,
            phase=desire.phase,
        )
        queries = qg.generate_batch(cluster_desire, count=queries_per_cluster)
        per_q = max(3, deficit // queries_per_cluster + 1)

        for q in queries:
            plan.append({
                "query": q,
                "cluster": name,
                "limit": min(per_q, limit_per_query),
            })

    return plan


# ── CLI demo ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--live" in sys.argv:
        # Generate queries from real balance data
        from balance import analyze_balance, get_db

        db = get_db()
        report = analyze_balance(db)
        desire = desire_from_balance(report)

        print(f"Focus cluster: {desire.focus_cluster}")
        print(f"Phase: {desire.phase}  |  State: {desire.state}\n")

        print("Generated queries:\n")
        qg = QueryGenerator()
        for q in qg.generate_batch(desire, count=5):
            print(f"  → \"{q}\"")

        print("\n\nHarvest plan:\n")
        plan = generate_harvest_plan(report)
        for entry in plan:
            print(f"  [{entry['cluster']}] \"{entry['query']}\"  limit={entry['limit']}")

    else:
        qg = QueryGenerator()

        print("Query Generator — demo\n")

        scenarios = [
            DesireState(focus_cluster="dark_drift", state="submerged", tension=0.2, density=0.3, phase="drift"),
            DesireState(focus_cluster="rupture_event", state="rupture", tension=0.9, density=0.8, phase="collapse"),
            DesireState(focus_cluster="nature_field", state="drifting", tension=0.3, density=0.4, phase="drift"),
            DesireState(focus_cluster="texture_evolving", state="dissolved", tension=0.1, density=0.2, phase="saturation"),
            DesireState(focus_cluster="industrial_noise", state="tense", tension=0.7, density=0.6, phase="reconfiguration"),
        ]

        for desire in scenarios:
            print(f"  cluster={desire.focus_cluster}  state={desire.state}  phase={desire.phase}")
            queries = qg.generate_batch(desire, count=3)
            for q in queries:
                print(f"    → \"{q}\"")
            print()

        print("Mutation drift (10 iterations, texture_evolving + drifting):\n")
        drift_desire = DesireState(focus_cluster="texture_evolving", state="drifting", phase="drift")
        for i in range(10):
            q = qg.generate(drift_desire)
            print(f"  {i+1:2d}. \"{q}\"")
