"""Tests for src/draft_store.py — DraftStore class."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.db import close_db, init_db, load_drafts_by_command
from src.db.draft_store import DraftStore, _deserialize, _serialize, register_model
from src.models.draft_change_order import DraftChangeOrder
from src.models.draft_rfi import DraftRfi
from src.views.draft_view_base import DRAFT_TTL_SECONDS


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    """Each test gets its own database file and clean model registry."""
    init_db(tmp_path / "test.db")
    register_model("rfi", DraftRfi)
    register_model("changeorder", DraftChangeOrder)
    yield
    close_db()


def _make_rfi(**overrides) -> DraftRfi:
    defaults = {
        "date_requested": "01/01/2025",
        "requested_by": "Jack",
        "questions": "What gauge?",
        "issues": "Plans unclear",
        "proposed_solution": "Use 12 AWG",
        "impact": "Work stops",
        "required_by": "02/01/2025",
        "submitted_at": "<t:1234567890:F>",
    }
    defaults.update(overrides)
    return DraftRfi(**defaults)


def _make_change_order(**overrides) -> DraftChangeOrder:
    defaults = {
        "date_requested": "01/01/2025",
        "submitted_at": "<t:1234567890:F>",
        "scope": "Add outlets",
        "materials": [("Breaker", "3"), ("Wire", "2")],
    }
    defaults.update(overrides)
    return DraftChangeOrder(**defaults)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialize:
    def test_excludes_message(self):
        draft = _make_rfi()
        data = _serialize(draft)
        assert "message" not in data

    def test_excludes_created_at(self):
        draft = _make_rfi()
        data = _serialize(draft)
        assert "created_at" not in data

    def test_includes_all_other_fields(self):
        draft = _make_rfi()
        data = _serialize(draft)
        assert data["date_requested"] == "01/01/2025"
        assert data["requested_by"] == "Jack"
        assert data["impact"] == "Work stops"

    def test_materials_roundtrip(self):
        """list[tuple[str,str]] survives serialize -> deserialize."""
        draft = _make_change_order()
        data = _serialize(draft)
        # JSON will have converted tuples to lists
        assert data["materials"] == [("Breaker", "3"), ("Wire", "2")]

        restored = _deserialize(
            "changeorder",
            draft.created_at.isoformat(),
            __import__("json").dumps(data),
        )
        assert restored is not None
        assert restored.materials == [("Breaker", "3"), ("Wire", "2")]
        assert all(isinstance(m, tuple) for m in restored.materials)


class TestDeserialize:
    def test_unknown_command_returns_none(self):
        result = _deserialize("nosuchcommand", datetime.now(UTC).isoformat(), "{}")
        assert result is None

    def test_corrupt_json_returns_none(self):
        result = _deserialize("rfi", datetime.now(UTC).isoformat(), "not json!")
        assert result is None

    def test_missing_field_returns_none(self):
        """If required constructor args are missing, deserialization fails gracefully."""
        result = _deserialize("rfi", datetime.now(UTC).isoformat(), '{"only_one": "field"}')
        assert result is None

    def test_naive_datetime_gets_utc(self):
        """A created_at without timezone info gets UTC attached."""
        naive_iso = "2025-01-01T12:00:00"
        draft = _deserialize("rfi", naive_iso, __import__("json").dumps(_serialize(_make_rfi())))
        assert draft is not None
        assert draft.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# DraftStore
# ---------------------------------------------------------------------------


class TestDraftStore:
    def test_setitem_persists(self):
        store = DraftStore("rfi")
        key = ("user1", "chan1", "rfi")
        store[key] = _make_rfi()

        rows = load_drafts_by_command("rfi")
        assert len(rows) == 1
        assert rows[0][0] == "user1"

    def test_pop_deletes(self):
        store = DraftStore("rfi")
        key = ("user1", "chan1", "rfi")
        store[key] = _make_rfi()
        store.pop(key)

        assert key not in store
        assert load_drafts_by_command("rfi") == []

    def test_pop_missing_key_with_default(self):
        store = DraftStore("rfi")
        result = store.pop(("no", "such", "key"), None)
        assert result is None

    def test_pop_missing_key_without_default(self):
        store = DraftStore("rfi")
        with pytest.raises(KeyError):
            store.pop(("no", "such", "key"))

    def test_save_persists_mutations(self):
        store = DraftStore("rfi")
        key = ("user1", "chan1", "rfi")
        store[key] = _make_rfi()

        # Mutate in-place
        store[key].questions = "Updated question"
        store.save(key)

        # Load fresh from DB
        fresh = DraftStore.load_from_db("rfi")
        assert fresh[key].questions == "Updated question"

    def test_save_noop_for_missing_key(self):
        store = DraftStore("rfi")
        store.save(("no", "such", "key"))  # should not raise

    def test_load_from_db_roundtrip(self):
        store = DraftStore("rfi")
        key = ("user1", "chan1", "rfi")
        store[key] = _make_rfi()

        fresh = DraftStore.load_from_db("rfi")
        assert key in fresh
        assert fresh[key].requested_by == "Jack"
        assert fresh[key].impact == "Work stops"

    def test_load_from_db_filters_by_command(self):
        rfi_store = DraftStore("rfi")
        co_store = DraftStore("changeorder")
        rfi_key = ("user1", "chan1", "rfi")
        co_key = ("user1", "chan1", "changeorder")
        rfi_store[rfi_key] = _make_rfi()
        co_store[co_key] = _make_change_order()

        loaded_rfi = DraftStore.load_from_db("rfi")
        assert rfi_key in loaded_rfi
        assert co_key not in loaded_rfi

    def test_load_from_db_skips_expired(self):
        store = DraftStore("rfi")
        key = ("user1", "chan1", "rfi")
        expired_draft = _make_rfi(
            created_at=datetime.now(UTC) - timedelta(seconds=DRAFT_TTL_SECONDS + 60)
        )
        store[key] = expired_draft

        fresh = DraftStore.load_from_db("rfi")
        assert key not in fresh
        # Expired row should be deleted from DB too
        assert load_drafts_by_command("rfi") == []

    def test_load_from_db_handles_corrupt_json(self):
        """A row with invalid JSON is skipped and deleted."""
        from src.db import _conn

        _conn.execute(
            "INSERT INTO drafts VALUES (?, ?, ?, ?, ?)",
            ("u", "c", "rfi", datetime.now(UTC).isoformat(), "not json"),
        )
        _conn.commit()

        fresh = DraftStore.load_from_db("rfi")
        assert len(fresh) == 0
        # Corrupt row should be cleaned up
        assert load_drafts_by_command("rfi") == []

    def test_db_failure_does_not_crash_setitem(self):
        store = DraftStore("rfi")
        key = ("user1", "chan1", "rfi")
        draft = _make_rfi()

        with patch("src.db.draft_store.upsert_draft", side_effect=Exception("DB down")):
            store[key] = draft  # should not raise

        # In-memory store still works
        assert key in store

    def test_db_failure_does_not_crash_pop(self):
        store = DraftStore("rfi")
        key = ("user1", "chan1", "rfi")
        store[key] = _make_rfi()

        with patch("src.db.draft_store.delete_draft", side_effect=Exception("DB down")):
            result = store.pop(key)  # should not raise

        assert result is not None
        assert key not in store
