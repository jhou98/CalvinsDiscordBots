"""
/inspectionreq — Inspection Request command.

To add or rename inspection types, edit INSPECTION_TYPES below.
"Other" is always appended automatically — no other changes needed.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.helpers import discord_timestamp, resolve_date
from src.models.draft_inspection import DraftInspection
from src.views.draft_view_base import (
    DraftKey,
    SweepMixin,
    check_existing_draft,
    draft_key,
    make_draft_view,
    make_select_then_modal,
)

log = logging.getLogger(__name__)
COMMAND = "inspectionreq"

# ---------------------------------------------------------------------------
# ↓ Edit this list to add / rename inspection types.
#   "Other" (free-text) is always appended automatically.
# ---------------------------------------------------------------------------
INSPECTION_TYPES: list[str] = [
    "Rough-in",
    "Underground",
    "Temporary Power",
    "Final",
    "Service",
]

drafts: dict[DraftKey, DraftInspection] = {}


# ---------------------------------------------------------------------------
# Embed / plain-text builders
# ---------------------------------------------------------------------------


def _embed(user, draft: DraftInspection, *, title: str, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="📅 Date Requested", value=draft.date_requested, inline=True)
    embed.add_field(name="🕐 Submitted At", value=draft.submitted_at, inline=True)
    embed.add_field(name="👤 Submitted By", value=user.mention, inline=True)
    embed.add_field(name="📆 Inspection Date", value=draft.inspection_date, inline=True)
    embed.add_field(name="🔍 Inspection Type", value=draft.inspection_type, inline=True)
    embed.add_field(name="🌅 AM / PM", value=draft.am_pm, inline=True)
    embed.add_field(name="📞 Site Contact", value=draft.site_contact, inline=False)
    embed.set_footer(text="Inspection Request System")
    return embed


def _draft_embed(user, draft: DraftInspection) -> discord.Embed:
    return _embed(user, draft, title="📋 Inspection Request — Draft", color=discord.Color.blue())


def _final_embed(user, draft: DraftInspection) -> discord.Embed:
    return _embed(
        user, draft, title="📋 Inspection Request — Submitted", color=discord.Color.green()
    )


def _plain_text(user, draft: DraftInspection) -> str:
    return "\n".join(
        [
            "INSPECTION REQUEST",
            f"Date Requested:  {draft.date_requested}",
            f"Submitted By:    {user.display_name}",
            f"Inspection Date: {draft.inspection_date}",
            f"Type:            {draft.inspection_type}",
            f"AM / PM:         {draft.am_pm}",
            f"Site Contact:    {draft.site_contact}",
        ]
    )


DraftView = make_draft_view(drafts, COMMAND, _draft_embed, _final_embed, _plain_text)


# ---------------------------------------------------------------------------
# Modals
#
# _InspectionModalBase holds the four shared fields and the draft-creation
# logic. Two concrete subclasses handle the inspection_type differently:
#   - InspectionModal        → type came from the select menu (known value)
#   - InspectionModalOther   → "Other" selected; adds a free-text type field
# ---------------------------------------------------------------------------


class _InspectionModalBase(discord.ui.Modal, title="Inspection Request"):
    inspection_date = discord.ui.TextInput(
        label="Inspection Date",
        placeholder="MM/DD/YYYY",
        required=True,
        max_length=10,
    )
    date_requested = discord.ui.TextInput(
        label="Date Requested",
        placeholder="MM/DD/YYYY  (leave blank for today)",
        required=False,
        max_length=10,
    )
    site_contact = discord.ui.TextInput(
        label="Site Contact",
        placeholder="Name and phone number",
        required=True,
        max_length=200,
    )
    am_pm = discord.ui.TextInput(
        label="AM / PM Preference",
        placeholder="AM  or  PM",
        required=True,
        max_length=10,
    )

    def __init__(self, inspection_type: str):
        super().__init__()
        self._inspection_type = inspection_type

    async def _create_draft(self, interaction: discord.Interaction, inspection_type: str):
        try:
            date_req = resolve_date(self.date_requested.value)
        except ValueError as e:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        try:
            insp_date = resolve_date(self.inspection_date.value)
        except ValueError as e:
            await interaction.response.send_message(f"⚠️ Inspection date — {e}", ephemeral=True)
            return

        key = draft_key(interaction, COMMAND)
        drafts[key] = DraftInspection(
            date_requested=date_req,
            inspection_date=insp_date,
            inspection_type=inspection_type,
            site_contact=self.site_contact.value.strip(),
            am_pm=self.am_pm.value.strip().upper(),
            submitted_at=discord_timestamp(),
        )
        draft = drafts[key]
        view = DraftView(key)
        await interaction.response.send_message(
            content="Draft created! Review and click **Done** to submit.",
            embed=_draft_embed(interaction.user, draft),
            view=view,
        )
        msg = await interaction.original_response()
        view.message = msg
        draft.message = msg


class InspectionModal(_InspectionModalBase):
    """Used when a named inspection type is selected from the menu."""

    async def on_submit(self, interaction: discord.Interaction):
        await self._create_draft(interaction, self._inspection_type)


class InspectionModalOther(_InspectionModalBase):
    """Used when 'Other' is selected — adds a free-text type field."""

    inspection_type_other = discord.ui.TextInput(
        label="Inspection Type (describe)",
        placeholder="Describe the type of inspection...",
        required=True,
        max_length=200,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await self._create_draft(interaction, self.inspection_type_other.value.strip())


# ---------------------------------------------------------------------------
# Select menu — shown first (ephemeral) so the user picks an inspection type
# ---------------------------------------------------------------------------


class InspectionTypeSelectView(
    make_select_then_modal(
        INSPECTION_TYPES,
        other_label="Other",
        placeholder="Select inspection type...",
    )
):
    async def modal_factory(self, value: str) -> discord.ui.Modal:
        if value == "Other":
            return InspectionModalOther(inspection_type=value)
        return InspectionModal(inspection_type=value)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class InspectionReq(commands.Cog, SweepMixin):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._store = drafts
        self._command_name = COMMAND
        self._start_sweep()

    def cog_unload(self):
        self._stop_sweep()

    @app_commands.command(name=COMMAND, description="Submit an inspection request")
    async def inspection_req(self, interaction: discord.Interaction):
        if await check_existing_draft(
            interaction, drafts, COMMAND, "an inspection request"
        ):
            return
        # Ephemeral so the type-picker doesn't clutter the channel
        await interaction.response.send_message(
            "Select the inspection type to continue:",
            view=InspectionTypeSelectView(),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(InspectionReq(bot))
