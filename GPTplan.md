# Becoming System — OpenClaw Automation Plan

## Overview

This document defines the architecture, workflow, and implementation plan for the Becoming system:

> A local-first AI-driven audio ingestion, processing, and evolution pipeline.

Core philosophy:

- Local-first
- Deterministic execution
- AI as orchestrator, not executor
- Modular + composable pipeline
- Minimal external dependencies

---

# System Architecture

## Layers

### 1. Execution Layer (Python Scripts)
Responsible for actual work:
- Scan files
- Transcribe audio
- Generate tags
- Manage metadata

### 2. Orchestration Layer (OpenClaw)
Responsible for:
- Triggering scripts
- Scheduling workflows
- Managing tasks

### 3. Intelligence Layer (LLMs via Ollama)
- Qwen3 / Qwen2.5 → tagging / reasoning
- Whisper → transcription (later)

### 4. Storage Layer (Local Filesystem)


~/Projects/becoming/


---

# Directory Structure


becoming/
├── data/
│ ├── inbox/ # raw audio input
│ ├── processed/ # processed audio
│ └── review_queue/ # human review items
├── metadata/
│ ├── pending.jsonl
│ ├── processed.jsonl
│ └── tags.jsonl
├── scripts/
│ ├── scan_inbox.py
│ ├── transcribe.py
│ ├── tag_audio.py
│ └── pipeline.py
├── logs/
└── README.md


---

# Phase 1 — Ingestion (DONE / CURRENT)

## Goal
Detect new audio files and register them.

## Script: `scan_inbox.py`

Responsibilities:
- Scan `data/inbox`
- Detect new audio files
- Append to `metadata/pending.jsonl`
- Avoid duplicates (idempotent)

## Output Format

```json
{
  "file": "audio.wav",
  "status": "new",
  "path": "...",
  "timestamp": "..."
}
Phase 2 — Transcription (NEXT)
Goal

Convert audio → text

Script: transcribe.py

Input:

pending.jsonl

Output:

Append transcription field
{
  "file": "...",
  "transcript": "...",
  "status": "transcribed"
}
Model Options
faster-whisper (recommended local)
whisper.cpp (alternative)
Phase 3 — Tagging (LLM)
Goal

Generate semantic labels from audio / transcript

Script: tag_audio.py

Input:

transcribed entries

Output:

{
  "file": "...",
  "tags": ["field-recording", "metal", "noise"],
  "description": "...",
  "status": "tagged"
}
Model
qwen3-coder:30b (preferred)
qwen2.5-coder:32b (fallback)
Phase 4 — Review Queue
Goal

Human-in-the-loop curation

Script: build_review_queue.py

Moves items into:

data/review_queue/

Adds:

confidence
suggested tags
Phase 5 — Indexing
Goal

Searchable audio library

Future:

embedding (nomic-embed-text)
vector DB (optional)
OpenClaw Integration Strategy
Key Principle

OpenClaw = orchestrator only
Python = executor

WRONG Pattern ❌
Let agent guess commands
Let agent write scripts
Let agent explore filesystem
CORRECT Pattern ✅
OpenClaw
  → exec
    → Python script
      → deterministic output
Skills Design
Example: scan_inbox

Location:

~/.openclaw/skills/scan-inbox/SKILL.md
Behavior
Trigger script execution
No reasoning
No improvisation
Current Limitation (IMPORTANT)

OpenClaw (current version):

Skills are NOT strictly enforced
Model may ignore skill
Slash commands may still go through model
Implication

Do NOT rely on OpenClaw for deterministic execution yet

Recommended Execution Strategy (CURRENT)
Hybrid Mode
Use OpenClaw for:
Monitoring
Triggering workflows
Future orchestration
Use CLI / Python for:
Actual execution
Testing pipeline
Deterministic runs
Phase 1 Automation (Recommended Now)
Option A — Manual
python scripts/scan_inbox.py
Option B — Cron
crontab -e

Add:

*/10 * * * * python3 ~/Projects/becoming/scripts/scan_inbox.py
Phase 2 Automation (Planned)

Pipeline:

scan → transcribe → tag → review

Script:

pipeline.py
Future OpenClaw Integration
When Stable

Use OpenClaw to:

Trigger pipeline
Monitor system
Remote control (Telegram, etc.)
Model Allocation Strategy
Layer	Model
Coding	qwen3-coder:30b
Agent	qwen2.5-coder:32b
Transcription	whisper / faster-whisper
Embedding	nomic-embed-text
Key Design Principles
1. Determinism over intelligence

Avoid:

AI guessing file paths
AI generating commands
2. Local-first
No cloud dependencies
Full control
3. Composability

Each script:

Single responsibility
Reusable
4. Idempotency

Running scripts multiple times:

Must not duplicate data
Current Status
 Local models configured
 OpenClaw running
 scan_inbox script working
 metadata pipeline initialized
 OpenClaw skill execution (partially unstable)
 transcription pipeline
 tagging pipeline
Next Steps
Immediate
Fix scan_inbox idempotency
Add transcribe.py
Build simple pipeline.py
Short Term
Add tagging via Qwen
Build review queue
Mid Term
Add embeddings
Add search
Long Term
Fully integrate OpenClaw automation
Add remote control interface
Final Insight

This system is NOT:

"an AI tool"

It IS:

"a programmable sensory system for sound"

End