#!/usr/bin/env python3
"""Quick check of available approved assets for the engine."""
import os, sys, sqlite3

os.chdir(os.path.join(os.path.dirname(__file__), ".."))

db = sqlite3.connect("library/becoming.db")
db.row_factory = sqlite3.Row

approved = db.execute("SELECT COUNT(*) FROM audio_assets WHERE approval_status = 'approved'").fetchone()[0]
total = db.execute("SELECT COUNT(*) FROM audio_assets").fetchone()[0]
print(f"Assets: {total} total, {approved} approved\n")

rows = db.execute("""
    SELECT a.id, a.local_id, a.normalized_file_path, a.duration_seconds,
           a.quality_score, a.world_fit_score, a.drift_fit_score, a.pulse_fit_score
    FROM audio_assets a WHERE a.approval_status = 'approved' ORDER BY a.id
""").fetchall()

for r in rows:
    tags_cur = db.execute("""
        SELECT GROUP_CONCAT(t.tag_text, ', ') FROM asset_tags at2
        JOIN tags t ON at2.tag_id = t.id
        WHERE at2.asset_id = ? AND at2.source_method = 'curator_review'
    """, (r["id"],)).fetchone()[0] or ""
    tags_model = db.execute("""
        SELECT GROUP_CONCAT(t.tag_text, ', ') FROM asset_tags at2
        JOIN tags t ON at2.tag_id = t.id
        WHERE at2.asset_id = ? AND at2.source_method = 'ollama_auto_tag'
    """, (r["id"],)).fetchone()[0] or ""
    npath = r["normalized_file_path"] or ""
    exists = "OK" if npath and os.path.isfile(npath) else "MISSING"
    print(f"[{exists}] {r['local_id']}")
    print(f"  dur={r['duration_seconds']:.1f}s q={r['quality_score']:.2f} fit={r['world_fit_score']:.2f} drift={r['drift_fit_score']:.2f} pulse={r['pulse_fit_score']:.2f}")
    print(f"  curator: [{tags_cur}]")
    print(f"  model:   [{tags_model}]")
    print()

exists_count = sum(1 for r in rows if r["normalized_file_path"] and os.path.isfile(r["normalized_file_path"]))
print(f"Normalized audio files: {exists_count}/{len(rows)}")

# Analysis features
print("\nAnalysis features sample:")
feats = db.execute("""
    SELECT a.local_id, af.* FROM analysis_features af
    JOIN audio_assets a ON af.asset_id = a.id
    WHERE a.approval_status = 'approved' LIMIT 3
""").fetchall()
for f in feats:
    cols = [k for k in f.keys() if k not in ("asset_id", "local_id")]
    print(f"  {f['local_id']}:")
    for c in cols:
        if f[c] is not None:
            print(f"    {c}: {f[c]}")
