"""
/matorder — Material Order command.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.helpers import discord_timestamp, format_materials, resolve_date
from src.models.draft_mat_order import DraftMatOrder
from src.views.draft_view_base import (
    DraftKey,
    SweepMixin,
    check_existing_draft,
    draft_key,
    make_draft_view,
)

log = logging.getLogger(__name__)
COMMAND = "matorder"

drafts: dict[DraftKey, DraftMatOrder] = {}


# ---------------------------------------------------------------------------
# Embed / plain-text builders
# ---------------------------------------------------------------------------


def _embed(user, draft: DraftMatOrder, *, title: str, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="📅 Date Requested", value=draft.date_requested, inline=True)
    embed.add_field(name="🕐 Submitted At", value=draft.submitted_at, inline=True)
    embed.add_field(name="👤 Requested By", value=draft.requested_by, inline=True)
    embed.add_field(name="📆 Required Date", value=draft.required_date, inline=True)
    embed.add_field(name="📞 Site Contact", value=draft.site_contact, inline=True)
    if draft.delivery_notes:
        embed.add_field(name="📝 Delivery Notes", value=draft.delivery_notes, inline=False)
    embed.add_field(
        name=f"📦 Materials ({len(draft.materials)} item{'s' if len(draft.materials) != 1 else ''})",
        value=format_materials(draft.materials),
        inline=False,
    )
    embed.set_footer(text="Material Order System")
    return embed


def _draft_embed(user, draft: DraftMatOrder) -> discord.Embed:
    return _embed(user, draft, title="📋 Material Order — Draft", color=discord.Color.blue())


def _final_embed(user, draft: DraftMatOrder) -> discord.Embed:
    return _embed(user, draft, title="📋 Material Order — Submitted", color=discord.Color.green())


def _plain_text(user, draft: DraftMatOrder) -> str:
    lines = [
        "MATERIAL ORDER",
        f"Date Requested: {draft.date_requested}",
        f"Requested By:   {draft.requested_by}",
        f"Required Date:  {draft.required_date}",
        f"Site Contact:   {draft.site_contact}",
    ]
    if draft.delivery_notes:
        lines += ["", "Delivery Notes:", draft.delivery_notes]
    lines += ["", "Materials:"]
    lines += (
        [f"  {n} - {q}" for n, q in draft.materials]
        if draft.materials
        else ["  No materials listed."]
    )
    return "\n".join(lines)


DraftView = make_draft_view(
    drafts, COMMAND, _draft_embed, _final_embed, _plain_text, has_materials=True
)


# ---------------------------------------------------------------------------
# Modal
# ---------------------------------------------------------------------------


class MatOrderModal(discord.ui.Modal, title="Material Order"):
    date_requested = discord.ui.TextInput(
        label="Date Requested",
        placeholder="MM/DD/YYYY  (leave blank for today)",
        required=False,
        max_length=10,
    )
    requested_by = discord.ui.TextInput(
        label="Requested By",
        placeholder="Name of person requesting",
        required=True,
        max_length=100,
    )
    required_date = discord.ui.TextInput(
        label="Required Date",
        placeholder="MM/DD/YYYY",
        required=True,
        max_length=10,
    )
    site_contact = discord.ui.TextInput(
        label="Site Contact w/ Phone",
        placeholder="Jane Smith — 555-867-5309",
        required=True,
        max_length=200,
    )
    delivery_notes = discord.ui.TextInput(
        label="Delivery Notes (optional)",
        placeholder="Gate code, drop-off location, etc.",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            date_req = resolve_date(self.date_requested.value)
        except ValueError as e:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        try:
            req_date = resolve_date(self.required_date.value)
        except ValueError as e:
            await interaction.response.send_message(f"⚠️ Required date — {e}", ephemeral=True)
            return

        key = draft_key(interaction, COMMAND)
        drafts[key] = DraftMatOrder(
            date_requested=date_req,
            requested_by=self.requested_by.value.strip(),
            required_date=req_date,
            site_contact=self.site_contact.value.strip(),
            delivery_notes=self.delivery_notes.value.strip(),
            submitted_at=discord_timestamp(),
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


class MatOrder(commands.Cog, SweepMixin):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._store = drafts
        self._command_name = COMMAND
        self._start_sweep()

    def cog_unload(self):
        self._stop_sweep()

    @app_commands.command(name=COMMAND, description="Submit a material order")
    async def mat_order(self, interaction: discord.Interaction):
        if await check_existing_draft(interaction, drafts, COMMAND, "a material order"):
            return
        await interaction.response.send_modal(MatOrderModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(MatOrder(bot))
