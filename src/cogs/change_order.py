import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.helpers.helpers import (
    build_change_order_embed,
    discord_timestamp,
    format_plain_text,
    parse_materials,
    resolve_date,
)
from src.models.draft_change_order import DraftChangeOrder
from src.views.draft_view_base import (
    DRAFT_TTL_SECONDS,  # noqa: F401 — re-exported so existing tests can import it from here
    DraftKey,
    SubmittedView,  # noqa: F401 — re-exported for tests
    SweepMixin,
    _is_numeric,
    draft_key,
    evict,
    is_expired,
    make_draft_view,
)

log = logging.getLogger(__name__)
COMMAND = "changeorder"

drafts: dict[DraftKey, DraftChangeOrder] = {}


# ---------------------------------------------------------------------------
# Embed / plain-text builders
# ---------------------------------------------------------------------------


def _draft_embed(user, draft: DraftChangeOrder) -> discord.Embed:
    return build_change_order_embed(
        user=user,
        date=draft.date,
        submitted_at=draft.submitted_at,
        scope=draft.scope,
        material_list=draft.materials,
        title="📋 Change Order Draft",
        color=discord.Color.blue(),
    )


def _final_embed(user, draft: DraftChangeOrder) -> discord.Embed:
    return build_change_order_embed(
        user=user,
        date=draft.date,
        submitted_at=draft.submitted_at,
        scope=draft.scope,
        material_list=draft.materials,
        title="📋 Change Order — Submitted",
        color=discord.Color.green(),
    )


def _plain_text(user, draft: DraftChangeOrder) -> str:
    return format_plain_text(
        user=user,
        date=draft.date,
        scope=draft.scope,
        material_list=draft.materials,
    )


DraftView = make_draft_view(
    drafts, COMMAND, _draft_embed, _final_embed, _plain_text, has_materials=True
)


# ---------------------------------------------------------------------------
# Modal
# ---------------------------------------------------------------------------


class ScopeModal(discord.ui.Modal, title="Change Order — Step 1 of 2"):
    date_requested = discord.ui.TextInput(
        label="Date Requested",
        placeholder="MM/DD/YYYY  (leave blank for today)",
        required=False,
        max_length=10,
    )
    scope_added = discord.ui.TextInput(
        label="Scope Added",
        placeholder="Describe the work being added...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
    )
    materials_input = discord.ui.TextInput(
        label="Materials  (Name - Quantity, one per line)",
        placeholder="20A Breaker - 3\n12 AWG Wire (250ft) - 2",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            date = resolve_date(self.date_requested.value)
        except ValueError as e:
            log.warning(
                "Date error for user %s (%s) in channel %s: %s",
                interaction.user,
                interaction.user.id,
                interaction.channel_id,
                e,
            )
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return

        material_list: list[tuple[str, str]] = []
        if self.materials_input.value.strip():
            material_list, parse_errors = parse_materials(self.materials_input.value)
            non_numeric = [f"`{n} - {q}`" for n, q in material_list if not _is_numeric(q)]
            if parse_errors or non_numeric:
                error_lines = []
                if parse_errors:
                    error_lines.append(
                        "**Missing quantity** (expected `Name - Quantity`):\n"
                        + "\n".join(f"• `{e}`" for e in parse_errors)
                    )
                if non_numeric:
                    error_lines.append(
                        "**Non-numeric quantity:**\n" + "\n".join(f"• {e}" for e in non_numeric)
                    )
                log.warning(
                    "Material errors on scope submit for user %s (%s): parse=%s non_numeric=%s",
                    interaction.user,
                    interaction.user.id,
                    parse_errors,
                    non_numeric,
                )
                await interaction.response.send_message(
                    "⚠️ Some material lines couldn't be added:\n\n"
                    + "\n\n".join(error_lines)
                    + "\n\nPlease run `/changeorder` again.",
                    ephemeral=True,
                )
                return

        key = draft_key(interaction, COMMAND)
        drafts[key] = DraftChangeOrder(
            date=date,
            submitted_at=discord_timestamp(),
            scope=self.scope_added.value.strip(),
            materials=material_list,
        )
        draft = drafts[key]
        view = DraftView(key)
        await interaction.response.send_message(
            content="Draft created! Add materials below, then click **Done** when finished.",
            embed=_draft_embed(interaction.user, draft),
            view=view,
        )
        msg = await interaction.original_response()
        view.message = msg
        draft.message = msg


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class ChangeOrder(commands.Cog, SweepMixin):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._store = drafts
        self._command_name = COMMAND
        self._start_sweep()

    def cog_unload(self):
        self._stop_sweep()

    @app_commands.command(name=COMMAND, description="Submit a change order")
    async def change_order(self, interaction: discord.Interaction):
        key = draft_key(interaction, COMMAND)
        existing = drafts.get(key)
        if existing and is_expired(existing):
            log.info(
                "Lazy eviction on command entry for user %s in channel %s",
                key[0],
                key[1],
            )
            await evict(drafts, key)
        if key in drafts:
            await interaction.response.send_message(
                "⚠️ You already have a change order in progress in this channel. "
                "Finish or cancel it before starting a new one.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(ScopeModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(ChangeOrder(bot))
