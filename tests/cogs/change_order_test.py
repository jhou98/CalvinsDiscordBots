"""
Tests for cogs/change_order.py — the /changeorder command.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from src.cogs.change_order import (
    COMMAND,
    ChangeOrder,
    DraftView,
    ScopeModal,
    SubmittedView,
    _draft_embed,
    _final_embed,
    drafts,
)
from src.models.draft_change_order import DraftChangeOrder
from src.views.draft_view_base import (
    DRAFT_TTL_SECONDS,
    _is_numeric,
    draft_key,
    evict,
    is_expired,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_KEY = ("123456789", "222", COMMAND)


def _seed_draft(draft_key_val: tuple = _TEST_KEY, *, expired: bool = False):
    age = timedelta(seconds=DRAFT_TTL_SECONDS + 60) if expired else timedelta(seconds=0)
    drafts[draft_key_val] = DraftChangeOrder(
        date="01/01/2025",
        submitted_at="<t:1234567890:F>",
        scope="Install panel",
        created_at=datetime.now(UTC) - age,
    )
    return drafts[draft_key_val]


def _clear_drafts():
    drafts.clear()


def _make_interaction(user_id="123456789", channel_id="222"):
    mock_message = MagicMock(spec=discord.Message)
    mock_message.edit = AsyncMock()
    user = MagicMock(spec=discord.Member)
    user.id = user_id
    user.mention = f"<@{user_id}>"
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = user
    interaction.channel_id = channel_id
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.original_response = AsyncMock(return_value=mock_message)
    return interaction, mock_message


# ---------------------------------------------------------------------------
# is_expired / evict
# ---------------------------------------------------------------------------

class TestIsExpired:
    def test_fresh_draft_not_expired(self):
        draft = _seed_draft()
        assert is_expired(draft) is False

    def test_stale_draft_is_expired(self):
        draft = _seed_draft(expired=True)
        assert is_expired(draft) is True


class TestEvict:
    def setup_method(self):
        _clear_drafts()

    async def test_evict_removes_from_store(self):
        _seed_draft()
        await evict(drafts, _TEST_KEY)
        assert _TEST_KEY not in drafts

    async def test_evict_edits_message(self, mock_message):
        draft = _seed_draft()
        draft.message = mock_message
        await evict(drafts, _TEST_KEY)
        mock_message.edit.assert_called_once()
        assert "expired" in mock_message.edit.call_args.kwargs.get("content", "").lower()

    async def test_evict_without_message_does_not_raise(self):
        _seed_draft()
        await evict(drafts, _TEST_KEY)

    async def test_evict_handles_not_found(self, mock_message):
        draft = _seed_draft()
        draft.message = mock_message
        mock_message.edit = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        await evict(drafts, _TEST_KEY)

    async def test_evict_handles_http_exception(self, mock_message):
        draft = _seed_draft()
        draft.message = mock_message
        mock_message.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))
        await evict(drafts, _TEST_KEY)

    async def test_evict_nonexistent_key_does_not_raise(self):
        await evict(drafts, ("0", "0", "noop"))


# ---------------------------------------------------------------------------
# ScopeModal
# ---------------------------------------------------------------------------

class TestScopeModal:
    def setup_method(self):
        _clear_drafts()

    def _make_modal(self, date="", scope="Install panel", materials_text=""):
        modal = ScopeModal()
        modal.date_requested = MagicMock()
        modal.date_requested.value = date
        modal.scope_added = MagicMock()
        modal.scope_added.value = scope
        modal.materials_input = MagicMock()
        modal.materials_input.value = materials_text
        return modal

    async def test_creates_draft_on_submit(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        assert draft_key(mock_interaction, COMMAND) in drafts

    async def test_draft_is_correct_type(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        assert isinstance(drafts[draft_key(mock_interaction, COMMAND)], DraftChangeOrder)

    async def test_draft_contains_correct_scope(self, mock_interaction):
        await self._make_modal(scope="Run new circuits").on_submit(mock_interaction)
        assert drafts[draft_key(mock_interaction, COMMAND)].scope == "Run new circuits"

    async def test_draft_materials_empty_when_none_provided(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        assert drafts[draft_key(mock_interaction, COMMAND)].materials == []

    async def test_draft_seeded_with_initial_materials(self, mock_interaction):
        await self._make_modal(materials_text="Breaker - 3\nWire - 2").on_submit(mock_interaction)
        materials = drafts[draft_key(mock_interaction, COMMAND)].materials
        assert ("Breaker", "3") in materials
        assert ("Wire", "2") in materials

    async def test_invalid_initial_material_format_sends_ephemeral(self, mock_interaction):
        await self._make_modal(materials_text="BadLine").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_invalid_initial_material_does_not_create_draft(self, mock_interaction):
        await self._make_modal(materials_text="BadLine").on_submit(mock_interaction)
        assert draft_key(mock_interaction, COMMAND) not in drafts

    async def test_non_numeric_initial_quantity_sends_ephemeral(self, mock_interaction):
        await self._make_modal(materials_text="Breaker - lots").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_non_numeric_initial_quantity_does_not_create_draft(self, mock_interaction):
        await self._make_modal(materials_text="Breaker - lots").on_submit(mock_interaction)
        assert draft_key(mock_interaction, COMMAND) not in drafts

    async def test_draft_message_stored(self, mock_interaction, mock_message):
        await self._make_modal().on_submit(mock_interaction)
        assert drafts[draft_key(mock_interaction, COMMAND)].message is mock_message

    async def test_draft_created_at_is_recent(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        draft = drafts[draft_key(mock_interaction, COMMAND)]
        assert (datetime.now(UTC) - draft.created_at).total_seconds() < 5

    async def test_sends_embed_and_view(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert isinstance(kwargs.get("embed"), discord.Embed)
        assert kwargs.get("view") is not None

    async def test_view_message_set(self, mock_interaction, mock_message):
        await self._make_modal().on_submit(mock_interaction)
        view = mock_interaction.response.send_message.call_args.kwargs["view"]
        assert view.message is mock_message

    async def test_invalid_date_sends_ephemeral(self, mock_interaction):
        await self._make_modal(date="2026-03-15").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_invalid_date_does_not_create_draft(self, mock_interaction):
        await self._make_modal(date="2026-03-15").on_submit(mock_interaction)
        assert draft_key(mock_interaction, COMMAND) not in drafts


# ---------------------------------------------------------------------------
# DraftView buttons
# ---------------------------------------------------------------------------

class TestDraftViewUndoLast:
    def setup_method(self):
        _clear_drafts()

    async def test_undo_removes_last_material(self, mock_interaction, mock_message):
        _seed_draft()
        drafts[_TEST_KEY].materials = [("A", "1"), ("B", "2")]
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).undo_last.callback(mock_interaction)
        assert drafts[_TEST_KEY].materials == [("A", "1")]

    async def test_undo_empty_sends_ephemeral(self, mock_interaction):
        _seed_draft()
        await DraftView(_TEST_KEY).undo_last.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_undo_expired_sends_ephemeral(self, mock_interaction):
        _seed_draft(expired=True)
        await DraftView(_TEST_KEY).undo_last.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


class TestDraftViewDone:
    def setup_method(self):
        _clear_drafts()

    async def test_done_removes_draft(self, mock_interaction, mock_message):
        _seed_draft()
        drafts[_TEST_KEY].materials = [("Breaker", "2")]
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert _TEST_KEY not in drafts

    async def test_done_edits_to_final_embed(self, mock_interaction, mock_message):
        _seed_draft()
        drafts[_TEST_KEY].materials = [("Breaker", "2")]
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        edited_embed = mock_message.edit.call_args.kwargs.get("embed")
        assert isinstance(edited_embed, discord.Embed)
        assert "Submitted" in edited_embed.title

    async def test_done_swaps_to_submitted_view(self, mock_interaction, mock_message):
        _seed_draft()
        drafts[_TEST_KEY].materials = [("Breaker", "2")]
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert isinstance(mock_message.edit.call_args.kwargs.get("view"), SubmittedView)

    async def test_done_no_materials_sends_ephemeral(self, mock_interaction, mock_message):
        _seed_draft()
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_done_no_materials_does_not_remove_draft(self, mock_interaction, mock_message):
        _seed_draft()
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert _TEST_KEY in drafts

    async def test_done_expired_sends_ephemeral(self, mock_interaction, mock_message):
        _seed_draft(expired=True)
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


class TestDraftViewCancel:
    def setup_method(self):
        _clear_drafts()

    async def test_cancel_removes_draft(self, mock_interaction, mock_message):
        _seed_draft()
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).cancel.callback(mock_interaction)
        assert _TEST_KEY not in drafts

    async def test_cancel_disables_buttons(self, mock_interaction, mock_message):
        _seed_draft()
        mock_interaction.message = mock_message
        view = DraftView(_TEST_KEY)
        await view.cancel.callback(mock_interaction)
        assert all(child.disabled for child in view.children)

    async def test_cancel_expired_sends_ephemeral(self, mock_interaction, mock_message):
        _seed_draft(expired=True)
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).cancel.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


class TestDraftViewInteractionCheck:
    async def test_wrong_user_blocked(self, mock_interaction):
        wrong_key = ("999", "222", COMMAND)
        result = await DraftView(wrong_key).interaction_check(mock_interaction)
        assert result is False
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_correct_user_allowed(self, mock_interaction):
        result = await DraftView(_TEST_KEY).interaction_check(mock_interaction)
        assert result is True


async def test_draft_view_has_no_timeout():
    assert DraftView(_TEST_KEY).timeout is None


# ---------------------------------------------------------------------------
# SubmittedView
# ---------------------------------------------------------------------------

class TestSubmittedView:
    async def test_copy_text_sends_ephemeral(self, mock_interaction):
        await SubmittedView("text").copy_text.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_copy_text_contains_plain_text(self, mock_interaction):
        await SubmittedView("some plain text").copy_text.callback(mock_interaction)
        sent = mock_interaction.response.send_message.call_args.args[0]
        assert "some plain text" in sent

    async def test_copy_text_wrapped_in_code_block(self, mock_interaction):
        await SubmittedView("text").copy_text.callback(mock_interaction)
        sent = mock_interaction.response.send_message.call_args.args[0]
        assert sent.startswith("```") and sent.endswith("```")

    async def test_submitted_view_has_no_timeout(self):
        assert SubmittedView("text").timeout is None


# ---------------------------------------------------------------------------
# Background sweep
# ---------------------------------------------------------------------------

class TestSweepExpiredDrafts:
    def setup_method(self):
        _clear_drafts()

    async def test_sweep_removes_expired(self):
        _seed_draft(expired=True)
        cog = ChangeOrder(MagicMock())
        cog._stop_sweep()
        await cog._do_sweep()
        assert _TEST_KEY not in drafts

    async def test_sweep_preserves_fresh(self):
        _seed_draft(expired=False)
        cog = ChangeOrder(MagicMock())
        cog._stop_sweep()
        await cog._do_sweep()
        assert _TEST_KEY in drafts

    async def test_sweep_edits_expired_message(self, mock_message):
        draft = _seed_draft(expired=True)
        draft.message = mock_message
        cog = ChangeOrder(MagicMock())
        cog._stop_sweep()
        await cog._do_sweep()
        mock_message.edit.assert_called_once()


# ---------------------------------------------------------------------------
# Multi-channel isolation
# ---------------------------------------------------------------------------

class TestMultiChannelIsolation:
    def setup_method(self):
        _clear_drafts()

    async def test_same_user_different_channels_independent(self):
        key_ch1 = ("123456789", "222", COMMAND)
        key_ch2 = ("123456789", "333", COMMAND)
        _seed_draft(key_ch1)
        _seed_draft(key_ch2)
        drafts[key_ch1].materials = [("A", "1")]
        drafts[key_ch2].materials = [("B", "2")]
        assert drafts[key_ch1].materials != drafts[key_ch2].materials

    async def test_same_user_same_channel_blocks(self):
        interaction, _ = _make_interaction()
        _seed_draft(_TEST_KEY)
        cog = ChangeOrder(MagicMock())
        cog._stop_sweep()
        await cog.change_order.callback(cog, interaction)
        interaction.response.send_modal.assert_not_called()
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_same_user_different_channel_allowed(self):
        _seed_draft(_TEST_KEY)
        interaction, _ = _make_interaction(channel_id="333")
        cog = ChangeOrder(MagicMock())
        cog._stop_sweep()
        await cog.change_order.callback(cog, interaction)
        interaction.response.send_modal.assert_called_once()

    async def test_expired_draft_allows_new_command(self, mock_interaction):
        _seed_draft(_TEST_KEY, expired=True)
        cog = ChangeOrder(MagicMock())
        cog._stop_sweep()
        await cog.change_order.callback(cog, mock_interaction)
        mock_interaction.response.send_modal.assert_called_once()


# ---------------------------------------------------------------------------
# ChangeOrder cog
# ---------------------------------------------------------------------------

class TestChangeOrderCog:
    def setup_method(self):
        _clear_drafts()

    async def test_opens_modal_when_no_draft(self, mock_interaction):
        cog = ChangeOrder(MagicMock())
        cog._stop_sweep()
        await cog.change_order.callback(cog, mock_interaction)
        mock_interaction.response.send_modal.assert_called_once()
        assert isinstance(
            mock_interaction.response.send_modal.call_args.args[0], ScopeModal
        )

    async def test_blocks_second_draft_same_channel(self, mock_interaction):
        _seed_draft(draft_key(mock_interaction, COMMAND))
        cog = ChangeOrder(MagicMock())
        cog._stop_sweep()
        await cog.change_order.callback(cog, mock_interaction)
        mock_interaction.response.send_modal.assert_not_called()
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True