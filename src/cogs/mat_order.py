"""
/matorder — Material Order command.

Flow:
  /matorder → Step 1 modal → Continue button → Step 2 modal → draft embed

Step 1 collects order metadata and site contact; Step 2 collects delivery
notes and optional initial materials. This two-step approach keeps each
modal within Discord's 5-field limit after splitting site contact into
separate name and phone fields.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.db.draft_store import DraftStore, register_model
from src.helpers import (
    discord_timestamp,
    format_materials,
    resolve_date,
    validate_materials,
    validate_phone,
)
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

register_model(COMMAND, DraftMatOrder)
drafts: DraftStore = DraftStore.load_from_db(COMMAND)


# ---------------------------------------------------------------------------
# Embed / plain-text builders
# ---------------------------------------------------------------------------


def _embed(user, draft: DraftMatOrder, *, title: str, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="📅 Date Requested", value=draft.date_requested, inline=True)
    embed.add_field(name="🕐 Submitted At", value=draft.submitted_at, inline=True)
    embed.add_field(name="👤 Requested By", value=draft.requested_by, inline=True)
    embed.add_field(name="📆 Required Date", value=draft.required_date, inline=True)
    embed.add_field(
        name="📞 Site Contact",
        value=f"{draft.site_contact_name} — {draft.site_contact_phone}",
        inline=True,
    )
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
        f"Contact Name:  {draft.site_contact_name}",
        f"Contact Phone: {draft.site_contact_phone}",
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
# Step 2 modal — delivery notes and initial materials
# Shown after Step 1 completes. Fills in delivery_notes and optional
# materials on the already-created draft, then posts the draft embed.
# ---------------------------------------------------------------------------


class MatOrderStep2Modal(discord.ui.Modal, title="Material Order — Step 2 of 2"):
    delivery_notes = discord.ui.TextInput(
        label="Delivery Notes (optional)",
        placeholder="Gate code, drop-off location, etc.",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )
    materials_input = discord.ui.TextInput(
        label="Materials  (Name - Quantity, one per line)",
        placeholder="20A Breaker - 3\n12 AWG Wire (250ft) - 2",
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
            log.error(
                "Draft missing on step 2 submit for user %s in channel %s",
                self.key[0],
                self.key[1],
            )
            await interaction.response.send_message(
                "⚠️ Draft expired. Please run `/matorder` again.", ephemeral=True
            )
            return

        draft.delivery_notes = self.delivery_notes.value.strip()

        if self.materials_input.value.strip():
            material_list, error_msg = validate_materials(self.materials_input.value)
            if error_msg:
                log.warning(
                    "Material errors on matorder step 2 for user %s (%s)",
                    interaction.user,
                    interaction.user.id,
                )
                await interaction.response.send_message(
                    error_msg + "\n\nPlease run `/matorder` again.",
                    ephemeral=True,
                )
                # Remove partial draft since step 2 failed
                drafts.pop(self.key, None)
                return
            draft.materials = material_list
        drafts.save(self.key)

        view = DraftView(self.key)
        await interaction.response.send_message(
            content="Draft created! Add materials below, then click **Done** when finished.",
            embed=_draft_embed(interaction.user, draft),
            view=view,
        )
        msg = await interaction.original_response()
        view.message = msg
        draft.message = msg
        log.info("Material order draft created for user %s in channel %s", self.key[0], self.key[1])


# ---------------------------------------------------------------------------
# Step 2 continue button — bridges the modal→modal gap.
# ---------------------------------------------------------------------------


class MatOrderStep2ContinueView(discord.ui.View):
    def __init__(self, key: DraftKey):
        super().__init__(timeout=300)  # 5 min to click Continue
        self.key = key

    @discord.ui.button(label="Continue →", style=discord.ButtonStyle.primary)
    async def continue_to_step2(self, interaction: discord.Interaction, button: discord.ui.Button):
        draft = drafts.get(self.key)
        if not draft:
            log.error(
                "Draft missing on continue click for user %s in channel %s",
                self.key[0],
                self.key[1],
            )
            await interaction.response.send_message(
                "⚠️ Draft expired. Please run `/matorder` again.", ephemeral=True
            )
            return
        for child in self.children:
            child.disabled = True
        await interaction.response.send_modal(MatOrderStep2Modal(self.key))


# ---------------------------------------------------------------------------
# Step 1 modal — order metadata and site contact
# ---------------------------------------------------------------------------


class MatOrderStep1Modal(discord.ui.Modal, title="Material Order — Step 1 of 2"):
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

    async def on_submit(self, interaction: discord.Interaction):
        try:
            date_req = resolve_date(self.date_requested.value)
        except ValueError as e:
            log.warning(
                "Date requested error for user %s (%s) in channel %s: %s",
                interaction.user,
                interaction.user.id,
                interaction.channel_id,
                e,
            )
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        try:
            req_date = resolve_date(self.required_date.value)
        except ValueError as e:
            log.warning(
                "Required date error for user %s (%s) in channel %s: %s",
                interaction.user,
                interaction.user.id,
                interaction.channel_id,
                e,
            )
            await interaction.response.send_message(f"⚠️ Required date — {e}", ephemeral=True)
            return

        phone = validate_phone(self.site_contact_phone.value)
        if phone is None:
            log.warning(
                "Phone validation failed for user %s (%s) in channel %s",
                interaction.user,
                interaction.user.id,
                interaction.channel_id,
            )
            await interaction.response.send_message(
                "⚠️ Invalid phone number. Please include 7–15 digits "
                "(e.g. `555-867-5309`, `(555) 867-5309`).",
                ephemeral=True,
            )
            return

        key = draft_key(interaction, COMMAND)
        drafts[key] = DraftMatOrder(
            date_requested=date_req,
            requested_by=self.requested_by.value.strip(),
            required_date=req_date,
            site_contact_name=self.site_contact_name.value.strip(),
            site_contact_phone=phone,
            submitted_at=discord_timestamp(),
        )
        # Can't send_modal from a modal on_submit — post an ephemeral button instead
        await interaction.response.send_message(
            content="✅ Step 1 saved! Click **Continue →** to add delivery notes and materials.",
            view=MatOrderStep2ContinueView(key),
            ephemeral=True,
        )


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
        await interaction.response.send_modal(MatOrderStep1Modal())


async def setup(bot: commands.Bot):
    await bot.add_cog(MatOrder(bot))
