"""
Tests for views/edit_modal_base.py — shared EditModalBase.

Uses a minimal concrete subclass to test the base class behavior
in isolation from any cog-specific logic.
"""

from unittest.mock import MagicMock

import discord

from src.models.draft_base import DraftBase
from src.views.edit_modal_base import EditModalBase
from tests.conftest import make_interaction

_TEST_KEY = ("111", "222", "testcmd")


class _FakeDraft(DraftBase):
    """Minimal draft with a single editable field."""

    value: str = "original"


class _FakeEditModal(EditModalBase, title="Fake Edit"):
    """Concrete subclass for testing the base class."""

    def _pre_fill(self, draft):
        self._captured_value = draft.value

    def _apply(self, draft) -> str | None:
        draft.value = "updated"
        return None


class _FailingEditModal(EditModalBase, title="Failing Edit"):
    """Returns an error from _apply."""

    def _pre_fill(self, draft):
        pass

    def _apply(self, draft) -> str | None:
        return "⚠️ Something went wrong."


def _make_store():
    store = {_TEST_KEY: _FakeDraft()}
    embed_fn = MagicMock(return_value=MagicMock(spec=discord.Embed))
    view_cls = MagicMock()
    return store, embed_fn, view_cls


class TestEditModalBase:
    async def test_pre_fill_called_on_init(self):
        store, embed_fn, view_cls = _make_store()
        modal = _FakeEditModal(_TEST_KEY, store, embed_fn, view_cls)
        assert modal._captured_value == "original"

    async def test_successful_apply_updates_draft(self):
        store, embed_fn, view_cls = _make_store()
        modal = _FakeEditModal(_TEST_KEY, store, embed_fn, view_cls)
        interaction, msg = make_interaction(user_id="111", channel_id="222")
        interaction.message = msg
        await modal.on_submit(interaction)
        assert store[_TEST_KEY].value == "updated"

    async def test_successful_apply_edits_message(self):
        store, embed_fn, view_cls = _make_store()
        modal = _FakeEditModal(_TEST_KEY, store, embed_fn, view_cls)
        interaction, msg = make_interaction(user_id="111", channel_id="222")
        interaction.message = msg
        await modal.on_submit(interaction)
        interaction.response.edit_message.assert_called_once()

    async def test_apply_error_sends_ephemeral(self):
        store, embed_fn, view_cls = _make_store()
        modal = _FailingEditModal(_TEST_KEY, store, embed_fn, view_cls)
        interaction, msg = make_interaction(user_id="111", channel_id="222")
        interaction.message = msg
        await modal.on_submit(interaction)
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True
        assert "Something went wrong" in interaction.response.send_message.call_args.args[0]

    async def test_apply_error_does_not_edit_message(self):
        store, embed_fn, view_cls = _make_store()
        modal = _FailingEditModal(_TEST_KEY, store, embed_fn, view_cls)
        interaction, msg = make_interaction(user_id="111", channel_id="222")
        interaction.message = msg
        await modal.on_submit(interaction)
        interaction.response.edit_message.assert_not_called()

    async def test_missing_draft_sends_ephemeral(self):
        store, embed_fn, view_cls = _make_store()
        modal = _FakeEditModal(_TEST_KEY, store, embed_fn, view_cls)
        store.clear()
        interaction, _ = make_interaction(user_id="111", channel_id="222")
        await modal.on_submit(interaction)
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_missing_draft_does_not_call_apply(self):
        store, embed_fn, view_cls = _make_store()
        modal = _FakeEditModal(_TEST_KEY, store, embed_fn, view_cls)
        store.clear()
        interaction, _ = make_interaction(user_id="111", channel_id="222")
        await modal.on_submit(interaction)
        # _apply would call edit_message after updating — verify it wasn't reached
        interaction.response.edit_message.assert_not_called()
