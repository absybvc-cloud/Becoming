"""
Weight Engine for the Becoming engine.

The system does NOT choose sounds randomly. It uses weighted selection:

  final_weight =
    base_weight
    × state_weight
    × tag_bias
    × rarity_boost
    × recency_penalty
    × external_modulation

This module computes the final weight for each candidate fragment
given the current state, memory, and world variables.
"""

from .roles import Role, SoundFragment
from .states import StateMachine
from .memory import EngineMemory
from .world import WorldInterface


class WeightEngine:
    """
    Computes selection weights for sound fragments based on
    state, memory, tags, rarity, recency, and world variables.
    """

    def __init__(
        self,
        state_machine: StateMachine,
        memory: EngineMemory,
        world: WorldInterface,
    ):
        self.state = state_machine
        self.memory = memory
        self.world = world

    def compute_weight(self, fragment: SoundFragment) -> float:
        """
        Compute the final selection weight for a fragment.
        Higher weight = more likely to be chosen.
        Returns 0.0 if fragment is not allowed (cooldown/recently played).
        """
        # Hard exclude: cooldown or recently played
        if not self.memory.is_allowed(fragment.id):
            return 0.0

        # 1. Base weight: world_fit_score (0-1)
        base = max(0.1, fragment.world_fit_score)

        # 2. State weight: how much this fragment's role is wanted right now
        role_weights = self.state.get_role_weights()
        state_w = role_weights.get(fragment.role, 0.1)

        # 3. Tag bias: boost fragments whose tags match state preferences
        tag_bias = self._compute_tag_bias(fragment)

        # 4. Rarity boost (anti-center: rarely played → higher weight)
        rarity = self.memory.rarity_boost(fragment.id)

        # 5. Recency penalty (recently played → lower weight)
        recency = self.memory.recency_penalty(fragment.id)

        # 6. Tag staleness (tags not heard recently → boost)
        staleness = self.memory.tag_staleness(fragment.tags)

        # 7. External modulation
        external = self._compute_external_modulation(fragment)

        weight = base * state_w * tag_bias * rarity * recency * staleness * external
        return max(0.001, weight)

    def compute_weights(
        self,
        fragments: list[SoundFragment],
        exclude_ids: set[str] | None = None,
    ) -> list[tuple[SoundFragment, float]]:
        """
        Compute weights for all fragments, excluding active ones.
        Returns list of (fragment, weight) pairs with weight > 0.
        """
        if exclude_ids is None:
            exclude_ids = set()

        results = []
        for frag in fragments:
            if frag.id in exclude_ids:
                continue
            w = self.compute_weight(frag)
            if w > 0:
                results.append((frag, w))
        return results

    def compute_weights_for_role(
        self,
        fragments: list[SoundFragment],
        role: Role,
        exclude_ids: set[str] | None = None,
    ) -> list[tuple[SoundFragment, float]]:
        """Compute weights filtered to a specific role."""
        role_frags = [f for f in fragments if f.role == role]
        return self.compute_weights(role_frags, exclude_ids)

    def _compute_tag_bias(self, fragment: SoundFragment) -> float:
        """
        Aggregate tag bias from the current state.
        Fragments with tags that match state preferences get boosted.
        """
        state_bias = self.state.get_tag_bias()
        if not state_bias or not fragment.tags:
            return 1.0

        total_bias = 0.0
        matches = 0
        for tag in fragment.tags:
            tag_lower = tag.lower()
            if tag_lower in state_bias:
                total_bias += state_bias[tag_lower]
                matches += 1

        if matches == 0:
            return 0.8  # slight penalty for no tag match
        return total_bias / matches  # average bias of matching tags

    def _compute_external_modulation(self, fragment: SoundFragment) -> float:
        """
        Modulate weight based on world state variables.
        """
        world = self.world.get()
        mod = 1.0

        # Time-based: bright sounds during day, dark at night
        brightness = self.world.get_time_brightness()
        if "dark" in fragment.tags or "low" in fragment.tags:
            # Dark sounds favored at night (low brightness)
            mod *= 0.5 + (1.0 - brightness)
        elif "shimmering" in fragment.tags:
            # Shimmery sounds favored during day
            mod *= 0.5 + brightness

        # Noise level: boost texture/noise when environment is noisy
        if world.noise_level > 0.3 and fragment.role == Role.TEXTURE:
            mod *= 1.0 + world.noise_level * 0.5

        # Human bias override
        for tag in fragment.tags:
            if tag in world.human_bias:
                mod *= world.human_bias[tag]

        return max(0.1, mod)
