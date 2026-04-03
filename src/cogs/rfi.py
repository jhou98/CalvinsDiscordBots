"""
/rfi — Request for Information command.

RFI has 7 fields which exceeds Discord's 5-field modal limit, so it uses
two chained modals:
  Step 1 (after impact select): date_requested, requested_by, required_by
  Step 2: questions, issues, proposed_solution

Flow:
  /rfi → ephemeral select (impact level) → Step 1 modal → Step 2 modal → draft embed

To add or rename impact options, edit RFI_IMPACT_OPTIONS below.
"Other" (free-text) is always appended automatically.
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.helpers.helpers import discord_timestamp, resolve_date
from src.models.draft_rfi import DraftRfi
from src.views.draft_view_base import (
    DraftKey,
    SweepMixin,
    draft_key,
    evict,
    is_expired,
    make_draft_view,
    make_select_then_modal,
)

log = logging.getLogger(__name__)
COMMAND = "rfi"

# ---------------------------------------------------------------------------
# ↓ Edit this list to add / rename impact levels.
#   "Other" (free-text) is always appended automatically.
# ---------------------------------------------------------------------------
RFI_IMPACT_OPTIONS: list[str] = [
    "Work stops",
    "Delay to other trades",
    "Minor",
]

drafts: dict[DraftKey, DraftRfi] = {}


# ---------------------------------------------------------------------------
# Embed / plain-text builders
# ---------------------------------------------------------------------------

def _embed(user, draft: DraftRfi, *, title: str, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="📅 Date Requested", value=draft.date_requested, inline=True)
    embed.add_field(name="🕐 Submitted At",   value=draft.submitted_at,   inline=True)
    embed.add_field(name="👤 Requested By",   value=draft.requested_by,   inline=True)
    embed.add_field(name="📆 Required By",    value=draft.required_by,    inline=True)
    embed.add_field(name="⚡ Impact",          value=draft.impact,         inline=True)
    embed.add_field(name="❓ Question",        value=draft.questions,      inline=False)
    embed.add_field(name="⚠️ Issue",           value=draft.issues,         inline=False)
    if draft.proposed_solution:
        embed.add_field(name="💡 Proposed Solution", value=draft.proposed_solution, inline=False)
    embed.set_footer(text="RFI System")
    return embed


def _draft_embed(user, draft: DraftRfi) -> discord.Embed:
    return _embed(user, draft, title="📋 RFI — Draft", color=discord.Color.blue())


def _final_embed(user, draft: DraftRfi) -> discord.Embed:
    return _embed(user, draft, title="📋 RFI — Submitted", color=discord.Color.green())


def _plain_text(user, draft: DraftRfi) -> str:
    lines = [
        "REQUEST FOR INFORMATION (RFI)",
        f"Date Requested: {draft.date_requested}",
        f"Requested By:   {draft.requested_by}",
        f"Required By:    {draft.required_by}",
        f"Impact:         {draft.impact}",
        "",
        "Question:",
        draft.questions,
        "",
        "Issue:",
        draft.issues,
    ]
    if draft.proposed_solution:
        lines += ["", "Proposed Solution:", draft.proposed_solution]
    return "\n".join(lines)


DraftView = make_draft_view(drafts, COMMAND, _draft_embed, _final_embed, _plain_text)


# ---------------------------------------------------------------------------
# Step 2 modal — question details
# Shown after Step 1 completes. Fills in questions, issues, proposed_solution
# on the already-created draft, then posts the draft embed.
# ---------------------------------------------------------------------------

class RfiStep2Modal(discord.ui.Modal, title="RFI — Step 2 of 2"):
    questions = discord.ui.TextInput(
        label="Question (1–2 sentences)",
        placeholder="Clear, specific question...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
    )
    issues = discord.ui.TextInput(
        label="Issue / Background",
        placeholder="Why is this being asked?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
    )
    proposed_solution = discord.ui.TextInput(
        label="Proposed Solution (optional)",
        placeholder="If you have one in mind...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    def __init__(self, key: DraftKey):
        super().__init__()
        self.key = key

    async def on_submit(self, interaction: discord.Interaction):
        draft = drafts.get(self.key)
        if not draft:
            await interaction.response.send_message(
                "⚠️ Draft expired. Please run `/rfi` again.", ephemeral=True
            )
            return
        draft.questions         = self.questions.value.strip()
        draft.issues            = self.issues.value.strip()
        draft.proposed_solution = self.proposed_solution.value.strip()

        view = DraftView(self.key)
        await interaction.response.send_message(
            content="Draft created! Review and click **Done** to submit.",
            embed=_draft_embed(interaction.user, draft),
            view=view,
        )
        msg = await interaction.original_response()
        view.message  = msg
        draft.message = msg


# ---------------------------------------------------------------------------
# Step 1 modals — identifiers + impact
# Shown after the impact select menu. Collects date_requested, requested_by,
# required_by, then chains to Step 2.
#
# Two concrete subclasses:
#   _RfiStep1Modal       → impact came from the select menu (known value)
#   _RfiStep1ModalOther  → "Other" selected; adds a free-text impact field
# ---------------------------------------------------------------------------

class _RfiStep1ModalBase(discord.ui.Modal, title="RFI — Step 1 of 2"):
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
    required_by = discord.ui.TextInput(
        label="Required By",
        placeholder="MM/DD/YYYY",
        required=True,
        max_length=10,
    )

    def __init__(self, impact: str):
        super().__init__()
        self._impact = impact

    async def _create_draft_and_chain(self, interaction: discord.Interaction, impact: str):
        try:
            date_req = resolve_date(self.date_requested.value)
        except ValueError as e:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        try:
            req_by = resolve_date(self.required_by.value)
        except ValueError as e:
            await interaction.response.send_message(
                f"⚠️ Required by date — {e}", ephemeral=True
            )
            return

        key = draft_key(interaction, COMMAND)
        drafts[key] = DraftRfi(
            date_requested=date_req,
            requested_by=self.requested_by.value.strip(),
            required_by=req_by,
            impact=impact,
            submitted_at=discord_timestamp(),
        )
        await interaction.response.send_modal(RfiStep2Modal(key))


class RfiStep1Modal(_RfiStep1ModalBase):
    """Used when a named impact level is selected from the menu."""

    async def on_submit(self, interaction: discord.Interaction):
        await self._create_draft_and_chain(interaction, self._impact)


class RfiStep1ModalOther(_RfiStep1ModalBase):
    """Used when 'Other' is selected — adds a free-text impact field."""

    impact_other = discord.ui.TextInput(
        label="Impact (describe)",
        placeholder="Describe the impact if this isn't answered...",
        required=True,
        max_length=200,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await self._create_draft_and_chain(interaction, self.impact_other.value.strip())


# ---------------------------------------------------------------------------
# Select menu — shown first (ephemeral) so the user picks an impact level
# ---------------------------------------------------------------------------

class RfiImpactSelectView(
    make_select_then_modal(
        RFI_IMPACT_OPTIONS,
        other_label="Other",
        placeholder="Select impact level...",
    )
):
    async def modal_factory(self, value: str) -> discord.ui.Modal:
        if value == "Other":
            return RfiStep1ModalOther(impact=value)
        return RfiStep1Modal(impact=value)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Rfi(commands.Cog, SweepMixin):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._store = drafts
        self._command_name = COMMAND
        self._start_sweep()

    def cog_unload(self):
        self._stop_sweep()

    @app_commands.command(name=COMMAND, description="Submit a Request for Information")
    async def rfi(self, interaction: discord.Interaction):
        key = draft_key(interaction, COMMAND)
        existing = drafts.get(key)
        if existing and is_expired(existing):
            await evict(drafts, key)
        if key in drafts:
            await interaction.response.send_message(
                "⚠️ You already have an RFI in progress in this channel. "
                "Finish or cancel it before starting a new one.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "Select the impact level to continue:",
            view=RfiImpactSelectView(),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Rfi(bot))