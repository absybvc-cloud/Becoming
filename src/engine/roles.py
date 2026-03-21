"""
Role definitions and role-mapping logic for the Becoming engine.

Roles are the critical abstraction from the blueprint:
  Ground  - continuous, low variation, stabilizing (bed layer)
  Texture - medium variation, granular/noisy/evolving (surface layer)
  Event   - rare, high contrast, breaks continuity (disruption layer)
  Pulse   - rhythmic or semi-rhythmic, system "life" (rhythm layer)

Each sound in the library gets assigned a primary role based on
curator tags, model tags, analysis features, and fit scores.
"""

from enum import Enum
from dataclasses import dataclass, field


class Role(str, Enum):
    GROUND = "ground"
    TEXTURE = "texture"
    EVENT = "event"
    PULSE = "pulse"


@dataclass
class SoundFragment:
    """A sound loaded from the database, mapped to an engine role."""
    id: str                     # local_id from database
    asset_id: int               # database primary key
    role: Role
    file_path: str              # normalized audio path
    duration: float             # seconds
    energy: float               # 0-1, derived from analysis
    density: float              # 0-1, derived from analysis
    loopable: bool              # true for long drones/pads
    tags: list[str] = field(default_factory=list)
    quality_score: float = 0.0
    world_fit_score: float = 0.0
    drift_fit_score: float = 0.0
    pulse_fit_score: float = 0.0
    # analysis features
    spectral_centroid: float = 0.0
    tempo: float = 0.0
    tonal_confidence: float = 0.0

    @property
    def cooldown(self) -> float:
        """Cooldown before this fragment can replay, based on role + duration."""
        base = {
            Role.GROUND: 180.0,   # long cooldown - beds shouldn't repeat fast
            Role.TEXTURE: 90.0,
            Role.EVENT: 30.0,     # events are brief, can recur sooner
            Role.PULSE: 60.0,
        }
        # scale by duration: longer sounds get more cooldown
        return base[self.role] + self.duration * 0.5


# ── Curator tag → role mapping ──────────────────────────────────────────────

CURATOR_TAG_ROLES = {
    "drift": Role.GROUND,
    "pad": Role.GROUND,
    "texture": Role.TEXTURE,
    "noise": Role.TEXTURE,
    "accent": Role.EVENT,
    "pulse": Role.PULSE,
    "field": Role.GROUND,      # field recordings are usually ambient beds
}

# ── Model tag → role signals ────────────────────────────────────────────────
# Each model tag contributes a score toward a role.

MODEL_TAG_ROLE_SCORES: dict[str, dict[Role, float]] = {
    "drone":            {Role.GROUND: 1.0},
    "ambient":          {Role.GROUND: 0.8},
    "drift_material":   {Role.GROUND: 0.9},
    "atmosphere":       {Role.GROUND: 0.7},
    "low":              {Role.GROUND: 0.5},
    "bassy":            {Role.GROUND: 0.4},
    "meditative":       {Role.GROUND: 0.6},
    "background_layer": {Role.GROUND: 0.8},
    "ocean":            {Role.GROUND: 0.5},
    "texture":          {Role.TEXTURE: 1.0},
    "evolving":         {Role.TEXTURE: 0.5},
    "shimmering":       {Role.TEXTURE: 0.6},
    "granular":         {Role.TEXTURE: 0.8},
    "found_sound":      {Role.TEXTURE: 0.6},
    "industrial":       {Role.TEXTURE: 0.5, Role.EVENT: 0.3},
    "noise":            {Role.TEXTURE: 0.7, Role.EVENT: 0.3},
    "distorted":        {Role.TEXTURE: 0.5, Role.EVENT: 0.3},
    "dark":             {Role.GROUND: 0.3, Role.TEXTURE: 0.3},
    "mysterious":       {Role.GROUND: 0.3, Role.TEXTURE: 0.3},
    "ominous":          {Role.GROUND: 0.4, Role.TEXTURE: 0.2},
    "synthetic":        {Role.TEXTURE: 0.4},
    "doppler":          {Role.TEXTURE: 0.4, Role.EVENT: 0.3},
    "glitchy":          {Role.EVENT: 0.7, Role.TEXTURE: 0.3},
    "glitch":           {Role.EVENT: 0.8},
    "atonal":           {Role.EVENT: 0.5, Role.TEXTURE: 0.3},
    "aggressive":       {Role.EVENT: 0.7},
    "percussive":       {Role.EVENT: 0.4, Role.PULSE: 0.6},
    "rare_event":       {Role.EVENT: 1.0},
    "feedback":         {Role.EVENT: 0.5, Role.TEXTURE: 0.3},
    "rhythmic":         {Role.PULSE: 0.9},
    "ritual_sound":     {Role.PULSE: 0.5, Role.GROUND: 0.3},
}


def assign_role(
    curator_tags: list[str],
    model_tags: list[str],
    duration: float,
    drift_fit: float,
    pulse_fit: float,
) -> Role:
    """
    Determine the primary role for a sound fragment.

    Priority:
      1. Curator tag (human judgment is strongest signal)
      2. Model tag scores (aggregated)
      3. Analysis features as tiebreaker
    """
    # 1. Check curator tags — first match wins (curator is authoritative)
    for tag in curator_tags:
        tag_lower = tag.strip().lower()
        if tag_lower in CURATOR_TAG_ROLES:
            role = CURATOR_TAG_ROLES[tag_lower]
            # Short sounds tagged as ground → reclassify as event
            if role == Role.GROUND and duration < 8.0:
                return Role.EVENT
            # Long sounds tagged as event → reclassify as texture
            if role == Role.EVENT and duration > 30.0:
                return Role.TEXTURE
            return role

    # 2. Accumulate model tag role scores
    scores = {r: 0.0 for r in Role}
    for tag in model_tags:
        tag_lower = tag.strip().lower()
        if tag_lower in MODEL_TAG_ROLE_SCORES:
            for role, score in MODEL_TAG_ROLE_SCORES[tag_lower].items():
                scores[role] += score

    # 3. Add analysis feature biases
    scores[Role.GROUND] += drift_fit * 0.5
    scores[Role.PULSE] += pulse_fit * 0.5

    # Duration heuristics
    if duration > 60.0:
        scores[Role.GROUND] += 0.5
    elif duration < 8.0:
        scores[Role.EVENT] += 0.8
    elif duration < 20.0:
        scores[Role.TEXTURE] += 0.3
        scores[Role.EVENT] += 0.3

    # Return the highest-scoring role
    return max(scores, key=lambda r: scores[r])
