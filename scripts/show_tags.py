#!/usr/bin/env python3
"""Show all tags in the Becoming database grouped by type."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.ingestion.database import Database

db = Database("library/becoming.db")
db.connect()

# Model-generated tags
print("=== AUTO-GENERATED TAGS (tag_type=model) ===")
rows = db.conn.execute("""
    SELECT a.local_id, t.tag_text, t.tag_type, at.confidence, at.source_method
    FROM asset_tags at
    JOIN tags t ON at.tag_id = t.id
    JOIN audio_assets a ON at.asset_id = a.id
    WHERE t.tag_type = 'model'
    ORDER BY a.id, at.confidence DESC
""").fetchall()
for r in rows:
    conf = f"{r['confidence']:.2f}" if r['confidence'] is not None else "n/a"
    print(f"  {r['local_id']:40s} | {r['tag_text']:25s} | conf={conf} | {r['source_method']}")
print(f"\nTotal model tags: {len(rows)}")

# Source tags
print("\n=== SOURCE TAGS (tag_type=source, from original metadata) ===")
src_rows = db.conn.execute("""
    SELECT a.local_id, t.tag_text, at.source_method
    FROM asset_tags at
    JOIN tags t ON at.tag_id = t.id
    JOIN audio_assets a ON at.asset_id = a.id
    WHERE t.tag_type = 'source'
    ORDER BY a.id, t.tag_text
""").fetchall()
for r in src_rows:
    print(f"  {r['local_id']:40s} | {r['tag_text']:25s} | {r['source_method']}")
print(f"\nTotal source tags: {len(src_rows)}")

# Curator tags
print("\n=== CURATOR TAGS (tag_type=curator, manual) ===")
cur_rows = db.conn.execute("""
    SELECT a.local_id, t.tag_text, at.source_method
    FROM asset_tags at
    JOIN tags t ON at.tag_id = t.id
    JOIN audio_assets a ON at.asset_id = a.id
    WHERE t.tag_type = 'curator'
    ORDER BY a.id, t.tag_text
""").fetchall()
for r in cur_rows:
    print(f"  {r['local_id']:40s} | {r['tag_text']:25s} | {r['source_method']}")
print(f"\nTotal curator tags: {len(cur_rows)}")

db.close()
