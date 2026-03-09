#!/usr/bin/env python3
"""
Smoke test — verifies all modules boot correctly without real audio files.
"""

import sys
import os

print("=== Becoming Smoke Test ===\n")
errors = []

# 1. imports
print("[1] Testing imports...")
try:
    from src.audio_library import AudioLibraryManager, Fragment
    from src.playback_engine import PlaybackEngine
    from src.memory import MemorySystem
    from src.state_engine import StateEngine
    from src.scheduler import Scheduler
    from src.mutation_engine import MutationEngine
    from src.ingestion.enums import SourceName, JobStatus, CandidateStatus, ApprovalStatus, TagType, ReviewActionType
    from src.ingestion.models import PipelineConfigModel, SourceSearchRequest, SourceSearchResult
    from src.ingestion.database import Database, generate_local_id
    from src.ingestion.pipeline import IngestionPipeline
    from src.ingestion.sources.freesound import FreesoundConnector
    from src.ingestion.sources.internet_archive import InternetArchiveConnector
    from src.ingestion.sources.wikimedia import WikimediaConnector
    print("    ✓ all imports OK")
except Exception as e:
    errors.append(f"Import failed: {e}")
    print(f"    ✗ {e}")

# 2. database
print("\n[2] Testing database init...")
try:
    db = Database("library/test_smoke.db")
    db.connect()
    db.close()
    os.remove("library/test_smoke.db")
    print("    ✓ database schema created and destroyed OK")
except Exception as e:
    errors.append(f"Database failed: {e}")
    print(f"    ✗ {e}")

# 3. models validation
print("\n[3] Testing Pydantic models...")
try:
    req = SourceSearchRequest(query="ambient", source_name="freesound", limit=10)
    assert req.limit == 10
    cfg = PipelineConfigModel()
    assert cfg.target_sample_rate == 44100
    print("    ✓ models OK")
except Exception as e:
    errors.append(f"Models failed: {e}")
    print(f"    ✗ {e}")

# 4. local_id generation
print("\n[4] Testing local_id generation...")
try:
    lid = generate_local_id("freesound", "123456", "abc123checksum")
    assert lid.startswith("freesound_123456_")
    assert len(lid.split("_")[-1]) == 8
    print(f"    ✓ local_id: {lid}")
except Exception as e:
    errors.append(f"local_id failed: {e}")
    print(f"    ✗ {e}")

# 5. memory system
print("\n[5] Testing MemorySystem...")
try:
    mem = MemorySystem()
    mem.register("frag_01", cooldown=60)
    assert mem.is_on_cooldown("frag_01")
    assert mem.was_recently_played("frag_01")
    assert mem.is_allowed("frag_02")
    print("    ✓ MemorySystem OK")
except Exception as e:
    errors.append(f"MemorySystem failed: {e}")
    print(f"    ✗ {e}")

# 6. state engine
print("\n[6] Testing StateEngine...")
try:
    state = StateEngine()
    assert state.state in ["pulse", "drift", "low_density", "ritual", "noise_event"]
    density = state.get_density()
    assert isinstance(density, int) and density > 0
    weights = state.get_category_weights()
    assert "rhythm" in weights
    state.force_state("pulse")
    assert state.state == "pulse"
    print(f"    ✓ StateEngine OK | state={state.state} density={density}")
except Exception as e:
    errors.append(f"StateEngine failed: {e}")
    print(f"    ✗ {e}")

# 7. audio library with no files
print("\n[7] Testing AudioLibraryManager (empty manifest)...")
try:
    import json, tempfile
    manifest = [
        {
            "id": "test_01",
            "category": "drone",
            "file_path": "nonexistent.wav",
            "duration": 10,
            "energy_level": 3,
            "density_level": 2,
            "loopable": True,
            "cooldown": 60,
        }
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(manifest, f)
        tmp = f.name
    lib = AudioLibraryManager(tmp)
    lib.load()  # should skip nonexistent file
    assert lib.get("test_01") is None  # skipped because file doesn't exist
    os.unlink(tmp)
    print("    ✓ AudioLibraryManager correctly skips missing files")
except Exception as e:
    errors.append(f"AudioLibraryManager failed: {e}")
    print(f"    ✗ {e}")

# 8. pipeline config
print("\n[8] Testing pipeline config...")
try:
    cfg = PipelineConfigModel(review_required=False, min_world_fit_score=0.3)
    assert not cfg.review_required
    assert cfg.min_world_fit_score == 0.3
    print("    ✓ PipelineConfigModel OK")
except Exception as e:
    errors.append(f"PipelineConfig failed: {e}")
    print(f"    ✗ {e}")

# summary
print("\n=== Results ===")
if errors:
    print(f"FAILED — {len(errors)} error(s):")
    for e in errors:
        print(f"  ✗ {e}")
    sys.exit(1)
else:
    print("ALL TESTS PASSED ✓")
    print("\nNext step: add a Freesound API key to .env and run:")
    print("  python ingest.py --query 'ambient drone' --source freesound --limit 5")
