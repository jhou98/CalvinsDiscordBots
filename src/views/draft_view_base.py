"""
Shared draft-view infrastructure used by every slash command.

Each cog:
  1. Defines its own `drafts` dict keyed by DraftKey
  2. Defines _draft_embed(), _final_embed(), _plain_text() functions
  3. Calls make_draft_view() to get a ready-to-use DraftView class
  4. Calls make_select_then_modal() for any field that needs a select-first flow
  5. Mixes SweepMixin into its Cog for background TTL eviction

DraftKey = (user_id, channel_id, command_name)
  → one active draft per user per channel per command
  → a user can run /matorder and /rfi simultaneously in the same channel
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import discord
from discord.ext import tasks

from src.models.draft_base import DraftBase

log = logging.getLogger(__name__)

DRAFT_TTL_SECONDS = 604800  # 7 days
SWEEP_INTERVAL_MINS = 60  # background sweep cadence

# (user_id, channel_id, command_name) — all strings to avoid snowflake overflow
DraftKey = tuple[str, str, str]

EmbedBuilder = Callable[[discord.Member, DraftBase], discord.Embed]
TextBuilder = Callable[[discord.Member, DraftBase], str]


# ---------------------------------------------------------------------------
# Expiry helpers
# ---------------------------------------------------------------------------


def is_expired(draft: DraftBase) -> bool:
    """Return True if the draft has lived longer than DRAFT_TTL_SECONDS."""
    return (datetime.now(UTC) - draft.created_at).total_seconds() > DRAFT_TTL_SECONDS


async def evict(store: dict, key: DraftKey) -> None:
    """
    Remove a draft and edit its Discord message to show the expiry notice.
    Safe to call from both lazy checks and the background sweep.
    """
    draft = store.pop(key, None)
    if draft and draft.message:
        with contextlib.suppress(discord.NotFound, discord.HTTPException):
            await draft.message.edit(
                content="⏱️ This request expired due to inactivity.",
                embed=None,
                view=None,
            )


def draft_key(interaction: discord.Interaction, command_name: str) -> DraftKey:
    """Build the store key from an interaction."""
    return (str(interaction.user.id), str(interaction.channel_id), command_name)


async def check_existing_draft(
    interaction: discord.Interaction,
    store: dict,
    command_name: str,
    label: str,
) -> bool:
    """
    Check for an existing draft, evict if expired.
    Returns True (blocked) if there is a non-expired draft, False otherwise.
    """
    key = draft_key(interaction, command_name)
    existing = store.get(key)
    if existing and is_expired(existing):
        log.info(
            "Lazy eviction on command entry for user %s in channel %s",
            key[0],
            key[1],
        )
        await evict(store, key)
    if key in store:
        await interaction.response.send_message(
            f"⚠️ You already have {label} in progress in this channel. "
            "Finish or cancel it before starting a new one.",
            ephemeral=True,
        )
        return True
    return False


# ---------------------------------------------------------------------------
# SubmittedView — open to anyone in the channel, no timeout
# ---------------------------------------------------------------------------


class SubmittedView(discord.ui.View):
    """
    Replaces DraftView once a request is submitted.
    The Copy Text button is intentionally open to all channel members so
    teammates can grab the plain-text output without needing to have been
    the original submitter.
    """

    def __init__(self, plain_text: str):
        super().__init__(timeout=None)
        self.plain_text = plain_text

    @discord.ui.button(label="⚡ Copy Text", style=discord.ButtonStyle.secondary)
    async def copy_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"```\n{self.plain_text}\n```",
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# AddMaterialModal — shared by any command that has a materials list
# ---------------------------------------------------------------------------


class AddMaterialModal(discord.ui.Modal, title="Add Materials"):
    materials_input = discord.ui.TextInput(
        label="Materials  (Name - Quantity, one per line)",
        placeholder="20A Breaker - 3\n12 AWG Wire (250ft) - 2\nJunction Box - 5",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
    )

    def __init__(
        self,
        draft_key: DraftKey,
        store: dict,
        draft_embed_fn: EmbedBuilder,
        view_cls: type,
    ):
        super().__init__()
        self.draft_key = draft_key
        self.store = store
        self.draft_embed_fn = draft_embed_fn
        self.view_cls = view_cls

    async def on_submit(self, interaction: discord.Interaction):
        from src.helpers.material_utils import validate_materials

        draft = self.store.get(self.draft_key)
        if not draft:
            log.error("Draft not found on add material for key %s", self.draft_key)
            await interaction.response.send_message(
                "⚠️ Your draft expired. Please run the command again.",
                ephemeral=True,
            )
            return
        if is_expired(draft):
            await evict(self.store, self.draft_key)
            await interaction.response.send_message(
                "⏱️ Your draft expired. Please run the command again.",
                ephemeral=True,
            )
            return

        material_list, error_msg = validate_materials(self.materials_input.value)
        if error_msg:
            log.warning("Material validation failed for key %s", self.draft_key)
            await interaction.response.send_message(error_msg, ephemeral=True)
            return

        draft.materials.extend(material_list)
        if hasattr(self.store, "save"):
            self.store.save(self.draft_key)
        await interaction.response.edit_message(
            embed=self.draft_embed_fn(interaction.user, draft),
            view=self.view_cls(self.draft_key),
        )


# ---------------------------------------------------------------------------
# make_select_then_modal
# ---------------------------------------------------------------------------


def make_select_then_modal(
    options: list[str],
    *,
    other_label: str = "Other",
    placeholder: str = "Select an option...",
) -> type:
    """
    Return a View base class that shows a Select menu (ephemeral message).
    On selection it calls self.modal_factory(selected_value) and opens the
    returned modal.

    Subclass it and implement modal_factory():

        class MySelectView(make_select_then_modal(MY_OPTIONS)):
            async def modal_factory(self, value: str) -> discord.ui.Modal:
                if value == "Other":
                    return MyModalOther()
                return MyModal(pre_selected=value)

    The options list is baked in at class-creation time — to change options
    just pass a different list. "Other" is always appended if not already present.
    """
    all_options = list(options)
    if other_label not in all_options:
        all_options.append(other_label)

    select_options = [discord.SelectOption(label=opt, value=opt) for opt in all_options]

    class SelectThenModalView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)  # 3 min — ephemeral expires anyway

        async def modal_factory(self, value: str) -> discord.ui.Modal:
            raise NotImplementedError("Subclass must implement modal_factory")

        @discord.ui.select(
            placeholder=placeholder,
            options=select_options,
            min_values=1,
            max_values=1,
        )
        async def on_select(self, interaction: discord.Interaction, select: discord.ui.Select):
            modal = await self.modal_factory(select.values[0])
            await interaction.response.send_modal(modal)

    return SelectThenModalView


# ---------------------------------------------------------------------------
# make_draft_view
# ---------------------------------------------------------------------------


def make_draft_view(
    store: dict,
    command_name: str,
    draft_embed_fn: EmbedBuilder,
    final_embed_fn: EmbedBuilder,
    plain_text_fn: TextBuilder,
    *,
    has_materials: bool = False,
    edit_modal_factory: type | None = None,
) -> type:
    """
    Return a DraftView class pre-wired to the given store and builder functions.

    Pass has_materials=True to include ➕ Add Material and ↩️ Undo Last buttons
    (used by /changeorder and /matorder).

    Pass edit_modal_factory to include a ✏️ Edit button. The factory is called as
    edit_modal_factory(key, store, draft_embed_fn, view_cls) and must return a
    discord.ui.Modal.

    discord.py reads button decorators at class-definition time via
    __init_subclass__, so we define both layouts as explicit classes and return
    the correct one. The Edit button is added programmatically in __init__
    to avoid class proliferation.
    """

    # ------------------------------------------------------------------
    # Shared logic extracted so both classes stay DRY
    # ------------------------------------------------------------------

    async def _check_expired(self_view, interaction: discord.Interaction) -> bool:
        draft = store.get(self_view.key)
        if draft and is_expired(draft):
            await evict(store, self_view.key)
            await interaction.response.send_message(
                "⏱️ This request has expired. Please run the command again.",
                ephemeral=True,
            )
            return True
        return False

    async def _interaction_check(self_view, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self_view.key[0]:
            await interaction.response.send_message(
                "⚠️ Only the person who started this request can modify it.",
                ephemeral=True,
            )
            return False
        return True

    async def _done(self_view, interaction: discord.Interaction, require_materials: bool):
        if await _check_expired(self_view, interaction):
            return
        draft = store.get(self_view.key)
        if not draft:
            log.error("Draft not found on submit for key %s", self_view.key)
            await interaction.response.send_message("⚠️ Draft not found.", ephemeral=True)
            return
        if require_materials and not getattr(draft, "materials", None):
            await interaction.response.send_message(
                "⚠️ Please add at least one material before submitting. "
                "Use **➕ Add Material** or **🗑️ Cancel** to discard.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            content="✅ Submitted!",
            embed=final_embed_fn(interaction.user, draft),
            view=SubmittedView(plain_text_fn(interaction.user, draft)),
        )
        store.pop(self_view.key, None)
        log.info(
            "%s submitted by user %s in channel %s",
            command_name,
            self_view.key[0],
            self_view.key[1],
        )

    async def _cancel(self_view, interaction: discord.Interaction):
        if await _check_expired(self_view, interaction):
            return
        for child in self_view.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="🗑️ Request cancelled.", embed=None, view=self_view
        )
        store.pop(self_view.key, None)
        log.info(
            "%s cancelled by user %s in channel %s",
            command_name,
            self_view.key[0],
            self_view.key[1],
        )

    # ------------------------------------------------------------------
    # Edit button helper — shared by both layouts when edit_modal_factory
    # is provided. Added programmatically in __init__ to avoid needing
    # extra class variants.
    # ------------------------------------------------------------------

    def _add_edit_button(self_view, row: int) -> None:
        if edit_modal_factory is None:
            return

        edit_btn = discord.ui.Button(label="✏️ Edit", style=discord.ButtonStyle.secondary, row=row)

        async def _edit_callback(interaction: discord.Interaction):
            if await _check_expired(self_view, interaction):
                return
            draft = store.get(self_view.key)
            if not draft:
                log.error("Draft not found on edit for key %s", self_view.key)
                await interaction.response.send_message("⚠️ Draft not found.", ephemeral=True)
                return
            modal = edit_modal_factory(self_view.key, store, draft_embed_fn, type(self_view))
            await interaction.response.send_modal(modal)

        edit_btn.callback = _edit_callback
        self_view.add_item(edit_btn)

    # ------------------------------------------------------------------
    # Layout with material buttons
    #   row 0: Add / Undo
    #   row 1: Edit (if edit_modal_factory)
    #   row N: Done / Cancel
    # ------------------------------------------------------------------

    if has_materials:
        done_cancel_row = 2 if edit_modal_factory else 1

        class DraftViewWithMaterials(discord.ui.View):
            def __init__(self, key: DraftKey):
                super().__init__(timeout=None)
                self.key = key
                self.message: discord.Message | None = None
                _add_edit_button(self, row=1)

            async def _check_expired(self, interaction):
                return await _check_expired(self, interaction)

            async def interaction_check(self, interaction):
                return await _interaction_check(self, interaction)

            @discord.ui.button(label="➕ Add Material", style=discord.ButtonStyle.primary, row=0)
            async def add_material(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                if await self._check_expired(interaction):
                    return
                if self.key not in store:
                    await interaction.response.send_message(
                        "⚠️ Draft not found. Please run the command again.", ephemeral=True
                    )
                    return
                await interaction.response.send_modal(
                    AddMaterialModal(
                        draft_key=self.key,
                        store=store,
                        draft_embed_fn=draft_embed_fn,
                        view_cls=DraftViewWithMaterials,
                    )
                )

            @discord.ui.button(label="↩️ Undo Last", style=discord.ButtonStyle.secondary, row=0)
            async def undo_last(self, interaction: discord.Interaction, button: discord.ui.Button):
                if await self._check_expired(interaction):
                    return
                draft = store.get(self.key)
                if not draft or not getattr(draft, "materials", None):
                    await interaction.response.send_message("Nothing to undo.", ephemeral=True)
                    return
                draft.materials.pop()
                if hasattr(store, "save"):
                    store.save(self.key)
                await interaction.response.edit_message(
                    embed=draft_embed_fn(interaction.user, draft),
                    view=DraftViewWithMaterials(self.key),
                )

            @discord.ui.button(
                label="✅ Done", style=discord.ButtonStyle.success, row=done_cancel_row
            )
            async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
                await _done(self, interaction, require_materials=True)

            @discord.ui.button(
                label="🗑️ Cancel", style=discord.ButtonStyle.danger, row=done_cancel_row
            )
            async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                await _cancel(self, interaction)

        return DraftViewWithMaterials

    # ------------------------------------------------------------------
    # Simple layout
    #   row 0: Edit (if edit_modal_factory)
    #   row N: Done / Cancel
    # ------------------------------------------------------------------

    else:
        done_cancel_row = 1 if edit_modal_factory else 0

        class DraftViewSimple(discord.ui.View):
            def __init__(self, key: DraftKey):
                super().__init__(timeout=None)
                self.key = key
                self.message: discord.Message | None = None
                _add_edit_button(self, row=0)

            async def _check_expired(self, interaction):
                return await _check_expired(self, interaction)

            async def interaction_check(self, interaction):
                return await _interaction_check(self, interaction)

            @discord.ui.button(
                label="✅ Done", style=discord.ButtonStyle.success, row=done_cancel_row
            )
            async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
                await _done(self, interaction, require_materials=False)

            @discord.ui.button(
                label="🗑️ Cancel", style=discord.ButtonStyle.danger, row=done_cancel_row
            )
            async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                await _cancel(self, interaction)

        return DraftViewSimple


# ---------------------------------------------------------------------------
# SweepMixin
# ---------------------------------------------------------------------------


class SweepMixin:
    """
    Mixin for commands.Cog subclasses that own a draft store.

    Usage in __init__:
        self._store        = drafts        # the module-level dict
        self._command_name = COMMAND       # for log messages
        self._start_sweep()

    Usage in cog_unload:
        self._stop_sweep()
    """

    _store: dict
    _command_name: str

    def _start_sweep(self):
        self.__sweep_loop = tasks.loop(minutes=SWEEP_INTERVAL_MINS)(self._do_sweep)
        self.__sweep_loop.before_loop(self._before_sweep)
        self.__sweep_loop.start()

    def _stop_sweep(self):
        self.__sweep_loop.cancel()

    async def _do_sweep(self):
        expired = [k for k, d in list(self._store.items()) if is_expired(d)]
        if expired:
            log.info(
                "Sweep evicting %d expired %s draft(s) from channels: %s",
                len(expired),
                self._command_name,
                [k[1] for k in expired],
            )
        for key in expired:
            await evict(self._store, key)

    async def _before_sweep(self):
        await self.bot.wait_until_ready()
