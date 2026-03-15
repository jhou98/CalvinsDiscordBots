"""
Tests for cogs/change_order_multistep.py — the multi-step /changeorderpro command.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import src.cogs.change_order_multistep as co_ms
from src.cogs.change_order_multistep import (
    ScopeModal,
    AddMaterialModal,
    DraftView,
    ChangeOrderMultiStep,
    drafts
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_draft(user_id: int):
    """Insert a fresh draft directly into the in-memory store."""
    drafts[user_id] = {
        "date": "01/01/2025",
        "submitted_at": "<t:1234567890:F>",
        "scope": "Install panel",
        "materials": [],
    }

def _clear_drafts():
    drafts.clear()

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
        modal = self._make_modal()
        await modal.on_submit(mock_interaction)
        assert mock_interaction.user.id in drafts

    async def test_draft_contains_correct_scope(self, mock_interaction):
        modal = self._make_modal(scope="Run new circuits")
        await modal.on_submit(mock_interaction)
        assert drafts[mock_interaction.user.id]["scope"] == "Run new circuits"

    async def test_sends_message_with_embed_and_view(self, mock_interaction):
        modal = self._make_modal()
        await modal.on_submit(mock_interaction)
        mock_interaction.response.send_message.assert_called_once()
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert isinstance(kwargs.get("embed"), discord.Embed)
        assert isinstance(kwargs.get("view"), DraftView)

# ---------------------------------------------------------------------------
# AddMaterialModal
# ---------------------------------------------------------------------------
class TestAddMaterialModal:
    def setup_method(self):
        _clear_drafts()

    def _make_modal(self, user_id, message, name="Breaker", qty="3"):
        modal = AddMaterialModal(user_id=user_id, message=message)
        modal.item_name = MagicMock()
        modal.item_name.value = name
        modal.quantity = MagicMock()
        modal.quantity.value = qty
        return modal

    async def test_adds_material_to_draft(self, mock_interaction, mock_message):
        _seed_draft(mock_interaction.user.id)
        modal = self._make_modal(mock_interaction.user.id, mock_message)
        await modal.on_submit(mock_interaction)
        assert ("Breaker", "3") in drafts[mock_interaction.user.id]["materials"]

    async def test_non_numeric_quantity_sends_ephemeral_error(self, mock_interaction, mock_message):
        _seed_draft(mock_interaction.user.id)
        modal = self._make_modal(mock_interaction.user.id, mock_message, qty="lots")
        await modal.on_submit(mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    async def test_missing_draft_sends_ephemeral_error(self, mock_interaction, mock_message):
        # No draft seeded — user ID unknown
        modal = self._make_modal(mock_interaction.user.id, mock_message)
        await modal.on_submit(mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    async def test_message_edited_after_add(self, mock_interaction, mock_message):
        _seed_draft(mock_interaction.user.id)
        modal = self._make_modal(mock_interaction.user.id, mock_message)
        await modal.on_submit(mock_interaction)
        mock_message.edit.assert_called_once()

    async def test_decimal_quantity_accepted(self, mock_interaction, mock_message):
        _seed_draft(mock_interaction.user.id)
        modal = self._make_modal(mock_interaction.user.id, mock_message, qty="2.5")
        await modal.on_submit(mock_interaction)
        assert ("Breaker", "2.5") in drafts[mock_interaction.user.id]["materials"]

# ---------------------------------------------------------------------------
# DraftView buttons
# ---------------------------------------------------------------------------
class TestDraftViewUndoLast:
    def setup_method(self):
        _clear_drafts()

    async def test_undo_removes_last_material(self, mock_interaction, mock_message):
        _seed_draft(mock_interaction.user.id)
        drafts[mock_interaction.user.id]["materials"] = [("A", "1"), ("B", "2")]
        mock_interaction.message = mock_message

        view = DraftView(mock_interaction.user.id)
        await view.undo_last.callback(mock_interaction)

        assert drafts[mock_interaction.user.id]["materials"] == [("A", "1")]

    async def test_undo_empty_sends_ephemeral(self, mock_interaction):
        _seed_draft(mock_interaction.user.id)
        view = DraftView(mock_interaction.user.id)
        await view.undo_last.callback(mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

class TestDraftViewDone:
    def setup_method(self):
        _clear_drafts()

    async def test_done_removes_draft(self, mock_interaction, mock_message):
        _seed_draft(mock_interaction.user.id)
        mock_interaction.message = mock_message

        view = DraftView(mock_interaction.user.id)
        await view.done.callback(mock_interaction)

        assert mock_interaction.user.id not in drafts

    async def test_done_disables_all_buttons(self, mock_interaction, mock_message):
        _seed_draft(mock_interaction.user.id)
        mock_interaction.message = mock_message

        view = DraftView(mock_interaction.user.id)
        await view.done.callback(mock_interaction)

        assert all(child.disabled for child in view.children)

    async def test_done_edits_message_with_final_embed(self, mock_interaction, mock_message):
        _seed_draft(mock_interaction.user.id)
        mock_interaction.message = mock_message

        view = DraftView(mock_interaction.user.id)
        await view.done.callback(mock_interaction)

        mock_message.edit.assert_called_once()
        edited_embed = mock_message.edit.call_args.kwargs.get("embed")
        assert isinstance(edited_embed, discord.Embed)
        assert "Submitted" in edited_embed.title

class TestDraftViewCancel:
    def setup_method(self):
        _clear_drafts()

    async def test_cancel_removes_draft(self, mock_interaction, mock_message):
        _seed_draft(mock_interaction.user.id)
        mock_interaction.message = mock_message

        view = DraftView(mock_interaction.user.id)
        await view.cancel.callback(mock_interaction)
        assert mock_interaction.user.id not in drafts

    async def test_cancel_disables_all_buttons(self, mock_interaction, mock_message):
        _seed_draft(mock_interaction.user.id)
        mock_interaction.message = mock_message

        view = DraftView(mock_interaction.user.id)
        await view.cancel.callback(mock_interaction)

        assert all(child.disabled for child in view.children)

# ---------------------------------------------------------------------------
# DraftView interaction_check
# ---------------------------------------------------------------------------
class TestDraftViewInteractionCheck:
    async def test_wrong_user_blocked(self, mock_interaction):
        view = DraftView(user_id=999)  # Different from mock_interaction.user.id (123456789)
        result = await view.interaction_check(mock_interaction)
        assert result is False
        mock_interaction.response.send_message.assert_called_once()
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    async def test_correct_user_allowed(self, mock_interaction):
        view = DraftView(user_id=mock_interaction.user.id)
        result = await view.interaction_check(mock_interaction)
        assert result is True

# ---------------------------------------------------------------------------
# ChangeOrderMultiStep cog
# ---------------------------------------------------------------------------
class TestChangeOrderMultiStepCog:
    def setup_method(self):
        _clear_drafts()

    async def test_opens_modal_when_no_existing_draft(self, mock_interaction):
        bot = MagicMock()
        cog = ChangeOrderMultiStep(bot)
        await cog.change_order_pro.callback(cog, mock_interaction)
        mock_interaction.response.send_modal.assert_called_once()

    async def test_blocks_second_draft(self, mock_interaction):
        _seed_draft(mock_interaction.user.id)
        bot = MagicMock()
        cog = ChangeOrderMultiStep(bot)
        await cog.change_order_pro.callback(cog, mock_interaction)
        # Should NOT open a modal — should send an ephemeral warning instead
        mock_interaction.response.send_modal.assert_not_called()
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True