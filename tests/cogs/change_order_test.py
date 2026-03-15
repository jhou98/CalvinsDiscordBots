"""
Tests for cogs/change_order.py — the single-modal /changeorder command.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from src.cogs.change_order import MaterialsModal, ChangeOrder

# ---------------------------------------------------------------------------
# MaterialsModal.on_submit
# ---------------------------------------------------------------------------

class TestMaterialsModalOnSubmit:
    def _make_modal(self, date="", scope="Install panel", materials_text="Breaker - 3"):
        modal = MaterialsModal()
        modal.date_requested = MagicMock()
        modal.date_requested.value = date
        modal.scope_added = MagicMock()
        modal.scope_added.value = scope
        modal.materials = MagicMock()
        modal.materials.value = materials_text
        return modal

    async def test_valid_submission_sends_embed(self, mock_interaction):
        modal = self._make_modal()
        await modal.on_submit(mock_interaction)

        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert isinstance(call_kwargs.get("embed"), discord.Embed)

    async def test_invalid_materials_sends_ephemeral_error(self, mock_interaction):
        modal = self._make_modal(materials_text="BadLine")
        await modal.on_submit(mock_interaction)

        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True

    async def test_blank_date_defaults_to_today(self, mock_interaction):
        modal = self._make_modal(date="")
        await modal.on_submit(mock_interaction)

        # Should reach send_message without error (date auto-filled)
        mock_interaction.response.send_message.assert_called_once()

    async def test_provided_date_preserved(self, mock_interaction):
        modal = self._make_modal(date="06/15/2025")
        await modal.on_submit(mock_interaction)

        embed = mock_interaction.response.send_message.call_args.kwargs["embed"]
        date_field = next(f for f in embed.fields if "Date" in f.name)
        assert date_field.value == "06/15/2025"

# ---------------------------------------------------------------------------
# ChangeOrder cog
# ---------------------------------------------------------------------------

class TestChangeOrderCog:
    async def test_change_order_command_opens_modal(self, mock_interaction):
        bot = MagicMock()
        cog = ChangeOrder(bot)
        await cog.change_order.callback(cog, mock_interaction)
        mock_interaction.response.send_modal.assert_called_once()
        modal_arg = mock_interaction.response.send_modal.call_args.args[0]
        assert isinstance(modal_arg, MaterialsModal)