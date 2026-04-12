"""Tests for src/db.py — SQLite persistence layer."""

import json
from datetime import UTC, datetime

import pytest

from src.db import close_db, delete_draft, init_db, load_drafts_by_command, upsert_draft


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    """Each test gets its own database file."""
    init_db(tmp_path / "test.db")
    yield
    close_db()


def test_init_creates_table(tmp_path):
    """init_db creates the drafts table and data directory."""
    db_path = tmp_path / "sub" / "drafts.db"
    close_db()
    init_db(db_path)
    assert db_path.exists()
    rows = load_drafts_by_command("rfi")
    assert rows == []


def test_upsert_and_load():
    """Round-trip a draft through upsert and load."""
    now = datetime.now(UTC)
    data = {"field_a": "hello", "field_b": 42}
    upsert_draft("user1", "chan1", "rfi", now, data)

    rows = load_drafts_by_command("rfi")
    assert len(rows) == 1
    user_id, channel_id, command, created_at_iso, data_json = rows[0]
    assert user_id == "user1"
    assert channel_id == "chan1"
    assert command == "rfi"
    assert created_at_iso == now.isoformat()
    assert json.loads(data_json) == data


def test_upsert_replaces_on_conflict():
    """Same primary key overwrites the existing row."""
    now = datetime.now(UTC)
    upsert_draft("u", "c", "cmd", now, {"v": 1})
    upsert_draft("u", "c", "cmd", now, {"v": 2})

    rows = load_drafts_by_command("cmd")
    assert len(rows) == 1
    assert json.loads(rows[0][4]) == {"v": 2}


def test_delete_removes_row():
    """delete_draft removes the row for the given key."""
    now = datetime.now(UTC)
    upsert_draft("u", "c", "cmd", now, {"x": 1})
    delete_draft("u", "c", "cmd")

    assert load_drafts_by_command("cmd") == []


def test_delete_missing_row_no_error():
    """Deleting a non-existent row is a no-op."""
    delete_draft("no", "such", "key")  # should not raise


def test_multiple_commands():
    """Multiple rows with different commands coexist."""
    now = datetime.now(UTC)
    upsert_draft("u", "c", "rfi", now, {"a": 1})
    upsert_draft("u", "c", "matorder", now, {"b": 2})

    rfi_rows = load_drafts_by_command("rfi")
    assert len(rfi_rows) == 1
    assert rfi_rows[0][2] == "rfi"

    matorder_rows = load_drafts_by_command("matorder")
    assert len(matorder_rows) == 1
    assert matorder_rows[0][2] == "matorder"


def test_load_empty_db():
    """load_drafts_by_command returns empty list on a fresh database."""
    assert load_drafts_by_command("rfi") == []


def test_operations_without_init():
    """When DB is not initialized, operations are no-ops."""
    close_db()
    # Should not raise — just log warnings and return gracefully
    upsert_draft("u", "c", "cmd", datetime.now(UTC), {})
    delete_draft("u", "c", "cmd")
    assert load_drafts_by_command("cmd") == []
