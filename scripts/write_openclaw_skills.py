#!/usr/bin/env python3
"""Write OpenClaw skill files for Becoming."""
import os

proj = "/Users/jiahashi/workspace/becoming/Becoming"
act = f"source {proj}/.venv/bin/activate"

harvest_skill = f"""---
name: becoming-harvest
description: "Auto-harvest sounds from Freesound, Internet Archive, and Wikimedia for the Becoming generative music project. Use when user asks to harvest, find, download, or collect new sounds. Triggers on: harvest sounds, find audio, download sounds, collect samples, grow library."
---

# Becoming Sound Harvester

Auto-harvest sounds from external sources for the Becoming generative music library.

## Commands

### Harvest all default queries (recommended first run):
```bash
cd {proj} && {act} && python harvest_sounds.py --limit 5
```

### Harvest specific query:
```bash
cd {proj} && {act} && python harvest_sounds.py --queries "ambient drone" --limit 10
```

### Harvest from specific source:
```bash
cd {proj} && {act} && python harvest_sounds.py --source freesound --limit 10
```

### Harvest by category (drone, texture, field_recording, rhythm, tonal, noise_event):
```bash
cd {proj} && {act} && python harvest_sounds.py --category drone --limit 10
```

### Dry run (preview without downloading):
```bash
cd {proj} && {act} && python harvest_sounds.py --dry-run
```

## Important
- Project path: {proj}
- Always activate .venv first
- Always use the exec tool to run these commands
- Do NOT guess paths or modify commands
"""

tag_skill = f"""---
name: becoming-tag
description: "Auto-tag audio assets in the Becoming library using local LLM (Ollama). Use when user asks to tag sounds, classify audio, label assets, or generate metadata. Triggers on: tag sounds, auto tag, classify audio, label library, generate tags."
---

# Becoming Auto-Tagger

Tag audio assets using local LLM (Ollama) for the Becoming sound library.

## Commands

### Tag all untagged assets:
```bash
cd {proj} && {act} && python auto_tag.py
```

### Tag a specific asset:
```bash
cd {proj} && {act} && python auto_tag.py --asset-id <ID>
```

### Re-tag everything (including already tagged):
```bash
cd {proj} && {act} && python auto_tag.py --retag
```

### Tag with a specific model:
```bash
cd {proj} && {act} && python auto_tag.py --model qwen2.5-coder:32b
```

### Dry run (preview prompts):
```bash
cd {proj} && {act} && python auto_tag.py --dry-run
```

## Important
- Requires Ollama running locally (ollama serve)
- Default model: qwen3-coder:30b
- Project path: {proj}
- Always activate .venv first
- Always use the exec tool to run commands
"""

pipeline_skill = f"""---
name: becoming-pipeline
description: "Run the full Becoming pipeline: harvest sounds, then auto-tag them. Use when user asks to run the full pipeline, process sounds end-to-end, or do a complete harvest+tag cycle. Triggers on: run pipeline, full pipeline, harvest and tag, process everything."
---

# Becoming Full Pipeline

Run harvest + auto-tag in sequence.

## Full pipeline:
```bash
cd {proj} && {act} && python harvest_sounds.py --limit 5 && python auto_tag.py
```

## Pipeline with specific source:
```bash
cd {proj} && {act} && python harvest_sounds.py --source freesound --limit 10 && python auto_tag.py
```

## Pipeline with specific category:
```bash
cd {proj} && {act} && python harvest_sounds.py --category drone --limit 5 && python auto_tag.py
```

## Check ingestion CLI help:
```bash
cd {proj} && {act} && python ingest.py --help
```

## Important
- Project path: {proj}
- Always activate .venv first
- Always use the exec tool to run commands
"""

scan_skill = f"""---
name: scan-inbox
description: "Run the Becoming inbox scanner to detect new audio files. Use when user asks to scan, check inbox, find new audio, or register audio files for the Becoming project."
---

# Scan Inbox

Scan the Becoming audio inbox and register new audio files.

## Instructions

Execute this exact command using the exec tool:

```bash
cd {proj} && {act} && python ingest.py --help
```

## Important

- The project is at `{proj}`
- Always activate `.venv` before running
- The CLI is `python ingest.py`
- Do NOT guess paths or use placeholder paths
- Do NOT use `./scan-inbox.sh` — that does not exist
"""

# Write to all locations
skills = {
    "becoming-harvest": harvest_skill,
    "becoming-tag": tag_skill,
    "becoming-pipeline": pipeline_skill,
    "scan-inbox": scan_skill,
}

home = os.path.expanduser("~")
for name, content in skills.items():
    for base in [
        f"{home}/.openclaw/skills/{name}",
        f"{home}/.openclaw/agents/main/agent/skills/{name}",
    ]:
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, "SKILL.md")
        with open(path, "w") as f:
            f.write(content)
        print(f"wrote: {path}")

print("\nAll skills written successfully")
