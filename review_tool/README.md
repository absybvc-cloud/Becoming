Becoming — Review Tool

A simple local review GUI to listen to ingested audio assets and apply curation tags.

Requirements:
- Python 3.10+
- On macOS: `afplay` (built-in) is used for playback. For mp3 support, `ffmpeg` + `pydub` are recommended.

How to run:

```bash
# create & activate venv (if not already)
python -m venv .venv
source .venv/bin/activate
pip install pydub
# ensure ffmpeg is installed: brew install ffmpeg
python -m review_tool.gui
```

Features:
- Loads pending assets from `library/becoming.db` (preferred) or `assets/library/manifest.json` as fallback
- Play / stop audio
- Inspect metadata and computed scores
- Apply decision (keep/maybe/reject/skip), role, and tags
- Persist decisions to the DB and create a symlinked curated folder

