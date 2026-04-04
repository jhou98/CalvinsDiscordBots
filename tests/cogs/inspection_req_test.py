"""
Tests for cogs/inspection_req.py — the /inspectionreq command.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import discord

from src.cogs.inspection_req import (
    COMMAND,
    INSPECTION_TYPES,
    InspectionModal,
    InspectionModalOther,
    InspectionReq,
    InspectionTypeSelectView,
    drafts,
)
from src.models.draft_inspection import DraftInspection
from src.views.draft_view_base import DRAFT_TTL_SECONDS, draft_key

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_KEY = ("123456789", "222", COMMAND)


def _seed_draft(key=_TEST_KEY, *, expired: bool = False):
    age = timedelta(seconds=DRAFT_TTL_SECONDS + 60) if expired else timedelta(seconds=0)
    drafts[key] = DraftInspection(
        date_requested="01/01/2025",
        inspection_date="02/01/2025",
        inspection_type="Rough-in",
        site_contact="Bob — 555-1234",
        am_pm="AM",
        submitted_at="<t:1234567890:F>",
        created_at=datetime.now(UTC) - age,
    )
    return drafts[key]


def _clear_drafts():
    drafts.clear()


# ---------------------------------------------------------------------------
# InspectionModal (named type)
# ---------------------------------------------------------------------------


class TestInspectionModal:
    def setup_method(self):
        _clear_drafts()

    def _make_modal(
        self,
        inspection_type="Rough-in",
        date="",
        insp_date="04/01/2026",
        site="Bob — 555",
        am_pm="AM",
    ):
        modal = InspectionModal(inspection_type=inspection_type)
        modal.date_requested = MagicMock(value=date)
        modal.inspection_date = MagicMock(value=insp_date)
        modal.site_contact = MagicMock(value=site)
        modal.am_pm = MagicMock(value=am_pm)
        return modal

    async def test_creates_draft(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        assert draft_key(mock_interaction, COMMAND) in drafts

    async def test_draft_stores_inspection_type(self, mock_interaction):
        await self._make_modal(inspection_type="Final").on_submit(mock_interaction)
        assert drafts[draft_key(mock_interaction, COMMAND)].inspection_type == "Final"

    async def test_draft_stores_am_pm_uppercased(self, mock_interaction):
        await self._make_modal(am_pm="am").on_submit(mock_interaction)
        assert drafts[draft_key(mock_interaction, COMMAND)].am_pm == "AM"

    async def test_sends_embed_and_view(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert isinstance(kwargs.get("embed"), discord.Embed)
        assert kwargs.get("view") is not None

    async def test_message_stored_on_draft(self, mock_interaction, mock_message):
        await self._make_modal().on_submit(mock_interaction)
        assert drafts[draft_key(mock_interaction, COMMAND)].message is mock_message

    async def test_invalid_date_requested_sends_ephemeral(self, mock_interaction):
        await self._make_modal(date="bad-date").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_invalid_date_requested_does_not_create_draft(self, mock_interaction):
        await self._make_modal(date="bad-date").on_submit(mock_interaction)
        assert draft_key(mock_interaction, COMMAND) not in drafts

    async def test_invalid_inspection_date_sends_ephemeral(self, mock_interaction):
        await self._make_modal(insp_date="not-a-date").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_blank_date_requested_defaults_to_today(self, mock_interaction):
        await self._make_modal(date="").on_submit(mock_interaction)
        draft = drafts[draft_key(mock_interaction, COMMAND)]
        import re

        assert re.match(r"\d{2}/\d{2}/\d{4}", draft.date_requested)


# ---------------------------------------------------------------------------
# InspectionModalOther (free-text type)
# ---------------------------------------------------------------------------


class TestInspectionModalOther:
    def setup_method(self):
        _clear_drafts()

    def _make_modal(self, type_text="Special inspection"):
        modal = InspectionModalOther(inspection_type="Other")
        modal.date_requested = MagicMock(value="")
        modal.inspection_date = MagicMock(value="04/01/2026")
        modal.site_contact = MagicMock(value="Bob — 555")
        modal.am_pm = MagicMock(value="PM")
        modal.inspection_type_other = MagicMock(value=type_text)
        return modal

    async def test_uses_free_text_as_type(self, mock_interaction):
        await self._make_modal("Special inspection").on_submit(mock_interaction)
        assert drafts[draft_key(mock_interaction, COMMAND)].inspection_type == "Special inspection"

    async def test_creates_draft(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        assert draft_key(mock_interaction, COMMAND) in drafts


# ---------------------------------------------------------------------------
# InspectionTypeSelectView
# ---------------------------------------------------------------------------


class TestInspectionTypeSelectView:
    async def test_named_type_returns_inspection_modal(self):
        view = InspectionTypeSelectView()
        modal = await view.modal_factory("Rough-in")
        assert isinstance(modal, InspectionModal)

    async def test_other_returns_inspection_modal_other(self):
        view = InspectionTypeSelectView()
        modal = await view.modal_factory("Other")
        assert isinstance(modal, InspectionModalOther)

    async def test_all_inspection_types_present_in_select(self):
        view = InspectionTypeSelectView()
        select = next(c for c in view.children if isinstance(c, discord.ui.Select))
        option_values = [o.value for o in select.options]
        for t in INSPECTION_TYPES:
            assert t in option_values
        assert "Other" in option_values


# ---------------------------------------------------------------------------
# InspectionReq cog
# ---------------------------------------------------------------------------


class TestInspectionReqCog:
    def setup_method(self):
        _clear_drafts()

    async def test_opens_select_when_no_draft(self, mock_interaction):
        cog = InspectionReq(MagicMock())
        cog._stop_sweep()
        await cog.inspection_req.callback(cog, mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert isinstance(kwargs.get("view"), InspectionTypeSelectView)
        assert kwargs.get("ephemeral") is True

    async def test_blocks_second_draft(self, mock_interaction):
        _seed_draft(draft_key(mock_interaction, COMMAND))
        cog = InspectionReq(MagicMock())
        cog._stop_sweep()
        await cog.inspection_req.callback(cog, mock_interaction)
        # Should send an error, not the select view
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        assert not isinstance(kwargs.get("view"), InspectionTypeSelectView)

    async def test_expired_draft_allows_new_command(self, mock_interaction):
        _seed_draft(draft_key(mock_interaction, COMMAND), expired=True)
        cog = InspectionReq(MagicMock())
        cog._stop_sweep()
        await cog.inspection_req.callback(cog, mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert isinstance(kwargs.get("view"), InspectionTypeSelectView)


# ---------------------------------------------------------------------------
# INSPECTION_TYPES is easy to extend
# ---------------------------------------------------------------------------


def test_inspection_types_is_a_list():
    assert isinstance(INSPECTION_TYPES, list)
    assert len(INSPECTION_TYPES) > 0


def test_other_not_in_inspection_types_constant():
    """'Other' should be appended by make_select_then_modal, not hardcoded."""
    assert "Other" not in INSPECTION_TYPES
