import json
import os
from dataclasses import dataclass, field
from typing import Optional


CATEGORIES = {"rhythm", "drone", "tonal", "field", "noise"}


@dataclass
class Fragment:
    id: str
    category: str
    file_path: str
    duration: float
    energy_level: int        # 1–10
    density_level: int       # 1–10
    loopable: bool
    cooldown: float          # seconds before this fragment can replay
    tags: list[str] = field(default_factory=list)

    def exists(self) -> bool:
        return os.path.isfile(self.file_path)


class AudioLibraryManager:
    def __init__(self, manifest_path: str):
        self.manifest_path = manifest_path
        self.fragments: dict[str, Fragment] = {}

    def load(self):
        with open(self.manifest_path, "r") as f:
            data = json.load(f)

        loaded = 0
        for entry in data:
            frag = Fragment(
                id=entry["id"],
                category=entry["category"],
                file_path=entry["file_path"],
                duration=entry["duration"],
                energy_level=entry.get("energy_level", 5),
                density_level=entry.get("density_level", 5),
                loopable=entry.get("loopable", False),
                cooldown=entry.get("cooldown", 60),
                tags=entry.get("tags", []),
            )
            if frag.category not in CATEGORIES:
                print(f"[library] skipping {frag.id}: unknown category '{frag.category}'")
                continue
            if not frag.exists():
                print(f"[library] skipping {frag.id}: file not found at {frag.file_path}")
                continue
            self.fragments[frag.id] = frag
            loaded += 1

        print(f"[library] loaded {loaded} fragments from {self.manifest_path}")

    def get_by_category(self, category: str) -> list[Fragment]:
        return [f for f in self.fragments.values() if f.category == category]

    def get(self, fragment_id: str) -> Optional[Fragment]:
        return self.fragments.get(fragment_id)

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {cat: 0 for cat in CATEGORIES}
        for frag in self.fragments.values():
            counts[frag.category] += 1
        return counts
