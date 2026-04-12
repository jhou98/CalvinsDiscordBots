"""
DraftStore — dict subclass that auto-persists drafts to SQLite.

Drop-in replacement for the module-level ``drafts: dict[DraftKey, DraftXxx] = {}``
in each cog.  Creates and deletes are automatic via __setitem__ and pop.
In-place mutations require an explicit ``save(key)`` call.
"""

import json
import logging
from dataclasses import fields as dc_fields
from datetime import UTC, datetime

from src.db import delete_draft, load_drafts_by_command, upsert_draft
from src.models.draft_base import DraftBase
from src.views.draft_view_base import DraftKey

log = logging.getLogger(__name__)

# Maps command name -> draft model class for deserialization
_MODEL_REGISTRY: dict[str, type] = {}


def register_model(command: str, model_cls: type) -> None:
    """Register a draft model class for a command name."""
    _MODEL_REGISTRY[command] = model_cls


def _serialize(draft: DraftBase) -> dict:
    """
    Convert a draft dataclass to a JSON-safe dict.

    Uses ``dataclasses.fields()`` instead of ``asdict()`` to avoid deep-copying
    the non-serializable ``discord.Message`` reference.  ``message`` and
    ``created_at`` are excluded (created_at lives in its own DB column).
    """
    return {
        f.name: getattr(draft, f.name)
        for f in dc_fields(draft)
        if f.name not in ("message", "created_at")
    }


def _deserialize(command: str, created_at_iso: str, data_json: str) -> DraftBase | None:
    """
    Reconstruct a draft model from its stored JSON and command name.
    Returns None if the command is unknown or the data is malformed.
    """
    cls = _MODEL_REGISTRY.get(command)
    if cls is None:
        log.warning("Unknown command %r in draft DB — skipping", command)
        return None

    try:
        data = json.loads(data_json)
    except json.JSONDecodeError:
        log.error("Corrupt JSON for command %r — skipping", command)
        return None

    # JSON converts tuples to lists; convert materials back to list[tuple[str, str]]
    if "materials" in data and isinstance(data["materials"], list):
        data["materials"] = [tuple(item) for item in data["materials"]]

    created_at = datetime.fromisoformat(created_at_iso)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)

    try:
        return cls(created_at=created_at, **data)
    except TypeError as e:
        log.error("Deserialization failed for command %r: %s — skipping", command, e)
        return None


class DraftStore(dict):
    """
    dict subclass that auto-persists to SQLite on create/delete.

    Usage (in each cog, replacing the module-level dict)::

        from src.db.draft_store import DraftStore, register_model
        register_model(COMMAND, DraftRfi)
        drafts: DraftStore = DraftStore.load_from_db(COMMAND)
    """

    def __init__(self, command_name: str):
        super().__init__()
        self._command_name = command_name

    def __setitem__(self, key: DraftKey, draft: DraftBase) -> None:
        super().__setitem__(key, draft)
        self._persist(key, draft)

    def pop(self, key: DraftKey, *args):
        had_key = key in self
        result = super().pop(key, *args)
        if had_key:
            user_id, channel_id, command = key
            try:
                delete_draft(user_id, channel_id, command)
            except Exception:
                log.exception("DB delete failed for key %s — continuing", key)
        return result

    def save(self, key: DraftKey) -> None:
        """Persist the current state of an in-place-mutated draft."""
        draft = self.get(key)
        if draft is not None:
            self._persist(key, draft)

    def _persist(self, key: DraftKey, draft: DraftBase) -> None:
        user_id, channel_id, command = key
        try:
            upsert_draft(user_id, channel_id, command, draft.created_at, _serialize(draft))
        except Exception:
            log.exception("DB upsert failed for key %s — continuing in-memory", key)

    @classmethod
    def load_from_db(cls, command_name: str) -> "DraftStore":
        """
        Create a DraftStore pre-populated with non-expired drafts from the DB.
        Expired rows are deleted as a cleanup step.
        """
        from src.views.draft_view_base import is_expired

        store = cls(command_name)
        try:
            rows = load_drafts_by_command(command_name)
        except Exception:
            log.exception("Failed to load drafts from DB — starting empty")
            return store

        for user_id, channel_id, command, created_at_iso, data_json in rows:
            draft = _deserialize(command, created_at_iso, data_json)
            if draft is None:
                try:
                    delete_draft(user_id, channel_id, command)
                except Exception:
                    log.exception(
                        "Failed to delete corrupt row (%s, %s, %s)",
                        user_id,
                        channel_id,
                        command,
                    )
                continue

            key: DraftKey = (user_id, channel_id, command)
            if is_expired(draft):
                log.info("Deleting expired draft on load: %s", key)
                try:
                    delete_draft(user_id, channel_id, command)
                except Exception:
                    log.exception("Failed to delete expired row %s", key)
                continue

            # Use dict.__setitem__ to avoid re-writing to DB what we just read
            dict.__setitem__(store, key, draft)

        loaded = len(store)
        if loaded:
            log.info("Loaded %d %s draft(s) from DB", loaded, command_name)
        return store
