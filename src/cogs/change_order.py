import logging
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.helpers.helpers import (
    build_change_order_embed,
    discord_timestamp,
    format_plain_text,
    parse_materials,
    resolve_date,
)
from src.models.draft_change_order import DraftChangeOrder

# In-memory draft store  { (user_id, channel_id): DraftChangeOrder }
# channel_id is unique across Discord so guild_id is redundant
# IDs stored as strings to avoid integer overflow on large snowflakes
drafts: dict[tuple[str, str], DraftChangeOrder] = {}
log = logging.getLogger(__name__)

DRAFT_TTL_SECONDS = 86400  # 1 day
SWEEP_INTERVAL_MINS = 1 * 60  # how often the background task evicts stale drafts


# ---------------------------------------------------------------------------
# Expiry helpers
# ---------------------------------------------------------------------------
def _is_expired(draft: DraftChangeOrder) -> bool:
    """Return True if the draft has exceeded its TTL."""
    age = (datetime.now(UTC) - draft.created_at).total_seconds()
    return age > DRAFT_TTL_SECONDS


async def _evict(draft_key: tuple[str, str]) -> None:
    """
    Remove a draft from the store and edit its Discord message to show it expired.
    Safe to call from both the lazy check and the background sweep.
    """
    draft = drafts.pop(draft_key, None)
    if draft and draft.message:
        try:  # noqa: SIM105
            await draft.message.edit(
                content="⏱️ Change order expired due to inactivity.",
                embed=None,
                view=None,
            )
        except (discord.NotFound, discord.HTTPException):
            pass  # Message deleted or uneditable — nothing to do


# ---------------------------------------------------------------------------
# Key helper
# ---------------------------------------------------------------------------


def _draft_key(interaction: discord.Interaction) -> tuple[str, str]:
    """Unique draft key scoped to (user, channel). channel_id is unique across Discord."""
    return (str(interaction.user.id), str(interaction.channel_id))


# ---------------------------------------------------------------------------
# Modal 1: Date + Scope
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
        placeholder="20A Breaker - 3\n12 AWG Wire (250ft) - 2\nJunction Box - 5",
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

        # Parse and validate initial materials if provided
        material_list: list[tuple[str, str]] = []
        if self.materials_input.value.strip():
            material_list, parse_errors = parse_materials(self.materials_input.value)
            non_numeric = [f"`{name} - {qty}`" for name, qty in material_list if not _is_numeric(qty)]

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
                    "Material parse/validation errors on scope submit for user %s (%s) in channel %s: parse=%s non_numeric=%s",
                    interaction.user,
                    interaction.user.id,
                    interaction.channel_id,
                    parse_errors,
                    non_numeric,
                )
                await interaction.response.send_message(
                    "⚠️ Some material lines couldn't be added:\n\n"
                    + "\n\n".join(error_lines)
                    + "\n\nPlease run `/changeorder` again and use the format `Name - Quantity` with a numeric quantity on each line.",
                    ephemeral=True,
                )
                return

        draft_key = _draft_key(interaction)
        drafts[draft_key] = DraftChangeOrder(
            date=date,
            submitted_at=discord_timestamp(),
            scope=self.scope_added.value.strip(),
            materials=material_list,
        )
        draft = drafts[draft_key]
        view = DraftView(draft_key)
        embed = _draft_embed(interaction.user, draft)
        await interaction.response.send_message(
            content="Draft created! Add materials below, then click **Done** when finished.",
            embed=embed,
            view=view,
        )

        message = await interaction.original_response()
        view.message = message
        draft.message = message

# ---------------------------------------------------------------------------
# Modal 2: Multi-line material entry
# ---------------------------------------------------------------------------
class AddMaterialModal(discord.ui.Modal, title="Add Materials"):
    materials_input = discord.ui.TextInput(
        label="Materials  (Name - Quantity, one per line)",
        placeholder="20A Breaker - 3\n12 AWG Wire (250ft) - 2\nJunction Box - 5",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
    )

    def __init__(self, draft_key: tuple[str, str], message: discord.Message):
        super().__init__()
        self.draft_key = draft_key
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        # Lazy expiry check before doing any work
        draft = drafts.get(self.draft_key)
        if draft and _is_expired(draft):
            log.info(
                "Lazy eviction on material add for user %s in channel %s",
                self.draft_key[0],
                self.draft_key[1],
            )
            await _evict(self.draft_key)
            await interaction.response.send_message(
                "⏱️ Your draft expired. Please run `/changeorder` again.",
                ephemeral=True,
            )
            return

        if not draft:
            log.warning(
                "Draft not found for user %s in channel %s on material add",
                self.draft_key[0],
                self.draft_key[1],
            )
            await interaction.response.send_message(
                "⚠️ Your draft expired. Please run `/changeorder` again.",
                ephemeral=True,
            )
            return

        material_list, parse_errors = parse_materials(self.materials_input.value)

        non_numeric = [f"`{name} - {qty}`" for name, qty in material_list if not _is_numeric(qty)]

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
                "Material parse/validation errors for user %s (%s) in channel %s: parse=%s non_numeric=%s",
                interaction.user,
                interaction.user.id,
                interaction.channel_id,
                parse_errors,
                non_numeric,
            )
            await interaction.response.send_message(
                "⚠️ Some lines couldn't be added:\n\n"
                + "\n\n".join(error_lines)
                + "\n\nPlease use the format `Name - Quantity` with a numeric quantity on each line.",
                ephemeral=True,
            )
            return

        draft.materials.extend(material_list)
        await interaction.response.defer()
        await self.message.edit(
            embed=_draft_embed(interaction.user, draft),
            view=DraftView(self.draft_key),
        )


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Shared embed builders (thin wrappers around the shared util)
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


# ---------------------------------------------------------------------------
# View: shown after a draft is finalised (copy text only, open to anyone)
# ---------------------------------------------------------------------------


class SubmittedView(discord.ui.View):
    """
    Replaces DraftView once a change order is submitted.
    All draft-editing buttons are gone; only Copy Text remains and is open
    to anyone in the channel so teammates can grab the plain-text output.
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
# View: buttons attached to the draft message
# ---------------------------------------------------------------------------


class DraftView(discord.ui.View):
    def __init__(self, draft_key: tuple[str, str]):
        super().__init__(timeout=None)  # TTL managed by created_at + sweep, not discord.py
        self.draft_key = draft_key
        self.message: discord.Message | None = None

    @property
    def user_id(self) -> str:
        return self.draft_key[0]

    async def _check_expired(self, interaction: discord.Interaction) -> bool:
        """
        Lazy expiry guard called at the top of every button callback.
        Returns True if the draft was expired and the interaction has been responded to.
        """
        draft = drafts.get(self.draft_key)
        if draft and _is_expired(draft):
            log.info(
                "Lazy eviction on button press for user %s in channel %s",
                self.draft_key[0],
                self.draft_key[1],
            )
            await _evict(self.draft_key)
            await interaction.response.send_message(
                "⏱️ This change order has expired. Please run `/changeorderpro` again.",
                ephemeral=True,
            )
            return True
        return False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "⚠️ Only the person who started this change order can modify it.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="➕ Add Material", style=discord.ButtonStyle.primary)
    async def add_material(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._check_expired(interaction):
            return
        if self.draft_key not in drafts:
            await interaction.response.send_message(
                "⚠️ Draft not found. Please run `/changeorderpro` again.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            AddMaterialModal(draft_key=self.draft_key, message=interaction.message)
        )

    @discord.ui.button(label="↩️ Undo Last", style=discord.ButtonStyle.secondary)
    async def undo_last(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._check_expired(interaction):
            return
        draft = drafts.get(self.draft_key)
        if not draft or not draft.materials:
            await interaction.response.send_message("Nothing to undo.", ephemeral=True)
            return
        draft.materials.pop()
        await interaction.response.defer()
        await interaction.message.edit(
            embed=_draft_embed(interaction.user, draft),
            view=DraftView(self.draft_key),
        )

    @discord.ui.button(label="✅ Done", style=discord.ButtonStyle.success)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._check_expired(interaction):
            return
        draft = drafts.get(self.draft_key)
        if not draft:
            await interaction.response.send_message("⚠️ Draft not found.", ephemeral=True)
            return
        if not draft.materials:
            await interaction.response.send_message(
                "⚠️ Please add at least one material before submitting. "
                "Use **➕ Add Material** or **🗑️ Cancel** to discard.",
                ephemeral=True,
            )
            return
        drafts.pop(self.draft_key)
        plain_text = format_plain_text(
            user=interaction.user,
            date=draft.date,
            scope=draft.scope,
            material_list=draft.materials,
        )
        await interaction.response.defer()
        await interaction.message.edit(
            content="✅ Change order submitted!",
            embed=_final_embed(interaction.user, draft),
            view=SubmittedView(plain_text),
        )

    @discord.ui.button(label="🗑️ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._check_expired(interaction):
            return
        drafts.pop(self.draft_key, None)
        for child in self.children:
            child.disabled = True
        await interaction.response.defer()
        await interaction.message.edit(content="🗑️ Change order cancelled.", embed=None, view=self)


# ---------------------------------------------------------------------------
# Cog + background sweep
# ---------------------------------------------------------------------------


class ChangeOrder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sweep_expired_drafts.start()

    def cog_unload(self):
        self.sweep_expired_drafts.cancel()

    @tasks.loop(minutes=SWEEP_INTERVAL_MINS)
    async def sweep_expired_drafts(self):
        """
        Background task (runs every SWEEP_INTERVAL_MINS) that evicts stale drafts
        from memory and edits their Discord messages to show the expiry notice.
        Keeps the drafts dict bounded on low-resource hosts.
        """
        expired_keys = [key for key, draft in drafts.items() if _is_expired(draft)]
        if expired_keys:
            log.info(
                "Sweep evicting %d expired draft(s) from channels: %s",
                len(expired_keys),
                [key[1] for key in expired_keys],
            )
        for key in expired_keys:
            await _evict(key)

    @sweep_expired_drafts.before_loop
    async def before_sweep(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="changeorder",
        description="Submit a change order (add materials one at a time with + button)",
    )
    async def change_order(self, interaction: discord.Interaction):
        draft_key = _draft_key(interaction)

        # Lazy expiry on command entry — cleans up before the duplicate check
        existing = drafts.get(draft_key)
        if existing and _is_expired(existing):
            log.info(
                "Lazy eviction on command entry for user %s in channel %s",
                draft_key[0],
                draft_key[1],
            )
            await _evict(draft_key)

        if draft_key in drafts:
            await interaction.response.send_message(
                "⚠️ You already have a change order in progress in this channel. "
                "Finish or cancel it before starting a new one.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(ScopeModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(ChangeOrder(bot))
