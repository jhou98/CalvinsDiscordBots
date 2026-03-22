"""
Tests for cogs/change_order.py — the /changeorder command (multi-step flow).
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import discord

from src.cogs.change_order import (
    DRAFT_TTL_SECONDS,
    AddMaterialModal,
    ChangeOrder,
    DraftView,
    ScopeModal,
    SubmittedView,
    _draft_key,
    _evict,
    _is_expired,
    drafts,
)
from src.models.draft_change_order import DraftChangeOrder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_KEY = (123456789, 111, 222)  # must match mock_interaction fixture IDs


def _seed_draft(draft_key: tuple[int, int, int] = _TEST_KEY, *, expired: bool = False):
    """Insert a draft into the store. Pass expired=True to backdate created_at past the TTL."""
    age = timedelta(seconds=DRAFT_TTL_SECONDS + 60) if expired else timedelta(seconds=0)
    drafts[draft_key] = DraftChangeOrder(
        date="01/01/2025",
        submitted_at="<t:1234567890:F>",
        scope="Install panel",
        created_at=datetime.now(UTC) - age,
    )
    return drafts[draft_key]


def _clear_drafts():
    drafts.clear()


def _make_interaction(user_id=123456789, guild_id=111, channel_id=222):
    """Build a self-contained mock interaction with configurable IDs."""
    mock_message = MagicMock(spec=discord.Message)
    mock_message.edit = AsyncMock()

    user = MagicMock(spec=discord.Member)
    user.id = user_id
    user.mention = f"<@{user_id}>"

    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = user
    interaction.guild_id = guild_id
    interaction.channel_id = channel_id
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.original_response = AsyncMock(return_value=mock_message)
    return interaction, mock_message


# ---------------------------------------------------------------------------
# _is_expired
# ---------------------------------------------------------------------------


class TestIsExpired:
    def test_fresh_draft_not_expired(self):
        draft = _seed_draft()
        assert _is_expired(draft) is False

    def test_stale_draft_is_expired(self):
        draft = _seed_draft(expired=True)
        assert _is_expired(draft) is True


# ---------------------------------------------------------------------------
# _evict
# ---------------------------------------------------------------------------


class TestEvict:
    def setup_method(self):
        _clear_drafts()

    async def test_evict_removes_from_store(self):
        _seed_draft()
        await _evict(_TEST_KEY)
        assert _TEST_KEY not in drafts

    async def test_evict_edits_message(self, mock_message):
        draft = _seed_draft()
        draft.message = mock_message
        await _evict(_TEST_KEY)
        mock_message.edit.assert_called_once()
        assert "expired" in mock_message.edit.call_args.kwargs.get("content", "").lower()

    async def test_evict_without_message_does_not_raise(self):
        _seed_draft()  # message=None by default
        await _evict(_TEST_KEY)  # should not raise

    async def test_evict_handles_not_found(self, mock_message):
        draft = _seed_draft()
        draft.message = mock_message
        mock_message.edit = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        await _evict(_TEST_KEY)  # should not raise

    async def test_evict_handles_http_exception(self, mock_message):
        draft = _seed_draft()
        draft.message = mock_message
        mock_message.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))
        await _evict(_TEST_KEY)  # should not raise

    async def test_evict_nonexistent_key_does_not_raise(self):
        await _evict((0, 0, 0))  # not in store — should be a no-op


# ---------------------------------------------------------------------------
# ScopeModal
# ---------------------------------------------------------------------------


class TestScopeModal:
    def setup_method(self):
        _clear_drafts()

    def _make_modal(self, date="", scope="Install panel"):
        modal = ScopeModal()
        modal.date_requested = MagicMock()
        modal.date_requested.value = date
        modal.scope_added = MagicMock()
        modal.scope_added.value = scope
        return modal

    async def test_creates_draft_on_submit(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        assert _draft_key(mock_interaction) in drafts

    async def test_draft_is_correct_type(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        assert isinstance(drafts[_draft_key(mock_interaction)], DraftChangeOrder)

    async def test_draft_contains_correct_scope(self, mock_interaction):
        await self._make_modal(scope="Run new circuits").on_submit(mock_interaction)
        assert drafts[_draft_key(mock_interaction)].scope == "Run new circuits"

    async def test_draft_materials_starts_empty(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        assert drafts[_draft_key(mock_interaction)].materials == []

    async def test_draft_message_stored_on_draft(self, mock_interaction, mock_message):
        await self._make_modal().on_submit(mock_interaction)
        assert drafts[_draft_key(mock_interaction)].message is mock_message

    async def test_draft_created_at_is_recent(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        draft = drafts[_draft_key(mock_interaction)]
        age = (datetime.now(UTC) - draft.created_at).total_seconds()
        assert age < 5

    async def test_sends_message_with_embed_and_view(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        mock_interaction.response.send_message.assert_called_once()
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert isinstance(kwargs.get("embed"), discord.Embed)
        assert isinstance(kwargs.get("view"), DraftView)

    async def test_view_message_set_after_submit(self, mock_interaction, mock_message):
        await self._make_modal().on_submit(mock_interaction)
        sent_view = mock_interaction.response.send_message.call_args.kwargs["view"]
        assert sent_view.message is mock_message

    async def test_invalid_date_format_sends_ephemeral_error(self, mock_interaction):
        await self._make_modal(date="2026-03-15").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_invalid_date_does_not_create_draft(self, mock_interaction):
        await self._make_modal(date="2026-03-15").on_submit(mock_interaction)
        assert _draft_key(mock_interaction) not in drafts


# ---------------------------------------------------------------------------
# AddMaterialModal
# ---------------------------------------------------------------------------


class TestAddMaterialModal:
    def setup_method(self):
        _clear_drafts()

    def _make_modal(self, draft_key, message, materials_text="Breaker - 3"):
        modal = AddMaterialModal(draft_key=draft_key, message=message)
        modal.materials_input = MagicMock()
        modal.materials_input.value = materials_text
        return modal

    async def test_adds_material_to_draft(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        await self._make_modal(_TEST_KEY, mock_message).on_submit(mock_interaction)
        assert ("Breaker", "3") in drafts[_TEST_KEY].materials

    async def test_non_numeric_quantity_sends_ephemeral_error(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        await self._make_modal(_TEST_KEY, mock_message, materials_text="Breaker - lots").on_submit(
            mock_interaction
        )
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_non_numeric_quantity_does_not_add_to_draft(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        await self._make_modal(_TEST_KEY, mock_message, materials_text="Breaker - lots").on_submit(
            mock_interaction
        )
        assert drafts[_TEST_KEY].materials == []

    async def test_missing_separator_sends_ephemeral_error(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        await self._make_modal(_TEST_KEY, mock_message, materials_text="BadLine").on_submit(
            mock_interaction
        )
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_missing_draft_sends_ephemeral_error(self, mock_interaction, mock_message):
        await self._make_modal(_TEST_KEY, mock_message).on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_message_edited_after_add(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        await self._make_modal(_TEST_KEY, mock_message).on_submit(mock_interaction)
        mock_message.edit.assert_called_once()

    async def test_decimal_quantity_accepted(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        await self._make_modal(_TEST_KEY, mock_message, materials_text="Breaker - 2.5").on_submit(
            mock_interaction
        )
        assert ("Breaker", "2.5") in drafts[_TEST_KEY].materials

    async def test_expired_draft_sends_ephemeral_error(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY, expired=True)
        await self._make_modal(_TEST_KEY, mock_message).on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_expired_draft_evicted(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY, expired=True)
        await self._make_modal(_TEST_KEY, mock_message).on_submit(mock_interaction)
        assert _TEST_KEY not in drafts

    async def test_expired_draft_does_not_add_material(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY, expired=True)
        await self._make_modal(_TEST_KEY, mock_message).on_submit(mock_interaction)
        assert _TEST_KEY not in drafts

    # --- bulk / multi-line ---

    async def test_adds_multiple_materials_in_one_submit(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        raw = "20A Breaker - 3\n12 AWG Wire - 2\nJunction Box - 5"
        await self._make_modal(_TEST_KEY, mock_message, materials_text=raw).on_submit(
            mock_interaction
        )
        materials = drafts[_TEST_KEY].materials
        assert ("20A Breaker", "3") in materials
        assert ("12 AWG Wire", "2") in materials
        assert ("Junction Box", "5") in materials

    async def test_bulk_add_appends_to_existing_materials(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        drafts[_TEST_KEY].materials = [("Existing Item", "1")]
        raw = "New Item A - 4\nNew Item B - 7"
        await self._make_modal(_TEST_KEY, mock_message, materials_text=raw).on_submit(
            mock_interaction
        )
        assert len(drafts[_TEST_KEY].materials) == 3
        assert ("Existing Item", "1") in drafts[_TEST_KEY].materials

    async def test_mixed_valid_and_invalid_sends_ephemeral_error(
        self, mock_interaction, mock_message
    ):
        _seed_draft(_TEST_KEY)
        raw = "Good Item - 2\nBadLine\nAnother Good - 10"
        await self._make_modal(_TEST_KEY, mock_message, materials_text=raw).on_submit(
            mock_interaction
        )
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_mixed_valid_and_invalid_does_not_partially_add(
        self, mock_interaction, mock_message
    ):
        _seed_draft(_TEST_KEY)
        raw = "Good Item - 2\nBadLine"
        await self._make_modal(_TEST_KEY, mock_message, materials_text=raw).on_submit(
            mock_interaction
        )
        assert drafts[_TEST_KEY].materials == []

    async def test_dash_in_item_name_parsed_correctly(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        await self._make_modal(_TEST_KEY, mock_message, materials_text="12-2 Wire - 5").on_submit(
            mock_interaction
        )
        assert ("12-2 Wire", "5") in drafts[_TEST_KEY].materials


# ---------------------------------------------------------------------------
# DraftView — _check_expired
# ---------------------------------------------------------------------------


class TestDraftViewCheckExpired:
    def setup_method(self):
        _clear_drafts()

    async def test_fresh_draft_not_blocked(self, mock_interaction):
        _seed_draft(_TEST_KEY)
        view = DraftView(_TEST_KEY)
        result = await view._check_expired(mock_interaction)
        assert result is False
        mock_interaction.response.send_message.assert_not_called()

    async def test_expired_draft_returns_true(self, mock_interaction):
        _seed_draft(_TEST_KEY, expired=True)
        view = DraftView(_TEST_KEY)
        result = await view._check_expired(mock_interaction)
        assert result is True

    async def test_expired_draft_sends_ephemeral(self, mock_interaction):
        _seed_draft(_TEST_KEY, expired=True)
        view = DraftView(_TEST_KEY)
        await view._check_expired(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_expired_draft_evicted_by_check(self, mock_interaction):
        _seed_draft(_TEST_KEY, expired=True)
        view = DraftView(_TEST_KEY)
        await view._check_expired(mock_interaction)
        assert _TEST_KEY not in drafts


# ---------------------------------------------------------------------------
# DraftView — timeout=None
# ---------------------------------------------------------------------------


async def test_view_has_no_timeout():
    """View timeout must be None — TTL is managed by created_at, not discord.py."""
    view = DraftView(_TEST_KEY)
    assert view.timeout is None


# ---------------------------------------------------------------------------
# DraftView buttons
# ---------------------------------------------------------------------------


class TestDraftViewUndoLast:
    def setup_method(self):
        _clear_drafts()

    async def test_undo_removes_last_material(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        drafts[_TEST_KEY].materials = [("A", "1"), ("B", "2")]
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).undo_last.callback(mock_interaction)
        assert drafts[_TEST_KEY].materials == [("A", "1")]

    async def test_undo_empty_sends_ephemeral(self, mock_interaction):
        _seed_draft(_TEST_KEY)
        await DraftView(_TEST_KEY).undo_last.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_undo_expired_draft_sends_ephemeral(self, mock_interaction):
        _seed_draft(_TEST_KEY, expired=True)
        await DraftView(_TEST_KEY).undo_last.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


class TestDraftViewDone:
    def setup_method(self):
        _clear_drafts()

    async def test_done_removes_draft(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        drafts[_TEST_KEY].materials = [("Breaker", "2")]
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert _TEST_KEY not in drafts

    async def test_done_edits_message_with_final_embed(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        drafts[_TEST_KEY].materials = [("Breaker", "2")]
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        mock_message.edit.assert_called_once()
        edited_embed = mock_message.edit.call_args.kwargs.get("embed")
        assert isinstance(edited_embed, discord.Embed)
        assert "Submitted" in edited_embed.title

    async def test_done_swaps_to_submitted_view(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        drafts[_TEST_KEY].materials = [("Breaker", "2")]
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        submitted_view = mock_message.edit.call_args.kwargs.get("view")
        assert isinstance(submitted_view, SubmittedView)

    async def test_done_with_no_materials_sends_ephemeral_error(
        self, mock_interaction, mock_message
    ):
        _seed_draft(_TEST_KEY)
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_done_with_no_materials_does_not_remove_draft(
        self, mock_interaction, mock_message
    ):
        _seed_draft(_TEST_KEY)
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert _TEST_KEY in drafts

    async def test_done_with_no_materials_does_not_edit_message(
        self, mock_interaction, mock_message
    ):
        _seed_draft(_TEST_KEY)
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        mock_message.edit.assert_not_called()

    async def test_done_expired_draft_sends_ephemeral(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY, expired=True)
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


class TestDraftViewCancel:
    def setup_method(self):
        _clear_drafts()

    async def test_cancel_removes_draft(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).cancel.callback(mock_interaction)
        assert _TEST_KEY not in drafts

    async def test_cancel_disables_all_buttons(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY)
        mock_interaction.message = mock_message
        view = DraftView(_TEST_KEY)
        await view.cancel.callback(mock_interaction)
        assert all(child.disabled for child in view.children)

    async def test_cancel_expired_draft_sends_ephemeral(self, mock_interaction, mock_message):
        _seed_draft(_TEST_KEY, expired=True)
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).cancel.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# DraftView interaction_check
# ---------------------------------------------------------------------------


class TestDraftViewInteractionCheck:
    async def test_wrong_user_blocked(self, mock_interaction):
        wrong_key = (999, 111, 222)
        result = await DraftView(wrong_key).interaction_check(mock_interaction)
        assert result is False
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_correct_user_allowed(self, mock_interaction):
        result = await DraftView(_TEST_KEY).interaction_check(mock_interaction)
        assert result is True


# ---------------------------------------------------------------------------
# Background sweep
# ---------------------------------------------------------------------------


class TestSweepExpiredDrafts:
    def setup_method(self):
        _clear_drafts()

    async def test_sweep_removes_expired_drafts(self):
        _seed_draft(_TEST_KEY, expired=True)
        cog = ChangeOrder(MagicMock())
        cog.sweep_expired_drafts.cancel()  # don't let the loop actually run
        await cog.sweep_expired_drafts()
        assert _TEST_KEY not in drafts

    async def test_sweep_preserves_fresh_drafts(self):
        fresh_key = (111, 111, 111)
        _seed_draft(fresh_key, expired=False)
        cog = ChangeOrder(MagicMock())
        cog.sweep_expired_drafts.cancel()
        await cog.sweep_expired_drafts()
        assert fresh_key in drafts

    async def test_sweep_edits_expired_message(self, mock_message):
        draft = _seed_draft(_TEST_KEY, expired=True)
        draft.message = mock_message
        cog = ChangeOrder(MagicMock())
        cog.sweep_expired_drafts.cancel()
        await cog.sweep_expired_drafts()
        mock_message.edit.assert_called_once()

    async def test_sweep_mixed_drafts(self):
        expired_key = (1, 1, 1)
        fresh_key = (2, 2, 2)
        _seed_draft(expired_key, expired=True)
        _seed_draft(fresh_key, expired=False)
        cog = ChangeOrder(MagicMock())
        cog.sweep_expired_drafts.cancel()
        await cog.sweep_expired_drafts()
        assert expired_key not in drafts
        assert fresh_key in drafts


# ---------------------------------------------------------------------------
# Multi-channel isolation
# ---------------------------------------------------------------------------


class TestMultiChannelDraftIsolation:
    def setup_method(self):
        _clear_drafts()

    async def test_same_user_different_channels_independent(self):
        key_ch1 = (123456789, 111, 222)
        key_ch2 = (123456789, 111, 333)
        _seed_draft(key_ch1)
        _seed_draft(key_ch2)
        drafts[key_ch1].materials = [("A", "1")]
        drafts[key_ch2].materials = [("B", "2")]
        assert drafts[key_ch1].materials != drafts[key_ch2].materials

    async def test_same_user_same_channel_blocks(self):
        interaction, _ = _make_interaction()
        _seed_draft(_TEST_KEY)
        cog = ChangeOrder(MagicMock())
        cog.sweep_expired_drafts.cancel()
        await cog.change_order.callback(cog, interaction)
        interaction.response.send_modal.assert_not_called()
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_same_user_different_channel_allowed(self):
        _seed_draft(_TEST_KEY)
        interaction, _ = _make_interaction(channel_id=333)
        cog = ChangeOrder(MagicMock())
        cog.sweep_expired_drafts.cancel()
        await cog.change_order.callback(cog, interaction)
        interaction.response.send_modal.assert_called_once()


# ---------------------------------------------------------------------------
# ChangeOrder cog
# ---------------------------------------------------------------------------


class TestChangeOrderCog:
    def setup_method(self):
        _clear_drafts()

    async def test_opens_modal_when_no_existing_draft(self, mock_interaction):
        cog = ChangeOrder(MagicMock())
        cog.sweep_expired_drafts.cancel()
        await cog.change_order.callback(cog, mock_interaction)
        mock_interaction.response.send_modal.assert_called_once()

    async def test_blocks_second_draft_same_channel(self, mock_interaction):
        _seed_draft(_draft_key(mock_interaction))
        cog = ChangeOrder(MagicMock())
        cog.sweep_expired_drafts.cancel()
        await cog.change_order.callback(cog, mock_interaction)
        mock_interaction.response.send_modal.assert_not_called()
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_expired_draft_allows_new_command(self, mock_interaction):
        """An expired draft at command entry should be lazily evicted, allowing a fresh one."""
        _seed_draft(_draft_key(mock_interaction), expired=True)
        cog = ChangeOrder(MagicMock())
        cog.sweep_expired_drafts.cancel()
        await cog.change_order.callback(cog, mock_interaction)
        mock_interaction.response.send_modal.assert_called_once()


# ---------------------------------------------------------------------------
# SubmittedView
# ---------------------------------------------------------------------------


class TestSubmittedView:
    def setup_method(self):
        _clear_drafts()

    async def test_copy_text_sends_ephemeral(self, mock_interaction):
        view = SubmittedView("some plain text")
        await view.copy_text.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_copy_text_contains_plain_text(self, mock_interaction):
        view = SubmittedView("some plain text")
        await view.copy_text.callback(mock_interaction)
        sent = mock_interaction.response.send_message.call_args.args[0]
        assert "some plain text" in sent

    async def test_copy_text_wrapped_in_code_block(self, mock_interaction):
        view = SubmittedView("some plain text")
        await view.copy_text.callback(mock_interaction)
        sent = mock_interaction.response.send_message.call_args.args[0]
        assert sent.startswith("```") and sent.endswith("```")

    async def test_copy_text_open_to_any_user(self, mock_interaction):
        """No interaction_check — any user in the channel can copy the text."""
        other_user = MagicMock(spec=discord.Member)
        other_user.id = 999
        mock_interaction.user = other_user
        view = SubmittedView("some plain text")
        await view.copy_text.callback(mock_interaction)
        mock_interaction.response.send_message.assert_called_once()

    async def test_view_has_no_timeout(self):
        view = SubmittedView("text")
        assert view.timeout is None


# ---------------------------------------------------------------------------
# format_plain_text
# ---------------------------------------------------------------------------


class TestFormatPlainText:
    def _make_user(self, name="Jack"):
        user = MagicMock(spec=discord.Member)
        user.display_name = name
        return user

    def test_contains_date(self):
        from src.helpers.helpers import format_plain_text

        result = format_plain_text(self._make_user(), "01/01/2025", "Install panel", [])
        assert "01/01/2025" in result

    def test_contains_scope(self):
        from src.helpers.helpers import format_plain_text

        result = format_plain_text(self._make_user(), "01/01/2025", "Install panel", [])
        assert "Install panel" in result

    def test_contains_user_name(self):
        from src.helpers.helpers import format_plain_text

        result = format_plain_text(self._make_user("Jack"), "01/01/2025", "Scope", [])
        assert "Jack" in result

    def test_materials_formatted_correctly(self):
        from src.helpers.helpers import format_plain_text

        result = format_plain_text(
            self._make_user(), "01/01/2025", "Scope", [("Breaker", "3"), ("Wire", "2")]
        )
        assert "Breaker - 3" in result
        assert "Wire - 2" in result

    def test_empty_materials_fallback(self):
        from src.helpers.helpers import format_plain_text

        result = format_plain_text(self._make_user(), "01/01/2025", "Scope", [])
        assert "No materials listed" in result
