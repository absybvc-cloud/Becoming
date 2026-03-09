import json
import sqlite3
from pathlib import Path
from typing import Optional

from .models import ReviewAsset


DB_PATH = "library/becoming.db"
MANIFEST_PATH = "assets/library/manifest.json"


def load_from_db(
    db_path: str = DB_PATH,
    status: Optional[object] = "pending_review",
    source: Optional[str] = None,
    limit: Optional[int] = None,
    order: str = "random",
) -> list[ReviewAsset]:
    if not Path(db_path).exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # join with candidate_items to get title/creator/source_tags
    where_clauses: list[str] = []
    params: list = []

    # status may be: None (no filter), a single status string, or an iterable of statuses
    if status is None:
        pass
    elif isinstance(status, (list, tuple, set)):
        placeholders = ",".join("?" for _ in status)
        where_clauses.append(f"a.approval_status IN ({placeholders})")
        params.extend(list(status))
    else:
        where_clauses.append("a.approval_status = ?")
        params.append(status)

    if source:
        where_clauses.append("c.source_name = ?")
        params.append(source)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    order_sql = {
        "random": "RANDOM()",
        "world_fit": "a.world_fit_score DESC",
        "newest": "a.created_at DESC",
    }.get(order, "RANDOM()")

    limit_sql = f"LIMIT {int(limit)}" if limit else ""

    rows = conn.execute(
        f"""
        SELECT
            a.id, a.local_id, a.normalized_file_path, a.duration_seconds,
            a.world_fit_score, a.pulse_fit_score, a.drift_fit_score,
            a.quality_score, a.approval_status, a.silence_ratio, a.rms,
            c.source_name, c.title, c.creator, c.source_tags_json
        FROM audio_assets a
        JOIN candidate_items c ON a.candidate_item_id = c.id
        WHERE {where_sql}
        ORDER BY {order_sql}
        {limit_sql}
        """,
        params,
    ).fetchall()

    # also fetch becoming/curator tags already stored
    assets = []
    for row in rows:
        existing_tags = _get_asset_tags(conn, row["id"], tag_types=("becoming", "curator"))
        source_tags = _parse_json_list(row["source_tags_json"])

        assets.append(ReviewAsset(
            asset_id=row["id"],
            local_id=row["local_id"],
            source_name=row["source_name"],
            duration_seconds=row["duration_seconds"] or 0.0,
            normalized_file_path=row["normalized_file_path"],
            source_tags=source_tags,
            model_tags=existing_tags,
            world_fit_score=row["world_fit_score"],
            pulse_fit_score=row["pulse_fit_score"],
            drift_fit_score=row["drift_fit_score"],
            quality_score=row["quality_score"],
            approval_status=row["approval_status"],
            title=row["title"],
            creator=row["creator"],
            silence_ratio=row["silence_ratio"],
            rms=row["rms"],
        ))
    conn.close()
    return assets


def _get_asset_tags(conn: sqlite3.Connection, asset_id: int, tag_types: tuple) -> list[str]:
    placeholders = ",".join("?" for _ in tag_types)
    rows = conn.execute(
        f"""SELECT t.tag_text FROM tags t
            JOIN asset_tags at ON at.tag_id = t.id
            WHERE at.asset_id = ? AND t.tag_type IN ({placeholders})""",
        (asset_id, *tag_types),
    ).fetchall()
    return [r["tag_text"] for r in rows]


def _parse_json_list(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        if isinstance(val, list):
            return [str(v) for v in val]
    except Exception:
        pass
    return []


def load_from_manifest(manifest_path: str = MANIFEST_PATH) -> list[ReviewAsset]:
    if not Path(manifest_path).exists():
        return []
    with open(manifest_path) as f:
        entries = json.load(f)
    assets = []
    for i, e in enumerate(entries):
        assets.append(ReviewAsset(
            asset_id=i,
            local_id=e.get("id", f"unknown_{i}"),
            source_name=e.get("source_name", "unknown"),
            duration_seconds=e.get("duration", 0.0),
            normalized_file_path=e.get("file_path", ""),
            source_tags=e.get("tags", []),
        ))
    return assets
