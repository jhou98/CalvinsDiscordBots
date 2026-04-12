"""
Tests for cogs/mat_order.py — the /matorder command.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import discord

from src.cogs.mat_order import (
    COMMAND,
    DraftView,
    MatOrder,
    MatOrderStep1Modal,
    MatOrderStep2ContinueView,
    MatOrderStep2Modal,
    drafts,
)
from src.models.draft_mat_order import DraftMatOrder
from src.views.draft_view_base import DRAFT_TTL_SECONDS, SubmittedView, draft_key
from tests.conftest import make_interaction

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_KEY = ("123456789", "222", COMMAND)


def _seed_draft(key=_TEST_KEY, *, expired: bool = False):
    age = timedelta(seconds=DRAFT_TTL_SECONDS + 60) if expired else timedelta(seconds=0)
    drafts[key] = DraftMatOrder(
        date_requested="01/01/2025",
        requested_by="Jack",
        required_date="02/01/2025",
        site_contact_name="Bob",
        site_contact_phone="555-1234",
        delivery_notes="",
        submitted_at="<t:1234567890:F>",
        created_at=datetime.now(UTC) - age,
    )
    return drafts[key]


def _clear_drafts():
    drafts.clear()


# ---------------------------------------------------------------------------
# MatOrderStep1Modal
# ---------------------------------------------------------------------------


class TestMatOrderStep1Modal:
    def setup_method(self):
        _clear_drafts()

    def _make_modal(
        self,
        date="",
        requested_by="Jack",
        required_date="05/01/2026",
        contact_name="Bob",
        contact_phone="555-867-5309",
    ):
        modal = MatOrderStep1Modal()
        modal.date_requested = MagicMock(value=date)
        modal.requested_by = MagicMock(value=requested_by)
        modal.required_date = MagicMock(value=required_date)
        modal.site_contact_name = MagicMock(value=contact_name)
        modal.site_contact_phone = MagicMock(value=contact_phone)
        return modal

    async def test_creates_partial_draft(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        assert draft_key(mock_interaction, COMMAND) in drafts

    async def test_draft_type(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        assert isinstance(drafts[draft_key(mock_interaction, COMMAND)], DraftMatOrder)

    async def test_stores_requested_by(self, mock_interaction):
        await self._make_modal(requested_by="Alice").on_submit(mock_interaction)
        assert drafts[draft_key(mock_interaction, COMMAND)].requested_by == "Alice"

    async def test_stores_contact_name(self, mock_interaction):
        await self._make_modal(contact_name="Jane").on_submit(mock_interaction)
        assert drafts[draft_key(mock_interaction, COMMAND)].site_contact_name == "Jane"

    async def test_stores_contact_phone(self, mock_interaction):
        await self._make_modal(contact_phone="555-123-4567").on_submit(mock_interaction)
        assert drafts[draft_key(mock_interaction, COMMAND)].site_contact_phone == "555-123-4567"

    async def test_posts_continue_button(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        assert isinstance(kwargs.get("view"), MatOrderStep2ContinueView)

    async def test_does_not_call_send_modal(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        mock_interaction.response.send_modal.assert_not_called()

    async def test_invalid_date_requested_sends_ephemeral(self, mock_interaction):
        await self._make_modal(date="bad").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_invalid_required_date_sends_ephemeral(self, mock_interaction):
        await self._make_modal(required_date="bad").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_invalid_date_does_not_create_draft(self, mock_interaction):
        await self._make_modal(date="bad").on_submit(mock_interaction)
        assert draft_key(mock_interaction, COMMAND) not in drafts

    async def test_invalid_phone_sends_ephemeral(self, mock_interaction):
        await self._make_modal(contact_phone="123").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_invalid_phone_does_not_create_draft(self, mock_interaction):
        await self._make_modal(contact_phone="123").on_submit(mock_interaction)
        assert draft_key(mock_interaction, COMMAND) not in drafts


# ---------------------------------------------------------------------------
# MatOrderStep2ContinueView
# ---------------------------------------------------------------------------


class TestMatOrderStep2ContinueView:
    def setup_method(self):
        _clear_drafts()

    async def test_continue_opens_step2_modal(self):
        _seed_draft()
        interaction, _ = make_interaction()
        view = MatOrderStep2ContinueView(_TEST_KEY)
        await view.continue_to_step2.callback(interaction)
        interaction.response.send_modal.assert_called_once()
        assert isinstance(
            interaction.response.send_modal.call_args.args[0], MatOrderStep2Modal
        )

    async def test_continue_missing_draft_sends_ephemeral(self):
        interaction, _ = make_interaction()
        view = MatOrderStep2ContinueView(_TEST_KEY)
        await view.continue_to_step2.callback(interaction)
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# MatOrderStep2Modal
# ---------------------------------------------------------------------------


class TestMatOrderStep2Modal:
    def setup_method(self):
        _clear_drafts()

    def _make_modal(self, key=_TEST_KEY, delivery_notes="", materials_text=""):
        modal = MatOrderStep2Modal(key=key)
        modal.delivery_notes = MagicMock(value=delivery_notes)
        modal.materials_input = MagicMock(value=materials_text)
        return modal

    async def test_stores_delivery_notes(self):
        _seed_draft()
        interaction, _ = make_interaction()
        await self._make_modal(delivery_notes="Call before delivery").on_submit(interaction)
        assert drafts[_TEST_KEY].delivery_notes == "Call before delivery"

    async def test_materials_starts_empty_when_not_provided(self):
        _seed_draft()
        interaction, _ = make_interaction()
        await self._make_modal().on_submit(interaction)
        assert drafts[_TEST_KEY].materials == []

    async def test_seeded_with_initial_materials(self):
        _seed_draft()
        interaction, _ = make_interaction()
        await self._make_modal(materials_text="Breaker - 3\nWire - 2").on_submit(interaction)
        materials = drafts[_TEST_KEY].materials
        assert ("Breaker", "3") in materials
        assert ("Wire", "2") in materials

    async def test_sends_embed_and_view(self):
        _seed_draft()
        interaction, _ = make_interaction()
        await self._make_modal().on_submit(interaction)
        kwargs = interaction.response.send_message.call_args.kwargs
        assert isinstance(kwargs.get("embed"), discord.Embed)
        assert kwargs.get("view") is not None

    async def test_message_stored(self):
        _seed_draft()
        interaction, msg = make_interaction()
        await self._make_modal().on_submit(interaction)
        assert drafts[_TEST_KEY].message is msg

    async def test_invalid_material_format_sends_ephemeral(self):
        _seed_draft()
        interaction, _ = make_interaction()
        await self._make_modal(materials_text="BadLine").on_submit(interaction)
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_invalid_material_removes_partial_draft(self):
        _seed_draft()
        interaction, _ = make_interaction()
        await self._make_modal(materials_text="BadLine").on_submit(interaction)
        assert _TEST_KEY not in drafts

    async def test_missing_draft_sends_ephemeral(self):
        interaction, _ = make_interaction()
        await self._make_modal().on_submit(interaction)
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# DraftView — material buttons
# ---------------------------------------------------------------------------


class TestMatOrderDraftViewUndoLast:
    def setup_method(self):
        _clear_drafts()

    async def test_undo_removes_last(self, mock_interaction, mock_message):
        _seed_draft()
        drafts[_TEST_KEY].materials = [("A", "1"), ("B", "2")]
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).undo_last.callback(mock_interaction)
        assert drafts[_TEST_KEY].materials == [("A", "1")]

    async def test_undo_empty_sends_ephemeral(self, mock_interaction):
        _seed_draft()
        await DraftView(_TEST_KEY).undo_last.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


class TestMatOrderDraftViewDone:
    def setup_method(self):
        _clear_drafts()

    async def test_done_requires_materials(self, mock_interaction, mock_message):
        _seed_draft()
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_done_removes_draft(self, mock_interaction, mock_message):
        _seed_draft()
        drafts[_TEST_KEY].materials = [("Conduit", "10")]
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert _TEST_KEY not in drafts

    async def test_done_swaps_to_submitted_view(self, mock_interaction, mock_message):
        _seed_draft()
        drafts[_TEST_KEY].materials = [("Conduit", "10")]
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert isinstance(mock_message.edit.call_args.kwargs.get("view"), SubmittedView)


# ---------------------------------------------------------------------------
# MatOrder cog
# ---------------------------------------------------------------------------


class TestMatOrderCog:
    def setup_method(self):
        _clear_drafts()

    async def test_opens_modal_when_no_draft(self, mock_interaction):
        cog = MatOrder(MagicMock())
        cog._stop_sweep()
        await cog.mat_order.callback(cog, mock_interaction)
        mock_interaction.response.send_modal.assert_called_once()
        assert isinstance(
            mock_interaction.response.send_modal.call_args.args[0], MatOrderStep1Modal
        )

    async def test_blocks_second_draft(self, mock_interaction):
        _seed_draft(draft_key(mock_interaction, COMMAND))
        cog = MatOrder(MagicMock())
        cog._stop_sweep()
        await cog.mat_order.callback(cog, mock_interaction)
        mock_interaction.response.send_modal.assert_not_called()
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_different_command_same_channel_allowed(self, mock_interaction):
        """A matorder and changeorder draft can coexist in the same channel."""
        co_key = (str(mock_interaction.user.id), str(mock_interaction.channel_id), "changeorder")
        import src.cogs.change_order as co_mod
        from src.models.draft_change_order import DraftChangeOrder

        co_mod.drafts[co_key] = DraftChangeOrder(
            date_requested="01/01/2025", submitted_at="x", scope="s"
        )
        cog = MatOrder(MagicMock())
        cog._stop_sweep()
        await cog.mat_order.callback(cog, mock_interaction)
        mock_interaction.response.send_modal.assert_called_once()
        del co_mod.drafts[co_key]
