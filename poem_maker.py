#!/usr/bin/env python3
"""
Poem Maker — live poetic visualization of the Becoming sound ecology.

Harvests tags, roles, clusters, and mood from the currently playing layers
and asks a local LLM to distill them into a single poetic line.
"""

from __future__ import annotations

import os
import requests

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

# Tags too mechanical / generic to be poetic
FILTER_TAGS = {
    "drift_material", "background_layer", "found_sound", "noise",
    "competition", "contest", "sound-design", "processed", "synthesis",
    "custom", "effect", "movie", "cinematic", "foley", "sound-effect",
    "multisample", "sample", "loop", "one-shot", "stereo", "mono",
    "normalized", "44100", "48000", "16bit", "24bit", "wav", "mp3",
    "flac", "aif", "ogg",
}


def harvest_words(blob: dict) -> str:
    """Format the word cloud from a [poem-words] JSON blob into a string."""
    words = blob.get("words", [])
    if not words:
        return "silence"
    return ", ".join(words)


def build_poem_prompt(
    words_str: str,
    state: str,
    phase: str,
    tension: float,
    density: float,
    previous_lines: list[str] | None = None,
    beat: str = "ascending",
    rhyme_word: str | None = None,
) -> str:
    """Build the LLM prompt for one poem line."""
    context = ""
    if previous_lines:
        recent = previous_lines[-3:]
        context = "\n\nPrevious lines (do not repeat):\n" + "\n".join(f"  {l}" for l in recent)

    if beat == "ascending":
        direction = "This line should RISE — expand, brighten, open upward, reach, emerge."
    else:
        direction = "This line should FALL — contract, darken, descend, dissolve, recede."

    if rhyme_word:
        rhyme_instr = (f"Your line MUST end with a word that rhymes with \"{rhyme_word}\".\n"
                       f"Rhyming is essential — the last word must sound like \"{rhyme_word}\".")
    else:
        rhyme_instr = "Write freely — no rhyme constraint for this line."

    return f"""You are a poet channelling an ever-shifting sound ecology called "Becoming".
These sounds are alive right now:

{words_str}

Mood: {state} | Phase: {phase} | tension={tension:.1f} | density={density:.1f}{context}

{direction}
{rhyme_instr}

Write ONE vivid poetic line — bold imagery, unexpected metaphor, sensory language.
No quotes, no explanation, just the raw line."""


def generate_line(
    prompt: str,
    model: str = "qwen3-coder:30b",
    ollama_base: str | None = None,
) -> str | None:
    """Call local Ollama and return a single poem line, or None on failure."""
    base = ollama_base or OLLAMA_BASE
    try:
        resp = requests.post(
            f"{base}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 1.0,
                    "num_predict": 80,
                },
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()

        # Take only the first non-empty line
        for line in raw.splitlines():
            line = line.strip().strip('"').strip("'").strip()
            if line and len(line) > 3:
                return line

        return raw[:120] if raw else None
    except Exception:
        return None
