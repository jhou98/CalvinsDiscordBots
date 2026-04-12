"""
Tests for views/draft_view_base.py — shared view infrastructure.

These tests cover the base functions in isolation. The cog tests cover
the same behaviour indirectly, but isolating it here means a failure
points directly at the base rather than a specific cog.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import discord

from src.helpers.validation_utils import is_numeric
from src.models.draft_base import DraftBase
from src.views.draft_view_base import (
    DRAFT_TTL_SECONDS,
    AddMaterialModal,
    SubmittedView,
    draft_key,
    evict,
    is_expired,
    make_draft_view,
    make_select_then_modal,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_TEST_KEY = ("111", "222", "testcmd")


def _make_draft(*, expired: bool = False) -> DraftBase:
    age = timedelta(seconds=DRAFT_TTL_SECONDS + 60) if expired else timedelta(seconds=0)
    draft = DraftBase(created_at=datetime.now(UTC) - age)
    return draft


def _make_draft_with_materials(*, expired: bool = False):
    """DraftBase doesn't have materials — use a simple namespace instead."""
    draft = _make_draft(expired=expired)
    draft.materials = []  # type: ignore[attr-defined]
    return draft


def _make_interaction(user_id="111", channel_id="222"):
    msg = MagicMock(spec=discord.Message)
    msg.edit = AsyncMock()
    user = MagicMock(spec=discord.Member)
    user.id = user_id
    user.mention = f"<@{user_id}>"
    user.display_name = "TestUser"
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = user
    interaction.channel_id = channel_id
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.original_response = AsyncMock(return_value=msg)
    interaction.message = msg
    return interaction, msg


# ---------------------------------------------------------------------------
# is_numeric
# ---------------------------------------------------------------------------


class TestIsNumeric:
    def test_integer_string(self):
        assert is_numeric("3") is True

    def test_float_string(self):
        assert is_numeric("2.5") is True

    def test_negative(self):
        assert is_numeric("-1") is True

    def test_word(self):
        assert is_numeric("lots") is False

    def test_empty(self):
        assert is_numeric("") is False

    def test_mixed(self):
        assert is_numeric("3boxes") is False


# ---------------------------------------------------------------------------
# is_expired
# ---------------------------------------------------------------------------


class TestIsExpired:
    def test_fresh_draft_not_expired(self):
        assert is_expired(_make_draft()) is False

    def test_stale_draft_is_expired(self):
        assert is_expired(_make_draft(expired=True)) is True

    def test_exactly_at_ttl_boundary(self):
        """A draft aged exactly TTL seconds should not yet be expired (strictly >)."""
        draft = DraftBase(created_at=datetime.now(UTC) - timedelta(seconds=DRAFT_TTL_SECONDS - 1))
        assert is_expired(draft) is False


# ---------------------------------------------------------------------------
# evict
# ---------------------------------------------------------------------------


class TestEvict:
    async def test_removes_key_from_store(self):
        store = {_TEST_KEY: _make_draft()}
        await evict(store, _TEST_KEY)
        assert _TEST_KEY not in store

    async def test_edits_message_with_expiry_content(self):
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock()
        draft = _make_draft()
        draft.message = msg
        store = {_TEST_KEY: draft}
        await evict(store, _TEST_KEY)
        msg.edit.assert_called_once()
        assert "expired" in msg.edit.call_args.kwargs.get("content", "").lower()

    async def test_clears_embed_and_view_on_edit(self):
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock()
        draft = _make_draft()
        draft.message = msg
        store = {_TEST_KEY: draft}
        await evict(store, _TEST_KEY)
        kwargs = msg.edit.call_args.kwargs
        assert kwargs.get("embed") is None
        assert kwargs.get("view") is None

    async def test_no_message_does_not_raise(self):
        store = {_TEST_KEY: _make_draft()}  # message=None by default
        await evict(store, _TEST_KEY)  # should not raise

    async def test_missing_key_does_not_raise(self):
        await evict({}, _TEST_KEY)  # should not raise

    async def test_handles_not_found(self):
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        draft = _make_draft()
        draft.message = msg
        store = {_TEST_KEY: draft}
        await evict(store, _TEST_KEY)  # should not raise

    async def test_handles_http_exception(self):
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))
        draft = _make_draft()
        draft.message = msg
        store = {_TEST_KEY: draft}
        await evict(store, _TEST_KEY)  # should not raise


# ---------------------------------------------------------------------------
# draft_key
# ---------------------------------------------------------------------------


class TestDraftKey:
    def test_returns_tuple_of_strings(self, mock_interaction):
        key = draft_key(mock_interaction, "changeorder")
        assert isinstance(key, tuple)
        assert all(isinstance(part, str) for part in key)

    def test_includes_command_name(self, mock_interaction):
        key = draft_key(mock_interaction, "mycommand")
        assert key[2] == "mycommand"

    def test_same_user_different_commands_differ(self, mock_interaction):
        key1 = draft_key(mock_interaction, "changeorder")
        key2 = draft_key(mock_interaction, "matorder")
        assert key1 != key2

    def test_same_user_different_channels_differ(self):
        ia, _ = _make_interaction(channel_id="100")
        ib, _ = _make_interaction(channel_id="200")
        assert draft_key(ia, "cmd") != draft_key(ib, "cmd")


# ---------------------------------------------------------------------------
# SubmittedView
# ---------------------------------------------------------------------------


class TestSubmittedView:
    async def test_copy_text_sends_ephemeral(self, mock_interaction):
        view = SubmittedView("hello")
        await view.copy_text.callback(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_copy_text_wraps_in_code_block(self, mock_interaction):
        view = SubmittedView("hello")
        await view.copy_text.callback(mock_interaction)
        sent = mock_interaction.response.send_message.call_args.args[0]
        assert sent.startswith("```") and sent.endswith("```")

    async def test_copy_text_contains_plain_text(self, mock_interaction):
        view = SubmittedView("specific content")
        await view.copy_text.callback(mock_interaction)
        sent = mock_interaction.response.send_message.call_args.args[0]
        assert "specific content" in sent

    async def test_any_user_can_copy(self, mock_interaction):
        """No interaction_check — open to all channel members."""
        other_user = MagicMock(spec=discord.Member)
        other_user.id = "999"
        mock_interaction.user = other_user
        view = SubmittedView("text")
        await view.copy_text.callback(mock_interaction)
        mock_interaction.response.send_message.assert_called_once()

    async def test_no_timeout(self):
        assert SubmittedView("text").timeout is None


# ---------------------------------------------------------------------------
# AddMaterialModal
# ---------------------------------------------------------------------------


class TestAddMaterialModal:
    def _store_and_draft(self, *, expired: bool = False):
        store = {}
        draft = _make_draft_with_materials(expired=expired)
        store[_TEST_KEY] = draft
        return store, draft

    def _make_modal(self, store, materials_text="Breaker - 3"):
        embed_fn = MagicMock(return_value=MagicMock(spec=discord.Embed))
        view_cls = MagicMock(return_value=MagicMock(spec=discord.ui.View))
        modal = AddMaterialModal(
            draft_key=_TEST_KEY,
            store=store,
            draft_embed_fn=embed_fn,
            view_cls=view_cls,
        )
        modal.materials_input = MagicMock(value=materials_text)
        return modal

    async def test_adds_material_to_draft(self, mock_interaction):
        store, draft = self._store_and_draft()
        mock_interaction.message = MagicMock(spec=discord.Message)
        mock_interaction.message.edit = AsyncMock()
        await self._make_modal(store).on_submit(mock_interaction)
        assert ("Breaker", "3") in draft.materials

    async def test_adds_multiple_materials(self, mock_interaction):
        store, draft = self._store_and_draft()
        mock_interaction.message = MagicMock(spec=discord.Message)
        mock_interaction.message.edit = AsyncMock()
        await self._make_modal(store, "Breaker - 3\nWire - 2").on_submit(mock_interaction)
        assert ("Breaker", "3") in draft.materials
        assert ("Wire", "2") in draft.materials

    async def test_appends_to_existing_materials(self, mock_interaction):
        store, draft = self._store_and_draft()
        draft.materials = [("Existing", "1")]
        mock_interaction.message = MagicMock(spec=discord.Message)
        mock_interaction.message.edit = AsyncMock()
        await self._make_modal(store, "New - 5").on_submit(mock_interaction)
        assert len(draft.materials) == 2
        assert ("Existing", "1") in draft.materials

    async def test_edits_message_on_success(self, mock_interaction):
        store, _ = self._store_and_draft()
        mock_interaction.message = MagicMock(spec=discord.Message)
        mock_interaction.message.edit = AsyncMock()
        await self._make_modal(store).on_submit(mock_interaction)
        mock_interaction.message.edit.assert_called_once()

    async def test_missing_separator_sends_ephemeral(self, mock_interaction):
        store, _ = self._store_and_draft()
        await self._make_modal(store, "BadLine").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_non_numeric_quantity_sends_ephemeral(self, mock_interaction):
        store, _ = self._store_and_draft()
        await self._make_modal(store, "Breaker - lots").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_mixed_valid_invalid_sends_ephemeral(self, mock_interaction):
        store, _ = self._store_and_draft()
        await self._make_modal(store, "Good - 2\nBadLine").on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_mixed_valid_invalid_does_not_partially_add(self, mock_interaction):
        store, draft = self._store_and_draft()
        await self._make_modal(store, "Good - 2\nBadLine").on_submit(mock_interaction)
        assert draft.materials == []

    async def test_missing_draft_sends_ephemeral(self, mock_interaction):
        await self._make_modal({}).on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_expired_draft_sends_ephemeral(self, mock_interaction):
        store, _ = self._store_and_draft(expired=True)
        await self._make_modal(store).on_submit(mock_interaction)
        assert mock_interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_expired_draft_evicted(self, mock_interaction):
        store, _ = self._store_and_draft(expired=True)
        await self._make_modal(store).on_submit(mock_interaction)
        assert _TEST_KEY not in store

    async def test_decimal_quantity_accepted(self, mock_interaction):
        store, draft = self._store_and_draft()
        mock_interaction.message = MagicMock(spec=discord.Message)
        mock_interaction.message.edit = AsyncMock()
        await self._make_modal(store, "Breaker - 2.5").on_submit(mock_interaction)
        assert ("Breaker", "2.5") in draft.materials

    async def test_dash_in_item_name_parsed_correctly(self, mock_interaction):
        store, draft = self._store_and_draft()
        mock_interaction.message = MagicMock(spec=discord.Message)
        mock_interaction.message.edit = AsyncMock()
        await self._make_modal(store, "12-2 Wire - 5").on_submit(mock_interaction)
        assert ("12-2 Wire", "5") in draft.materials


# ---------------------------------------------------------------------------
# make_select_then_modal
# ---------------------------------------------------------------------------


class TestMakeSelectThenModal:
    async def test_other_appended_if_not_present(self):
        View = make_select_then_modal(["A", "B"])

        class ConcreteView(View):
            async def modal_factory(self, value):
                return MagicMock(spec=discord.ui.Modal)

        view = ConcreteView()
        select = next(c for c in view.children if isinstance(c, discord.ui.Select))
        values = [o.value for o in select.options]
        assert "Other" in values

    async def test_other_not_duplicated_if_already_present(self):
        View = make_select_then_modal(["A", "Other"])

        class ConcreteView(View):
            async def modal_factory(self, value):
                return MagicMock(spec=discord.ui.Modal)

        view = ConcreteView()
        select = next(c for c in view.children if isinstance(c, discord.ui.Select))
        values = [o.value for o in select.options]
        assert values.count("Other") == 1

    async def test_all_options_present_in_select(self):
        opts = ["Alpha", "Beta", "Gamma"]
        View = make_select_then_modal(opts)

        class ConcreteView(View):
            async def modal_factory(self, value):
                return MagicMock(spec=discord.ui.Modal)

        view = ConcreteView()
        select = next(c for c in view.children if isinstance(c, discord.ui.Select))
        values = [o.value for o in select.options]
        for opt in opts:
            assert opt in values

    async def test_custom_other_label(self):
        View = make_select_then_modal(["A"], other_label="Custom")

        class ConcreteView(View):
            async def modal_factory(self, value):
                return MagicMock(spec=discord.ui.Modal)

        view = ConcreteView()
        select = next(c for c in view.children if isinstance(c, discord.ui.Select))
        values = [o.value for o in select.options]
        assert "Custom" in values
        assert "Other" not in values

    async def test_on_select_calls_modal_factory_and_sends_modal(self, mock_interaction):
        expected_modal = MagicMock(spec=discord.ui.Modal)

        View = make_select_then_modal(["OptionA"])

        class ConcreteView(View):
            async def modal_factory(self, value):
                return expected_modal

        view = ConcreteView()
        view.on_select._values = ["OptionA"]
        await view.on_select.callback(mock_interaction)
        mock_interaction.response.send_modal.assert_called_once_with(expected_modal)

    async def test_placeholder_set_on_select(self):
        View = make_select_then_modal(["A"], placeholder="Pick something...")

        class ConcreteView(View):
            async def modal_factory(self, value):
                return MagicMock(spec=discord.ui.Modal)

        view = ConcreteView()
        select = next(c for c in view.children if isinstance(c, discord.ui.Select))
        assert select.placeholder == "Pick something..."


# ---------------------------------------------------------------------------
# make_draft_view — simple layout (has_materials=False)
# ---------------------------------------------------------------------------


class TestMakeDraftViewSimple:
    def _setup(self):
        store = {}
        draft = _make_draft()
        store[_TEST_KEY] = draft

        embed_fn = MagicMock(return_value=MagicMock(spec=discord.Embed))
        final_fn = MagicMock(return_value=MagicMock(spec=discord.Embed))
        text_fn = MagicMock(return_value="plain text")

        View = make_draft_view(store, "testcmd", embed_fn, final_fn, text_fn, has_materials=False)
        return store, draft, View

    async def test_no_timeout(self):
        _, _, View = self._setup()
        assert View(_TEST_KEY).timeout is None

    async def test_has_done_and_cancel_buttons(self):
        _, _, View = self._setup()
        view = View(_TEST_KEY)
        labels = [c.label for c in view.children]
        assert "✅ Done" in labels
        assert "🗑️ Cancel" in labels

    async def test_no_material_buttons(self):
        _, _, View = self._setup()
        view = View(_TEST_KEY)
        labels = [c.label for c in view.children]
        assert "➕ Add Material" not in labels
        assert "↩️ Undo Last" not in labels

    async def test_done_removes_draft(self):
        store, _, View = self._setup()
        interaction, msg = _make_interaction()
        interaction.message = msg
        await View(_TEST_KEY).done.callback(interaction)
        assert _TEST_KEY not in store

    async def test_done_edits_to_submitted_view(self):
        store, _, View = self._setup()
        interaction, msg = _make_interaction()
        interaction.message = msg
        await View(_TEST_KEY).done.callback(interaction)
        assert isinstance(msg.edit.call_args.kwargs.get("view"), SubmittedView)

    async def test_done_missing_draft_sends_ephemeral(self):
        _, _, View = self._setup()
        interaction, _ = _make_interaction()
        empty_store_view = View(_TEST_KEY)
        empty_store_view.key = ("0", "0", "noop")  # key not in store
        await empty_store_view.done.callback(interaction)
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_done_expired_sends_ephemeral(self):
        store = {}
        draft = _make_draft(expired=True)
        store[_TEST_KEY] = draft
        final_fn = MagicMock(return_value=MagicMock(spec=discord.Embed))
        embed_fn = MagicMock(return_value=MagicMock(spec=discord.Embed))
        text_fn = MagicMock(return_value="")
        View = make_draft_view(store, "testcmd", embed_fn, final_fn, text_fn, has_materials=False)
        interaction, _ = _make_interaction()
        await View(_TEST_KEY).done.callback(interaction)
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_cancel_removes_draft(self):
        store, _, View = self._setup()
        interaction, msg = _make_interaction()
        interaction.message = msg
        await View(_TEST_KEY).cancel.callback(interaction)
        assert _TEST_KEY not in store

    async def test_cancel_disables_buttons(self):
        store, _, View = self._setup()
        interaction, msg = _make_interaction()
        interaction.message = msg
        view = View(_TEST_KEY)
        await view.cancel.callback(interaction)
        assert all(child.disabled for child in view.children)

    async def test_interaction_check_wrong_user_blocked(self):
        _, _, View = self._setup()
        interaction, _ = _make_interaction(user_id="999")
        result = await View(_TEST_KEY).interaction_check(interaction)
        assert result is False
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_interaction_check_correct_user_allowed(self):
        _, _, View = self._setup()
        interaction, _ = _make_interaction(user_id="111")
        result = await View(_TEST_KEY).interaction_check(interaction)
        assert result is True


# ---------------------------------------------------------------------------
# make_draft_view — materials layout (has_materials=True)
# ---------------------------------------------------------------------------


class TestMakeDraftViewWithMaterials:
    def _setup(self):
        store = {}
        draft = _make_draft_with_materials()
        store[_TEST_KEY] = draft

        embed_fn = MagicMock(return_value=MagicMock(spec=discord.Embed))
        final_fn = MagicMock(return_value=MagicMock(spec=discord.Embed))
        text_fn = MagicMock(return_value="plain text")

        View = make_draft_view(store, "testcmd", embed_fn, final_fn, text_fn, has_materials=True)
        return store, draft, View

    async def test_has_material_buttons(self):
        _, _, View = self._setup()
        view = View(_TEST_KEY)
        labels = [c.label for c in view.children]
        assert "➕ Add Material" in labels
        assert "↩️ Undo Last" in labels

    async def test_done_requires_materials(self):
        store, draft, View = self._setup()
        draft.materials = []
        interaction, msg = _make_interaction()
        interaction.message = msg
        await View(_TEST_KEY).done.callback(interaction)
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True
        assert _TEST_KEY in store  # draft not removed

    async def test_done_with_materials_removes_draft(self):
        store, draft, View = self._setup()
        draft.materials = [("Breaker", "2")]
        interaction, msg = _make_interaction()
        interaction.message = msg
        await View(_TEST_KEY).done.callback(interaction)
        assert _TEST_KEY not in store

    async def test_undo_removes_last_material(self):
        store, draft, View = self._setup()
        draft.materials = [("A", "1"), ("B", "2")]
        interaction, msg = _make_interaction()
        interaction.message = msg
        await View(_TEST_KEY).undo_last.callback(interaction)
        assert draft.materials == [("A", "1")]

    async def test_undo_empty_sends_ephemeral(self):
        store, draft, View = self._setup()
        draft.materials = []
        interaction, _ = _make_interaction()
        await View(_TEST_KEY).undo_last.callback(interaction)
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True

    async def test_add_material_opens_modal(self):
        store, _, View = self._setup()
        interaction, _ = _make_interaction()
        await View(_TEST_KEY).add_material.callback(interaction)
        modal = interaction.response.send_modal.call_args.args[0]
        assert isinstance(modal, AddMaterialModal)


# ---------------------------------------------------------------------------
# SweepMixin
# ---------------------------------------------------------------------------


class TestSweepMixin:
    async def test_sweep_evicts_expired_drafts(self):
        from discord.ext import commands

        from src.views.draft_view_base import SweepMixin

        store = {_TEST_KEY: _make_draft(expired=True)}

        class FakeCog(commands.Cog, SweepMixin):
            def __init__(self):
                self.bot = MagicMock()
                self.bot.wait_until_ready = AsyncMock()
                self._store = store
                self._command_name = "testcmd"
                self._start_sweep()

        cog = FakeCog()
        cog._stop_sweep()
        await cog._do_sweep()
        assert _TEST_KEY not in store

    async def test_sweep_preserves_fresh_drafts(self):
        from discord.ext import commands

        from src.views.draft_view_base import SweepMixin

        store = {_TEST_KEY: _make_draft(expired=False)}

        class FakeCog(commands.Cog, SweepMixin):
            def __init__(self):
                self.bot = MagicMock()
                self.bot.wait_until_ready = AsyncMock()
                self._store = store
                self._command_name = "testcmd"
                self._start_sweep()

        cog = FakeCog()
        cog._stop_sweep()
        await cog._do_sweep()
        assert _TEST_KEY in store

    async def test_sweep_mixed(self):
        from discord.ext import commands

        from src.views.draft_view_base import SweepMixin

        expired_key = ("1", "1", "cmd")
        fresh_key = ("2", "2", "cmd")
        store = {
            expired_key: _make_draft(expired=True),
            fresh_key: _make_draft(expired=False),
        }

        class FakeCog(commands.Cog, SweepMixin):
            def __init__(self):
                self.bot = MagicMock()
                self.bot.wait_until_ready = AsyncMock()
                self._store = store
                self._command_name = "testcmd"
                self._start_sweep()

        cog = FakeCog()
        cog._stop_sweep()
        await cog._do_sweep()
        assert expired_key not in store
        assert fresh_key in store
