#!/usr/bin/env python3
"""
Deduplicate live mic slices in the database.

Clusters slices by spectral features, keeps the best (highest quality) from
each cluster, and removes the rest — deleting DB rows and audio files.

Usage:
    python scripts/dedup_live_slices.py              # dry run
    python scripts/dedup_live_slices.py --apply       # actually delete
"""

import argparse
import sqlite3
import os
from pathlib import Path

import numpy as np

DB_PATH = os.path.join("library", "becoming.db")
DISTANCE_THRESHOLD = 0.18  # slices closer than this are considered duplicates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually delete duplicates")
    args = parser.parse_args()

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    rows = db.execute("""
        SELECT a.id, a.local_id, a.quality_score, a.duration_seconds,
               a.raw_file_path, a.normalized_file_path,
               f.spectral_centroid_mean, f.spectral_bandwidth_mean,
               f.zero_crossing_rate_mean, f.tonal_confidence,
               f.music_probability, f.noise_probability
        FROM audio_assets a
        JOIN analysis_features f ON f.asset_id = a.id
        WHERE a.local_id LIKE 'local_live_%'
        ORDER BY a.id
    """).fetchall()

    if not rows:
        print("No live slices found.")
        return

    print(f"Total live slices: {len(rows)}")

    # Build normalized feature vectors
    ids = [r["id"] for r in rows]
    quality = [r["quality_score"] or 0 for r in rows]
    raw_paths = [r["raw_file_path"] for r in rows]
    norm_paths = [r["normalized_file_path"] for r in rows]

    vecs = np.array([
        [
            r["spectral_centroid_mean"] or 0,
            r["spectral_bandwidth_mean"] or 0,
            (r["zero_crossing_rate_mean"] or 0) * 10000,
            r["tonal_confidence"] or 0,
            r["music_probability"] or 0,
            r["noise_probability"] or 0,
        ]
        for r in rows
    ], dtype=np.float64)

    # Min-max normalize each column
    for c in range(vecs.shape[1]):
        mn, mx = vecs[:, c].min(), vecs[:, c].max()
        if mx > mn:
            vecs[:, c] = (vecs[:, c] - mn) / (mx - mn)
        else:
            vecs[:, c] = 0.0

    # Greedy clustering: keep the first (or best-quality) in each cluster
    keep = set()
    remove = set()

    for i in range(len(vecs)):
        if ids[i] in remove:
            continue
        keep.add(ids[i])
        for j in range(i + 1, len(vecs)):
            if ids[j] in remove:
                continue
            dist = float(np.linalg.norm(vecs[i] - vecs[j]))
            if dist < DISTANCE_THRESHOLD:
                # Keep the one with higher quality
                if quality[j] > quality[i]:
                    remove.add(ids[i])
                    keep.discard(ids[i])
                    keep.add(ids[j])
                    break  # restart cluster head
                else:
                    remove.add(ids[j])

    print(f"Keep:   {len(keep)}")
    print(f"Remove: {len(remove)}")

    if not remove:
        print("No duplicates found.")
        return

    remove_list = sorted(remove)
    print(f"\nAsset IDs to remove: {remove_list[:30]}{'...' if len(remove_list) > 30 else ''}")

    if not args.apply:
        print("\nDry run — pass --apply to actually delete.")
        return

    # Delete from DB and disk
    deleted_files = 0
    for asset_id in remove_list:
        idx = ids.index(asset_id)
        # Delete files
        for fpath in [raw_paths[idx], norm_paths[idx]]:
            if fpath:
                p = Path(fpath)
                if p.exists():
                    p.unlink()
                    deleted_files += 1

        # Delete DB rows (cascading: asset_tags, analysis_features, then asset)
        db.execute("DELETE FROM asset_tags WHERE asset_id = ?", (asset_id,))
        db.execute("DELETE FROM analysis_features WHERE asset_id = ?", (asset_id,))
        # Delete candidate item too
        cand_id = db.execute(
            "SELECT candidate_item_id FROM audio_assets WHERE id = ?", (asset_id,)
        ).fetchone()
        db.execute("DELETE FROM audio_assets WHERE id = ?", (asset_id,))
        if cand_id and cand_id[0]:
            # Only delete candidate if no other assets reference it
            other = db.execute(
                "SELECT count(*) FROM audio_assets WHERE candidate_item_id = ?",
                (cand_id[0],)
            ).fetchone()[0]
            if other == 0:
                db.execute("DELETE FROM candidate_items WHERE id = ?", (cand_id[0],))

    db.commit()
    db.close()

    print(f"\nDeleted {len(remove_list)} assets from DB, {deleted_files} files from disk.")


if __name__ == "__main__":
    main()
