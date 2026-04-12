"""
Base class for cog-specific edit modals.

Used by make_draft_view's edit_modal_factory parameter. Each cog subclasses
EditModalBase, defines its TextInput fields, and implements _pre_fill and _apply.
"""

from __future__ import annotations

import logging

import discord

from src.models.draft_base import DraftBase
from src.views.draft_view_base import DraftKey, EmbedBuilder

log = logging.getLogger(__name__)


class EditModalBase(discord.ui.Modal):
    """
    Base class for edit modals used by make_draft_view's edit_modal_factory.

    Subclasses define their TextInput fields as class attributes and implement:
      - _pre_fill(draft): set .default on each field from current draft values
      - _apply(draft) -> str | None: validate inputs, update draft in-place,
        return an error message string or None on success
    """

    def __init__(self, key: DraftKey, store: dict, draft_embed_fn: EmbedBuilder, view_cls: type):
        super().__init__()
        self.key = key
        self.store = store
        self.draft_embed_fn = draft_embed_fn
        self.view_cls = view_cls
        self._pre_fill(store[key])

    def _pre_fill(self, draft: DraftBase) -> None:
        raise NotImplementedError

    def _apply(self, draft: DraftBase) -> str | None:
        raise NotImplementedError

    async def on_submit(self, interaction: discord.Interaction):
        draft = self.store.get(self.key)
        if not draft:
            log.error("Draft not found on edit submit for key %s", self.key)
            await interaction.response.send_message(
                "⚠️ Draft expired. Please run the command again.", ephemeral=True
            )
            return

        error = self._apply(draft)
        if error:
            log.warning("Edit validation failed for key %s: %s", self.key, error)
            await interaction.response.send_message(error, ephemeral=True)
            return

        if hasattr(self.store, "save"):
            self.store.save(self.key)

        await interaction.response.defer()
        await interaction.message.edit(
            embed=self.draft_embed_fn(interaction.user, draft),
            view=self.view_cls(self.key),
        )
