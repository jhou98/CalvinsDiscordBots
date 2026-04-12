import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.helpers import discord_timestamp, format_materials, resolve_date, validate_materials
from src.models.draft_change_order import DraftChangeOrder
from src.views.draft_view_base import (
    DraftKey,
    SweepMixin,
    check_existing_draft,
    draft_key,
    make_draft_view,
)

log = logging.getLogger(__name__)
COMMAND = "changeorder"

drafts: dict[DraftKey, DraftChangeOrder] = {}


# ---------------------------------------------------------------------------
# Embed / plain-text builders
# ---------------------------------------------------------------------------

_DEFAULT_EMBED_COLOR = discord.Color.yellow()


def _build_change_order_embed(
    user: discord.User | discord.Member,
    date_requested: str,
    submitted_at: str,
    scope: str,
    material_list: list[tuple[str, str]],
    *,
    title: str = "📋 Change Order",
    color: discord.Color = _DEFAULT_EMBED_COLOR,
) -> discord.Embed:
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="📅 Date Requested", value=date_requested, inline=True)
    embed.add_field(name="🕐 Submitted At", value=submitted_at, inline=True)
    embed.add_field(name="👤 Submitted By", value=user.mention, inline=True)
    embed.add_field(name="🔧 Scope Added", value=scope, inline=False)
    embed.add_field(
        name=f"📦 Materials ({len(material_list)} item{'s' if len(material_list) != 1 else ''})",
        value=format_materials(material_list),
        inline=False,
    )
    embed.set_footer(text="Change Order System")
    return embed


def _format_plain_text(
    user: discord.User | discord.Member,
    date_requested: str,
    scope: str,
    material_list: list[tuple[str, str]],
) -> str:
    lines = [
        "CHANGE ORDER",
        f"Date Requested: {date_requested}",
        f"Submitted By:   {user.display_name}",
        "",
        "Scope Added:",
        scope,
        "",
        "Materials:",
    ]
    if material_list:
        lines += [f"  {name} - {qty}" for name, qty in material_list]
    else:
        lines.append("  No materials listed.")
    return "\n".join(lines)


def _draft_embed(user, draft: DraftChangeOrder) -> discord.Embed:
    return _build_change_order_embed(
        user=user,
        date_requested=draft.date_requested,
        submitted_at=draft.submitted_at,
        scope=draft.scope,
        material_list=draft.materials,
        title="📋 Change Order Draft",
        color=discord.Color.blue(),
    )


def _final_embed(user, draft: DraftChangeOrder) -> discord.Embed:
    return _build_change_order_embed(
        user=user,
        date_requested=draft.date_requested,
        submitted_at=draft.submitted_at,
        scope=draft.scope,
        material_list=draft.materials,
        title="📋 Change Order — Submitted",
        color=discord.Color.green(),
    )


def _plain_text(user, draft: DraftChangeOrder) -> str:
    return _format_plain_text(
        user=user,
        date_requested=draft.date_requested,
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
            material_list, error_msg = validate_materials(self.materials_input.value)
            if error_msg:
                log.warning(
                    "Material errors on scope submit for user %s (%s)",
                    interaction.user,
                    interaction.user.id,
                )
                await interaction.response.send_message(
                    error_msg + "\n\nPlease run `/changeorder` again.",
                    ephemeral=True,
                )
                return

        key = draft_key(interaction, COMMAND)
        drafts[key] = DraftChangeOrder(
            date_requested=date,
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
        log.info(
            "Change order draft created for user %s in channel %s",
            key[0],
            key[1],
        )


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
        if await check_existing_draft(interaction, drafts, COMMAND, "a change order"):
            return
        await interaction.response.send_modal(ScopeModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(ChangeOrder(bot))
