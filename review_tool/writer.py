import sqlite3
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import ReviewRecord

DB_PATH = "library/becoming.db"
CURATED_ROOT = "library/curated"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_review(record: ReviewRecord, db_path: str = DB_PATH):
    """Persist a review decision back to the database."""
    if not Path(db_path).exists():
        print(f"[writer] DB not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    now = utcnow()

    # map decision to approval_status
    status_map = {
        "keep":   "approved",
        "maybe":  "pending_review",
        "reject": "rejected",
        "skip":   None,  # no change
    }
    new_status = status_map.get(record.decision)

    if new_status is not None:
        conn.execute(
            "UPDATE audio_assets SET approval_status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, record.asset_id),
        )

    # write review_action row
    if record.decision != "skip":
        action_type = {
            "keep": "approve",
            "maybe": "approve",
            "reject": "reject",
        }.get(record.decision, "approve")

        conn.execute(
            """INSERT INTO review_actions (asset_id, action_type, reviewer, notes, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (record.asset_id, action_type, "curator", record.notes or "", now),
        )

    # role tag
    if record.role and record.role != "none":
        _upsert_tag_on_asset(conn, record.asset_id, record.role, "curator")

    # becoming tags
    for tag in record.becoming_tags:
        tag = tag.strip()
        if tag:
            _upsert_tag_on_asset(conn, record.asset_id, tag, "becoming")

    conn.commit()
    conn.close()


def _upsert_tag_on_asset(conn: sqlite3.Connection, asset_id: int, tag_text: str, tag_type: str):
    row = conn.execute(
        "SELECT id FROM tags WHERE tag_text = ? AND tag_type = ?",
        (tag_text, tag_type),
    ).fetchone()
    if row:
        tag_id = row[0]
    else:
        cur = conn.execute(
            "INSERT INTO tags (tag_text, tag_type, created_at) VALUES (?, ?, ?)",
            (tag_text, tag_type, utcnow()),
        )
        tag_id = cur.lastrowid

    conn.execute(
        """INSERT OR IGNORE INTO asset_tags (asset_id, tag_id, confidence, source_method, created_at)
           VALUES (?, ?, NULL, 'curator_review', ?)""",
        (asset_id, tag_id, utcnow()),
    )


def promote_asset(
    asset_id: int,
    normalized_file_path: str,
    decision: str,
    role: str,
    db_path: str = DB_PATH,
    curated_root: str = CURATED_ROOT,
):
    """Create a symlink in library/curated/<decision>/<role>/."""
    if decision not in ("keep", "maybe", "reject"):
        return

    if decision == "keep":
        folder = Path(curated_root) / "keep" / (role if role != "none" else "unassigned")
    else:
        folder = Path(curated_root) / decision

    folder.mkdir(parents=True, exist_ok=True)

    src = Path(normalized_file_path).resolve()
    if not src.exists():
        return

    dest = folder / src.name
    if dest.exists() or dest.is_symlink():
        dest.unlink()

    try:
        dest.symlink_to(src)
    except Exception:
        # fallback: copy
        try:
            shutil.copy2(src, dest)
        except Exception as e:
            print(f"[writer] promote failed: {e}")
