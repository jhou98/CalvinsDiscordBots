"""
SQLite persistence layer for in-progress drafts.

The database stores drafts as JSON blobs keyed by (user_id, channel_id, command).
Only this module touches the connection — all callers go through these functions.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_conn: sqlite3.Connection | None = None

DB_DIR = Path("data")
DB_PATH = DB_DIR / "drafts.db"


def init_db(path: Path = DB_PATH) -> None:
    """Create the data directory and drafts table. Call once at startup."""
    global _conn
    path.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(path), check_same_thread=False)
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute(
        """
        CREATE TABLE IF NOT EXISTS drafts (
            user_id    TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            command    TEXT NOT NULL,
            created_at TEXT NOT NULL,
            data       TEXT NOT NULL,
            PRIMARY KEY (user_id, channel_id, command)
        )
        """
    )
    _conn.commit()
    log.info("Draft database initialized at %s", path)


def upsert_draft(
    user_id: str,
    channel_id: str,
    command: str,
    created_at: datetime,
    data: dict,
) -> None:
    """Insert or replace a draft row."""
    if _conn is None:
        log.warning("DB not initialized — skipping upsert")
        return
    _conn.execute(
        """
        INSERT OR REPLACE INTO drafts (user_id, channel_id, command, created_at, data)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, channel_id, command, created_at.isoformat(), json.dumps(data)),
    )
    _conn.commit()


def delete_draft(user_id: str, channel_id: str, command: str) -> None:
    """Remove a draft row. No-op if not present."""
    if _conn is None:
        log.warning("DB not initialized — skipping delete")
        return
    _conn.execute(
        "DELETE FROM drafts WHERE user_id = ? AND channel_id = ? AND command = ?",
        (user_id, channel_id, command),
    )
    _conn.commit()


def load_drafts_by_command(command: str) -> list[tuple[str, str, str, str, str]]:
    """
    Return rows for a single command as (user_id, channel_id, command, created_at_iso, data_json).
    Caller is responsible for deserialization and TTL filtering.
    """
    if _conn is None:
        log.warning("DB not initialized — returning empty draft list")
        return []
    cursor = _conn.execute(
        "SELECT user_id, channel_id, command, created_at, data FROM drafts WHERE command = ?",
        (command,),
    )
    return cursor.fetchall()


def close_db() -> None:
    """Close the database connection. Safe to call multiple times."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None
