"""
Tests for cogs/rfi.py — the /rfi command.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import discord

from src.cogs.rfi import (
    COMMAND,
    RFI_IMPACT_OPTIONS,
    DraftView,
    EditRfiModal,
    Rfi,
    RfiImpactSelectView,
    RfiStep1Modal,
    RfiStep1ModalOther,
    RfiStep2ContinueView,
    RfiStep2Modal,
    _draft_embed,
    drafts,
)
from src.models.draft_rfi import DraftRfi
from src.views.draft_view_base import DRAFT_TTL_SECONDS, SubmittedView, draft_key
from tests.conftest import make_interaction

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_KEY = ("123456789", "222", COMMAND)


def _seed_draft(key=_TEST_KEY, *, expired: bool = False):
    age = timedelta(seconds=DRAFT_TTL_SECONDS + 60) if expired else timedelta(seconds=0)
    drafts[key] = DraftRfi(
        date_requested="01/01/2025",
        requested_by="Jack",
        questions="What gauge wire?",
        issues="Plans unclear",
        proposed_solution="Use 12 AWG",
        impact="Work stops",
        required_by="02/01/2025",
        submitted_at="<t:1234567890:F>",
        created_at=datetime.now(UTC) - age,
    )
    return drafts[key]


def _clear_drafts():
    drafts.clear()


# ---------------------------------------------------------------------------
# RfiStep1Modal (named impact)
# ---------------------------------------------------------------------------


class TestRfiStep1Modal:
    def setup_method(self):
        _clear_drafts()

    def _make_modal(
        self, impact="Work stops", date="", requested_by="Jack", required_by="05/01/2026"
    ):
        modal = RfiStep1Modal(impact=impact)
        modal.date_requested = MagicMock(value=date)
        modal.requested_by = MagicMock(value=requested_by)
        modal.required_by = MagicMock(value=required_by)
        return modal

    async def test_creates_draft(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        assert draft_key(mock_interaction, COMMAND) in drafts

    async def test_draft_stores_impact(self, mock_interaction):
        await self._make_modal(impact="Minor").on_submit(mock_interaction)
        assert drafts[draft_key(mock_interaction, COMMAND)].impact == "Minor"

    async def test_posts_continue_button(self, mock_interaction):
        """Step 1 can't chain to a modal directly — posts an ephemeral Continue button."""
        await self._make_modal().on_submit(mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        assert isinstance(kwargs.get("view"), RfiStep2ContinueView)

    async def test_does_not_call_send_modal(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        mock_interaction.response.send_modal.assert_not_called()

    async def test_invalid_date_sends_ephemeral(self, mock_interaction):
        await self._make_modal(date="bad").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_invalid_required_by_sends_ephemeral(self, mock_interaction):
        await self._make_modal(required_by="bad").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_invalid_date_does_not_create_draft(self, mock_interaction):
        await self._make_modal(date="bad").on_submit(mock_interaction)
        assert draft_key(mock_interaction, COMMAND) not in drafts


# ---------------------------------------------------------------------------
# RfiStep1ModalOther (free-text impact)
# ---------------------------------------------------------------------------


class TestRfiStep1ModalOther:
    def setup_method(self):
        _clear_drafts()

    def _make_modal(self, impact_text="Custom impact"):
        modal = RfiStep1ModalOther(impact="Other")
        modal.date_requested = MagicMock(value="")
        modal.requested_by = MagicMock(value="Jack")
        modal.required_by = MagicMock(value="05/01/2026")
        modal.impact_other = MagicMock(value=impact_text)
        return modal

    async def test_uses_free_text_impact(self, mock_interaction):
        await self._make_modal("Custom impact").on_submit(mock_interaction)
        assert drafts[draft_key(mock_interaction, COMMAND)].impact == "Custom impact"

    async def test_posts_continue_button(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert isinstance(kwargs.get("view"), RfiStep2ContinueView)


# ---------------------------------------------------------------------------
# RfiStep2Modal
# ---------------------------------------------------------------------------


class TestRfiStep2Modal:
    def setup_method(self):
        _clear_drafts()

    def _make_modal(self, key=_TEST_KEY, questions="What?", issues="Plans unclear", solution=""):
        modal = RfiStep2Modal(key=key)
        modal.questions = MagicMock(value=questions)
        modal.issues = MagicMock(value=issues)
        modal.proposed_solution = MagicMock(value=solution)
        return modal

    async def test_fills_draft_questions(self, mock_interaction):
        _seed_draft()
        await self._make_modal(questions="What gauge?").on_submit(mock_interaction)
        assert drafts[_TEST_KEY].questions == "What gauge?"

    async def test_fills_draft_issues(self, mock_interaction):
        _seed_draft()
        await self._make_modal(issues="Plans unclear").on_submit(mock_interaction)
        assert drafts[_TEST_KEY].issues == "Plans unclear"

    async def test_fills_proposed_solution(self, mock_interaction):
        _seed_draft()
        await self._make_modal(solution="Use 12 AWG").on_submit(mock_interaction)
        assert drafts[_TEST_KEY].proposed_solution == "Use 12 AWG"

    async def test_blank_solution_stored_as_empty(self, mock_interaction):
        _seed_draft()
        await self._make_modal(solution="").on_submit(mock_interaction)
        assert drafts[_TEST_KEY].proposed_solution == ""

    async def test_sends_embed_and_view(self, mock_interaction):
        _seed_draft()
        await self._make_modal().on_submit(mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert isinstance(kwargs.get("embed"), discord.Embed)
        assert kwargs.get("view") is not None

    async def test_message_stored(self, mock_interaction, mock_message):
        _seed_draft()
        await self._make_modal().on_submit(mock_interaction)
        assert drafts[_TEST_KEY].message is mock_message

    async def test_missing_draft_sends_ephemeral(self, mock_interaction):
        await self._make_modal().on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# RfiStep2ContinueView
# ---------------------------------------------------------------------------


class TestRfiStep2ContinueView:
    def setup_method(self):
        _clear_drafts()

    async def test_continue_opens_step2_modal(self, mock_interaction):
        _seed_draft()
        view = RfiStep2ContinueView(_TEST_KEY)
        await view.continue_to_step2.callback(mock_interaction)
        mock_interaction.response.send_modal.assert_called_once()
        assert isinstance(mock_interaction.response.send_modal.call_args.args[0], RfiStep2Modal)

    async def test_continue_missing_draft_sends_ephemeral(self, mock_interaction):
        view = RfiStep2ContinueView(_TEST_KEY)
        await view.continue_to_step2.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# RfiImpactSelectView
# ---------------------------------------------------------------------------


class TestRfiImpactSelectView:
    async def test_named_impact_returns_step1_modal(self):
        view = RfiImpactSelectView()
        modal = await view.modal_factory("Work stops")
        assert isinstance(modal, RfiStep1Modal)

    async def test_other_returns_step1_modal_other(self):
        view = RfiImpactSelectView()
        modal = await view.modal_factory("Other")
        assert isinstance(modal, RfiStep1ModalOther)

    async def test_all_impact_options_in_select(self):
        view = RfiImpactSelectView()
        select = next(c for c in view.children if isinstance(c, discord.ui.Select))
        option_values = [o.value for o in select.options]
        for opt in RFI_IMPACT_OPTIONS:
            assert opt in option_values
        assert "Other" in option_values


# ---------------------------------------------------------------------------
# DraftView — simple (no material buttons)
# ---------------------------------------------------------------------------


class TestRfiDraftViewDone:
    def setup_method(self):
        _clear_drafts()

    async def test_done_removes_draft(self, mock_interaction, mock_message):
        _seed_draft()
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert _TEST_KEY not in drafts

    async def test_done_swaps_to_submitted_view(self, mock_interaction, mock_message):
        _seed_draft()
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        assert isinstance(
            mock_interaction.response.edit_message.call_args.kwargs.get("view"), SubmittedView
        )

    async def test_done_final_embed_title(self, mock_interaction, mock_message):
        _seed_draft()
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).done.callback(mock_interaction)
        embed = mock_interaction.response.edit_message.call_args.kwargs.get("embed")
        assert "Submitted" in embed.title


class TestRfiDraftViewCancel:
    def setup_method(self):
        _clear_drafts()

    async def test_cancel_removes_draft(self, mock_interaction, mock_message):
        _seed_draft()
        mock_interaction.message = mock_message
        await DraftView(_TEST_KEY).cancel.callback(mock_interaction)
        assert _TEST_KEY not in drafts


# ---------------------------------------------------------------------------
# Rfi cog
# ---------------------------------------------------------------------------


class TestRfiCog:
    def setup_method(self):
        _clear_drafts()

    async def test_opens_select_when_no_draft(self, mock_interaction):
        cog = Rfi(MagicMock())
        cog._stop_sweep()
        await cog.rfi.callback(cog, mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert isinstance(kwargs.get("view"), RfiImpactSelectView)
        assert kwargs.get("ephemeral") is True

    async def test_blocks_second_draft(self, mock_interaction):
        _seed_draft(draft_key(mock_interaction, COMMAND))
        cog = Rfi(MagicMock())
        cog._stop_sweep()
        await cog.rfi.callback(cog, mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert not isinstance(kwargs.get("view"), RfiImpactSelectView)
        assert kwargs.get("ephemeral") is True

    async def test_expired_draft_allows_new_command(self, mock_interaction):
        _seed_draft(draft_key(mock_interaction, COMMAND), expired=True)
        cog = Rfi(MagicMock())
        cog._stop_sweep()
        await cog.rfi.callback(cog, mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert isinstance(kwargs.get("view"), RfiImpactSelectView)


# ---------------------------------------------------------------------------
# RFI_IMPACT_OPTIONS constant
# ---------------------------------------------------------------------------


def test_rfi_impact_options_is_a_list():
    assert isinstance(RFI_IMPACT_OPTIONS, list)
    assert len(RFI_IMPACT_OPTIONS) > 0


def test_other_not_in_rfi_impact_options():
    """'Other' should be appended by make_select_then_modal, not hardcoded."""
    assert "Other" not in RFI_IMPACT_OPTIONS


# ---------------------------------------------------------------------------
# EditRfiModal
# ---------------------------------------------------------------------------


class TestEditRfiModal:
    def setup_method(self):
        _clear_drafts()

    def _make_modal(
        self,
        key=_TEST_KEY,
        questions="Updated question?",
        issues="Updated issue",
        solution="Updated solution",
    ):
        modal = EditRfiModal(key, drafts, _draft_embed, DraftView)
        modal.questions = MagicMock(value=questions)
        modal.issues = MagicMock(value=issues)
        modal.proposed_solution = MagicMock(value=solution)
        return modal

    async def test_pre_fills_from_draft(self):
        draft = _seed_draft()
        modal = EditRfiModal(_TEST_KEY, drafts, _draft_embed, DraftView)
        assert modal.questions.default == draft.questions
        assert modal.issues.default == draft.issues
        assert modal.proposed_solution.default == draft.proposed_solution

    async def test_updates_draft_on_submit(self):
        _seed_draft()
        interaction, msg = make_interaction()
        interaction.message = msg
        await self._make_modal(
            questions="New question?", issues="New issue", solution="New solution"
        ).on_submit(interaction)
        draft = drafts[_TEST_KEY]
        assert draft.questions == "New question?"
        assert draft.issues == "New issue"
        assert draft.proposed_solution == "New solution"

    async def test_clears_solution_when_blank(self):
        _seed_draft()
        interaction, msg = make_interaction()
        interaction.message = msg
        await self._make_modal(solution="").on_submit(interaction)
        assert drafts[_TEST_KEY].proposed_solution == ""

    async def test_refreshes_embed_on_submit(self):
        _seed_draft()
        interaction, msg = make_interaction()
        interaction.message = msg
        await self._make_modal().on_submit(interaction)
        interaction.response.edit_message.assert_called_once()

    async def test_missing_draft_sends_ephemeral(self):
        _seed_draft()
        modal = self._make_modal()
        _clear_drafts()
        interaction, _ = make_interaction()
        await modal.on_submit(interaction)
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# DraftView has Edit button
# ---------------------------------------------------------------------------


class TestRfiDraftViewEditButton:
    async def test_edit_button_present(self):
        view = DraftView(_TEST_KEY)
        labels = [c.label for c in view.children]
        assert "✏️ Edit" in labels

    async def test_done_cancel_on_row_1(self):
        view = DraftView(_TEST_KEY)
        done_btn = next(c for c in view.children if c.label == "✅ Done")
        cancel_btn = next(c for c in view.children if c.label == "🗑️ Cancel")
        assert done_btn.row == 1
        assert cancel_btn.row == 1
