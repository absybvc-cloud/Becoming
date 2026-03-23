"""
Semantic vector representation for Becoming sounds.

Each sound gets two vectors:
  1. Semantic Vector - tag-based meaning (what does it sound like?)
  2. Role Vector    - system function (what does it do in the mix?)

Plus cluster assignment for anti-loop drift tracking.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .roles import SoundFragment, Role


# ── Semantic Vector ─────────────────────────────────────────────────────────

@dataclass
class SemanticVector:
    """Sparse, normalized tag → weight mapping representing a sound's meaning."""
    weights: dict[str, float] = field(default_factory=dict)

    def similarity(self, other: SemanticVector) -> float:
        """Cosine similarity between two semantic vectors. Range [0, 1]."""
        common = set(self.weights) & set(other.weights)
        if not common:
            return 0.0
        dot = sum(self.weights[k] * other.weights[k] for k in common)
        mag_a = math.sqrt(sum(v * v for v in self.weights.values()))
        mag_b = math.sqrt(sum(v * v for v in other.weights.values()))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    def shared_tags(self, other: SemanticVector) -> set[str]:
        """Tags present in both vectors (bridge tag candidates)."""
        return set(self.weights) & set(other.weights)

    def dominant_tags(self, n: int = 5) -> list[str]:
        """Top-n tags by weight."""
        return [k for k, _ in sorted(self.weights.items(), key=lambda x: -x[1])[:n]]

    def combine(self, other: SemanticVector, my_weight: float = 0.5) -> SemanticVector:
        """Blend two vectors with a mixing ratio."""
        ow = 1.0 - my_weight
        merged: dict[str, float] = {}
        for k, v in self.weights.items():
            merged[k] = v * my_weight + other.weights.get(k, 0.0) * ow
        for k, v in other.weights.items():
            if k not in merged:
                merged[k] = v * ow
        return SemanticVector(weights=merged)

    def distort(self, drop_prob: float = 0.15, noise: float = 0.1) -> SemanticVector:
        """Misrecognition: randomly drop tags and add noise."""
        new_w: dict[str, float] = {}
        for k, v in self.weights.items():
            if random.random() < drop_prob:
                continue  # tag dropped
            new_w[k] = max(0.0, v + random.gauss(0, noise))
        return SemanticVector(weights=new_w)

    def __len__(self) -> int:
        return len(self.weights)


# ── Role Vector ─────────────────────────────────────────────────────────────

@dataclass
class RoleVector:
    """System-function vector: describes what a sound DOES, not what it means."""
    grounding: float = 0.0       # stabilizing bed quality
    eventfulness: float = 0.0    # disruptive / rare quality
    pulse_strength: float = 0.0  # rhythmic regularity
    density: float = 0.0         # spectral fullness
    brightness: float = 0.0      # spectral center of mass
    loopability: float = 0.0     # can it sustain / loop?
    rupture_potential: float = 0.0  # capacity to break flow

    def compatibility(self, other: RoleVector) -> float:
        """How compatible two sounds are for co-existence in the mix."""
        # Complementary is good: ground + event is compatible
        # Same-niche is slightly less so: ground + ground is redundant
        diff = abs(self.grounding - other.grounding) * 0.3 \
             + abs(self.eventfulness - other.eventfulness) * 0.3 \
             + abs(self.pulse_strength - other.pulse_strength) * 0.2 \
             + abs(self.density - other.density) * 0.2
        return min(1.0, 0.3 + diff)  # 0.3 baseline, up to 1.0 for complementary


# ── Cluster ─────────────────────────────────────────────────────────────────

# Predefined clusters aligned with Becoming's sonic world.
# Keywords must reflect tags that Freesound / LLM actually produce for each category.
CLUSTER_DEFS: dict[str, set[str]] = {
    "dark_drift":        {"dark", "low", "bassy", "ominous", "mysterious", "rumble",
                          "deep", "eerie", "haunting", "sinister"},
    "tonal_meditative":  {"meditative", "tonal", "harmonic", "clean", "resonant", "bells", "chime",
                          "singing-bowl", "crystal", "tuning", "gentle", "calm"},
    "nature_field":      {"nature", "ocean", "rain", "forest", "wind", "field_recording",
                          "field-recording", "field", "meadow", "soundscape", "natural-soundscape",
                          "creek", "stream", "bird", "insect", "thunder", "sea", "wave", "water"},
    "urban_field":       {"urban", "city", "traffic", "exterior", "street", "car", "road",
                          "train", "station", "crowd", "market", "bus", "pedestrian",
                          "construction", "highway", "subway"},
    "industrial_noise":  {"industrial", "distorted", "feedback", "saturated",
                          "machine", "factory", "hum", "electrical", "mechanical",
                          "electromagnetic", "motor", "generator"},
    "texture_evolving":  {"evolving", "granular", "shimmering", "synthetic", "morphing",
                          "processed", "abstract", "experimental", "generative", "modular",
                          "lo-fi", "tape"},
    "pulse_rhythm":      {"rhythmic", "pulse_material", "ritual_sound", "heartbeat",
                          "beat", "loop", "drum", "repetitive", "pattern", "click",
                          "tap", "synth-percussion", "tempo", "sequence"},
    "rupture_event":     {"rare_event", "glitch", "aggressive", "atonal", "glitchy",
                          "impact", "crash", "shatter", "bang", "smash", "hit", "break",
                          "breaking", "collision", "explosion", "burst", "destroy",
                          "destruction", "boom", "crack", "crunch", "crush",
                          "demolition", "shattering", "smashing", "crashing"},
    "ambient_float":     {"ambient", "atmosphere", "floating", "delicate", "serene",
                          "background_layer", "ethereal", "soft", "airy", "spacious"},
}

# Tags so common they appear on almost everything — discount them in cluster scoring.
_GENERIC_TAGS = {"drone", "drift_material", "nature", "texture", "found_sound",
                 "percussive", "noise", "ominous"}


def _assign_cluster(tags: set[str]) -> str:
    """Assign a sound to the best-matching cluster."""
    best_cluster = "texture_evolving"  # fallback
    best_score = 0.0
    specific_tags = tags - _GENERIC_TAGS
    for cname, ctags in CLUSTER_DEFS.items():
        # Specific tags count full, generic tags count at 0.2
        specific_overlap = len(specific_tags & ctags)
        generic_overlap = len((tags & _GENERIC_TAGS) & ctags)
        score = specific_overlap + generic_overlap * 0.2
        if score > best_score:
            best_score = score
            best_cluster = cname
    return best_cluster


# ── Builder ─────────────────────────────────────────────────────────────────

# Tag contribution weights by source type
CURATOR_WEIGHT = 1.0
MODEL_WEIGHT = 0.7
SOURCE_WEIGHT = 0.4


def build_semantic_vector(fragment: SoundFragment) -> SemanticVector:
    """Build a semantic vector from a fragment's tags."""
    weights: dict[str, float] = {}
    for tag in fragment.tags:
        t = tag.lower().strip()
        if not t:
            continue
        # We don't know the source breakdown here, so use uniform weight.
        # The library enricher below uses per-source weights.
        weights[t] = max(weights.get(t, 0.0), 0.8)

    # Normalize to [0,1]
    if weights:
        peak = max(weights.values())
        if peak > 0:
            weights = {k: v / peak for k, v in weights.items()}

    return SemanticVector(weights=weights)


def build_semantic_vector_from_tags(
    curator_tags: list[str],
    model_tags: list[str],
    source_tags: list[str],
) -> SemanticVector:
    """Build a semantic vector with proper per-source weighting."""
    weights: dict[str, float] = {}
    for t in curator_tags:
        k = t.lower().strip()
        if k:
            weights[k] = max(weights.get(k, 0.0), CURATOR_WEIGHT)
    for t in model_tags:
        k = t.lower().strip()
        if k:
            weights[k] = max(weights.get(k, 0.0), MODEL_WEIGHT)
    for t in source_tags:
        k = t.lower().strip()
        if k:
            weights[k] = max(weights.get(k, 0.0), SOURCE_WEIGHT)

    # Normalize to [0,1]
    if weights:
        peak = max(weights.values())
        if peak > 0:
            weights = {k: v / peak for k, v in weights.items()}

    return SemanticVector(weights=weights)


def build_role_vector(fragment: SoundFragment) -> RoleVector:
    """Derive a role vector from fragment properties."""
    rv = RoleVector()

    # Grounding: high for ground role, long duration, low energy
    rv.grounding = {
        Role.GROUND: 0.9, Role.TEXTURE: 0.3,
        Role.EVENT: 0.05, Role.PULSE: 0.2,
    }.get(fragment.role, 0.3)

    # Eventfulness: inverse of grounding
    rv.eventfulness = {
        Role.GROUND: 0.05, Role.TEXTURE: 0.3,
        Role.EVENT: 0.9, Role.PULSE: 0.2,
    }.get(fragment.role, 0.3)

    # Pulse strength
    rv.pulse_strength = {
        Role.GROUND: 0.05, Role.TEXTURE: 0.1,
        Role.EVENT: 0.1, Role.PULSE: 0.9,
    }.get(fragment.role, 0.1)

    # Density from analysis
    rv.density = fragment.density

    # Brightness from spectral centroid
    rv.brightness = min(1.0, fragment.spectral_centroid / 5000.0)

    # Loopability
    rv.loopability = 0.9 if fragment.loopable else max(0.1, min(0.7, fragment.duration / 60.0))

    # Rupture potential
    rv.rupture_potential = {
        Role.GROUND: 0.02, Role.TEXTURE: 0.15,
        Role.EVENT: 0.8, Role.PULSE: 0.1,
    }.get(fragment.role, 0.1)
    # Boost if tagged as aggressive/rare/glitch
    rupture_tags = {"aggressive", "rare_event", "glitch", "glitchy", "feedback", "distorted"}
    if rupture_tags & set(t.lower() for t in fragment.tags):
        rv.rupture_potential = min(1.0, rv.rupture_potential + 0.3)

    return rv


def assign_cluster(fragment: SoundFragment) -> str:
    """Assign a fragment to the best cluster."""
    return _assign_cluster(set(t.lower() for t in fragment.tags))
