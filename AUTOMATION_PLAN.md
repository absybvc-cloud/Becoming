# Becoming — OpenClaw Automation Plan & Recommendations

## What I Found & Fixed

### Problem: OpenClaw Won't Run Scripts from Natural Language

**Root Causes (3 issues found):**

1. **Wrong paths in skills** — The skill referenced `~/Projects/becoming/scripts/scan_inbox.py` but the actual project is at `/Users/jiahashi/workspace/becoming/Becoming`. The model hallucinated `./scan-inbox.sh /path/to/Becoming/inbox` because it had no correct path to use.

2. **Agent-level skill missing YAML frontmatter** — The skill at `~/.openclaw/agents/main/agent/skills/scan-inbox/SKILL.md` had no `---` frontmatter with `name` and `description`, just raw markdown. OpenClaw couldn't properly trigger or match it.

3. **Local LLM tool-calling limitation** — `qwen2.5-coder:32b` outputs tool calls as plain text JSON (`{"name": "exec", "arguments": {...}}`) instead of actually invoking the `exec` tool through OpenClaw's function calling protocol. This is a known limitation of Ollama-hosted models with tool calling.

**Fixes Applied:**
- Rewrote all skill SKILL.md files with correct YAML frontmatter and correct absolute paths
- Created 4 skills: `scan-inbox`, `becoming-harvest`, `becoming-tag`, `becoming-pipeline`
- Skills installed in both `~/.openclaw/skills/` and `~/.openclaw/agents/main/agent/skills/`

### Remaining Issue: Model Tool Calling

The local models (qwen2.5-coder:32b, qwen3-coder:30b) may still struggle with OpenClaw's tool calling format. **This is an Ollama + OpenClaw compatibility issue, not a script issue.**

**Workarounds (choose one):**

1. **Use `/skill` slash commands instead of natural language:**
   ```
   /skill becoming-harvest
   /skill becoming-tag
   /skill becoming-pipeline
   ```
   This bypasses the model's tool-calling issues entirely.

2. **Switch to `qwen3-coder:30b` as primary agent model** — it has 262K context vs 16K on qwen2.5-coder:32b, and newer models handle tool calling better. Update `~/.openclaw/openclaw.json`:
   ```json
   "agents": {
     "defaults": {
       "model": {
         "primary": "ollama/qwen3-coder:30b"
       }
     }
   }
   ```

3. **Use cron automation** (most reliable, see below)

---

## What Was Created

### 1. `harvest_sounds.py` — Auto-Harvester
Batch searches Freesound, Internet Archive, and Wikimedia with curated queries that match Becoming's sonic world.

```bash
# Dry run (preview)
python harvest_sounds.py --dry-run

# Harvest all categories, 5 results per query
python harvest_sounds.py --limit 5

# Harvest only drone sounds from freesound
python harvest_sounds.py --category drone --source freesound --limit 10

# Custom query
python harvest_sounds.py --queries "tibetan singing bowl" --limit 5
```

**25 built-in queries** across 6 categories: drone, texture, field_recording, rhythm, tonal, noise_event.

### 2. `auto_tag.py` — LLM Auto-Tagger
Uses Ollama (qwen3-coder:30b) to generate semantic tags from audio features + source metadata.

```bash
# Tag all untagged assets
python auto_tag.py

# Dry run
python auto_tag.py --dry-run

# Tag specific asset
python auto_tag.py --asset-id 42

# Re-tag everything
python auto_tag.py --retag
```

**Becoming Ontology** — Tags follow a structured ontology:
- `sonic_character`: drone, texture, tonal, noise, rhythmic, granular, etc.
- `environment`: nature, urban, industrial, underwater, cave, etc.
- `mood`: meditative, tense, serene, dark, mysterious, etc.
- `becoming_role`: pulse_material, drift_material, transition, rare_event, etc.
- `source_type`: field_recording, synthesizer, voice, found_sound, etc.

Tags are stored in the database as `tag_type=model`, `source_method=ollama_auto_tag` with confidence scores.

### 3. OpenClaw Skills (4 skills)
| Skill | Trigger Phrases |
|-------|----------------|
| `scan-inbox` | "scan inbox", "find new audio", "register files" |
| `becoming-harvest` | "harvest sounds", "find audio", "download sounds", "grow library" |
| `becoming-tag` | "tag sounds", "auto tag", "classify audio", "label library" |
| `becoming-pipeline` | "run pipeline", "harvest and tag", "process everything" |

### 4. `scripts/write_openclaw_skills.py`
Utility to regenerate all OpenClaw skills if you need to update paths later.

---

## Recommended Execution Strategy

### Phase 1 — Now (Manual + Scripts)
Use CLI directly, which is deterministic and reliable:

```bash
cd /Users/jiahashi/workspace/becoming/Becoming
source .venv/bin/activate

# Step 1: Harvest sounds
python harvest_sounds.py --category drone --limit 5

# Step 2: Auto-tag
python auto_tag.py

# Step 3: Review (GUI)
python -m review_tool.gui

# Step 4: Export approved assets
python ingest.py --export-manifest
```

### Phase 2 — Cron Automation (Recommended)
The most reliable way to automate. Add to crontab:

```bash
crontab -e
```

```cron
# Harvest new sounds every 6 hours
0 */6 * * * cd /Users/jiahashi/workspace/becoming/Becoming && source .venv/bin/activate && python harvest_sounds.py --limit 3 >> library/harvest_cron.log 2>&1

# Auto-tag every hour
0 * * * * cd /Users/jiahashi/workspace/becoming/Becoming && source .venv/bin/activate && python auto_tag.py >> library/tag_cron.log 2>&1
```

### Phase 3 — OpenClaw Orchestration (When Stable)
Use OpenClaw for monitoring and ad-hoc commands:
- "harvest some drone sounds" → triggers `becoming-harvest` skill
- "tag everything" → triggers `becoming-tag` skill
- "run the full pipeline" → triggers `becoming-pipeline` skill

For now, prefer `/skill becoming-harvest` over natural language until the model's tool-calling improves.

### Phase 4 — Future Enhancements
1. **Whisper transcription** for spoken-word audio classification
2. **Audio embeddings** (nomic-embed-text) for similarity search
3. **Confidence-based auto-approval** — skip manual review for high-confidence assets
4. **OpenClaw cron** — `openclaw cron` can schedule recurring tasks through the gateway

---

## Missing Dependency Note

The `pydub` warning about ffmpeg means some audio formats won't normalize correctly. Install it:

```bash
brew install ffmpeg
```

---

## Architecture Summary

```
                    ┌──────────────┐
                    │   OpenClaw   │  ← Orchestrator (skills/natural language)
                    └──────┬───────┘
                           │ exec tool
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   harvest_sounds.py  auto_tag.py    ingest.py (manual)
          │                │                │
          ▼                ▼                ▼
   ┌─────────────────────────────────────────────┐
   │           src/ingestion/pipeline.py          │
   │  search → download → normalize → analyze →  │
   │           score → store → tag               │
   └──────────────────┬──────────────────────────┘
                      ▼
   ┌─────────────────────────────────────────────┐
   │        library/becoming.db (SQLite)          │
   │  audio_assets | tags | analysis_features     │
   └──────────────────┬──────────────────────────┘
                      ▼
   ┌─────────────────────────────────────────────┐
   │         review_tool (GUI)                    │
   │    human-in-the-loop curation                │
   └──────────────────┬──────────────────────────┘
                      ▼
   ┌─────────────────────────────────────────────┐
   │     manifest.json → Playback Engine          │
   │  main.py → generative music runtime          │
   └─────────────────────────────────────────────┘
```
