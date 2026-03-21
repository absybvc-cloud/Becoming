#!/usr/bin/env python3
"""Quick tag count summary."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.ingestion.database import Database

db = Database("library/becoming.db")
db.connect()

print("=== TAG COUNTS BY TYPE ===")
for tt in ["model", "source", "curator", "ontology", "becoming"]:
    c = db.conn.execute(
        "SELECT COUNT(*) FROM asset_tags at JOIN tags t ON at.tag_id=t.id WHERE t.tag_type=?",
        (tt,)
    ).fetchone()[0]
    if c > 0:
        print(f"  {tt:12s}: {c} tags")

print("\n=== MODEL TAGS (from auto_tag.py) ===")
rows = db.conn.execute(
    "SELECT a.local_id, t.tag_text, at.confidence, at.source_method "
    "FROM asset_tags at JOIN tags t ON at.tag_id=t.id "
    "JOIN audio_assets a ON at.asset_id=a.id "
    "WHERE t.tag_type='model' ORDER BY a.id, at.confidence DESC"
).fetchall()
if rows:
    for r in rows:
        c = f"{r['confidence']:.2f}" if r["confidence"] else "n/a"
        print(f"  {r['local_id']:40s} | {r['tag_text']:20s} | conf={c}")
else:
    print("  (none yet - run: .venv/bin/python auto_tag.py)")

print("\n=== CURATOR TAGS (your manual tags) ===")
rows2 = db.conn.execute(
    "SELECT a.local_id, t.tag_text, at.source_method "
    "FROM asset_tags at JOIN tags t ON at.tag_id=t.id "
    "JOIN audio_assets a ON at.asset_id=a.id "
    "WHERE t.tag_type='curator' ORDER BY a.id"
).fetchall()
if rows2:
    for r in rows2:
        print(f"  {r['local_id']:40s} | {r['tag_text']:20s} | {r['source_method']}")
else:
    print("  (none)")

db.close()
