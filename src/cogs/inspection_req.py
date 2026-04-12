"""
/inspectionreq — Inspection Request command.

Flow:
  /inspectionreq → ephemeral select (type) → Step 1 modal → Continue button → Step 2 modal → draft embed

Step 1 collects inspection details; Step 2 collects site contact info.
This two-step approach keeps each modal within Discord's 5-field limit
after splitting site contact into separate name and phone fields.

To add or rename inspection types, edit INSPECTION_TYPES below.
"Other" is always appended automatically — no other changes needed.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.helpers import discord_timestamp, resolve_date, validate_phone
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
    embed.add_field(
        name="📞 Site Contact",
        value=f"{draft.site_contact_name} — {draft.site_contact_phone}",
        inline=False,
    )
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
            f"Site Contact:    {draft.site_contact_name} — {draft.site_contact_phone}",
        ]
    )


# ---------------------------------------------------------------------------
# Edit modal — allows editing draft fields after creation.
# Editable: inspection_date, site_contact_name, site_contact_phone, am_pm
# Non-editable: date_requested, inspection_type
# ---------------------------------------------------------------------------


class EditInspectionModal(discord.ui.Modal, title="Edit Inspection Request"):
    inspection_date = discord.ui.TextInput(
        label="Inspection Date",
        placeholder="MM/DD/YYYY",
        required=True,
        max_length=10,
    )
    site_contact_name = discord.ui.TextInput(
        label="Site Contact Name",
        placeholder="Jane Smith",
        required=True,
        max_length=100,
    )
    site_contact_phone = discord.ui.TextInput(
        label="Site Contact Phone",
        placeholder="555-867-5309",
        required=True,
        max_length=30,
    )
    am_pm = discord.ui.TextInput(
        label="AM / PM Preference",
        placeholder="AM  or  PM",
        required=True,
        max_length=10,
    )

    def __init__(self, key, store, draft_embed_fn, view_cls):
        super().__init__()
        self.key = key
        self.store = store
        self.draft_embed_fn = draft_embed_fn
        self.view_cls = view_cls
        # Pre-fill with current values
        draft = store[key]
        self.inspection_date.default = draft.inspection_date
        self.site_contact_name.default = draft.site_contact_name
        self.site_contact_phone.default = draft.site_contact_phone
        self.am_pm.default = draft.am_pm

    async def on_submit(self, interaction: discord.Interaction):
        draft = self.store.get(self.key)
        if not draft:
            await interaction.response.send_message(
                "⚠️ Draft expired. Please run `/inspectionreq` again.", ephemeral=True
            )
            return

        try:
            insp_date = resolve_date(self.inspection_date.value)
        except ValueError as e:
            await interaction.response.send_message(
                f"⚠️ Inspection date — {e}", ephemeral=True
            )
            return

        phone = validate_phone(self.site_contact_phone.value)
        if phone is None:
            await interaction.response.send_message(
                "⚠️ Invalid phone number. Please include 7–15 digits "
                "(e.g. `555-867-5309`, `(555) 867-5309`).",
                ephemeral=True,
            )
            return

        draft.inspection_date = insp_date
        draft.site_contact_name = self.site_contact_name.value.strip()
        draft.site_contact_phone = phone
        draft.am_pm = self.am_pm.value.strip().upper()

        await interaction.response.defer()
        await interaction.message.edit(
            embed=self.draft_embed_fn(interaction.user, draft),
            view=self.view_cls(self.key),
        )


DraftView = make_draft_view(
    drafts, COMMAND, _draft_embed, _final_embed, _plain_text,
    edit_modal_factory=EditInspectionModal,
)


# ---------------------------------------------------------------------------
# Step 2 modal — site contact info
# Shown after Step 1 completes. Fills in site_contact_name and
# site_contact_phone on the already-created draft, then posts the draft embed.
# ---------------------------------------------------------------------------


class InspectionStep2Modal(discord.ui.Modal, title="Inspection Request — Contact"):
    site_contact_name = discord.ui.TextInput(
        label="Site Contact Name",
        placeholder="Jane Smith",
        required=True,
        max_length=100,
    )
    site_contact_phone = discord.ui.TextInput(
        label="Site Contact Phone",
        placeholder="555-867-5309",
        required=True,
        max_length=30,
    )

    def __init__(self, key: DraftKey):
        super().__init__()
        self.key = key

    async def on_submit(self, interaction: discord.Interaction):
        draft = drafts.get(self.key)
        if not draft:
            await interaction.response.send_message(
                "⚠️ Draft expired. Please run `/inspectionreq` again.", ephemeral=True
            )
            return

        phone = validate_phone(self.site_contact_phone.value)
        if phone is None:
            await interaction.response.send_message(
                "⚠️ Invalid phone number. Please include 7–15 digits "
                "(e.g. `555-867-5309`, `(555) 867-5309`).",
                ephemeral=True,
            )
            return

        draft.site_contact_name = self.site_contact_name.value.strip()
        draft.site_contact_phone = phone

        view = DraftView(self.key)
        await interaction.response.send_message(
            content="Draft created! Review and click **Done** to submit.",
            embed=_draft_embed(interaction.user, draft),
            view=view,
        )
        msg = await interaction.original_response()
        view.message = msg
        draft.message = msg


# ---------------------------------------------------------------------------
# Step 2 continue button — bridges the modal→modal gap.
# Discord forbids responding to a modal submission with another modal, so
# Step 1 posts an ephemeral "Continue" button instead.
# ---------------------------------------------------------------------------


class InspectionStep2ContinueView(discord.ui.View):
    def __init__(self, key: DraftKey):
        super().__init__(timeout=300)  # 5 min to click Continue
        self.key = key

    @discord.ui.button(label="Continue →", style=discord.ButtonStyle.primary)
    async def continue_to_step2(self, interaction: discord.Interaction, button: discord.ui.Button):
        draft = drafts.get(self.key)
        if not draft:
            await interaction.response.send_message(
                "⚠️ Draft expired. Please run `/inspectionreq` again.", ephemeral=True
            )
            return
        for child in self.children:
            child.disabled = True
        await interaction.response.send_modal(InspectionStep2Modal(self.key))


# ---------------------------------------------------------------------------
# Step 1 modals — inspection details
#
# _InspectionStep1Base holds the three shared fields and the partial-draft
# creation logic. Two concrete subclasses handle the inspection_type:
#   - InspectionStep1Modal      → type came from the select menu (known value)
#   - InspectionStep1ModalOther → "Other" selected; adds a free-text type field
# ---------------------------------------------------------------------------


class _InspectionStep1Base(discord.ui.Modal, title="Inspection Request — Step 1 of 2"):
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
    am_pm = discord.ui.TextInput(
        label="AM / PM Preference",
        placeholder="AM  or  PM",
        required=True,
        max_length=10,
    )

    def __init__(self, inspection_type: str):
        super().__init__()
        self._inspection_type = inspection_type

    async def _create_draft_and_continue(
        self, interaction: discord.Interaction, inspection_type: str
    ):
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
            am_pm=self.am_pm.value.strip().upper(),
            submitted_at=discord_timestamp(),
        )
        # Can't send_modal from a modal on_submit — post an ephemeral button instead
        await interaction.response.send_message(
            content="✅ Step 1 saved! Click **Continue →** to add site contact details.",
            view=InspectionStep2ContinueView(key),
            ephemeral=True,
        )


class InspectionStep1Modal(_InspectionStep1Base):
    """Used when a named inspection type is selected from the menu."""

    async def on_submit(self, interaction: discord.Interaction):
        await self._create_draft_and_continue(interaction, self._inspection_type)


class InspectionStep1ModalOther(_InspectionStep1Base):
    """Used when 'Other' is selected — adds a free-text type field."""

    inspection_type_other = discord.ui.TextInput(
        label="Inspection Type (describe)",
        placeholder="Describe the type of inspection...",
        required=True,
        max_length=200,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await self._create_draft_and_continue(
            interaction, self.inspection_type_other.value.strip()
        )


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
            return InspectionStep1ModalOther(inspection_type=value)
        return InspectionStep1Modal(inspection_type=value)


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
