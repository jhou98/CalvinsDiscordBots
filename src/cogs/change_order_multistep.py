import discord
import logging
from discord import app_commands
from discord.ext import commands
from src.helpers.helpers import resolve_date, discord_timestamp, build_change_order_embed

# In-memory draft store  { user_id: { date, submitted_at, scope, materials } }
drafts: dict[int, dict] = {}
log = logging.getLogger(__name__)

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

    async def on_submit(self, interaction: discord.Interaction):
        try:
            date = resolve_date(self.date_requested.value)
        except ValueError as e:
            log.warning(
                "Date error for user %s, (%d): %s",
                interaction.user, interaction.user.id, e
            )
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        
        drafts[interaction.user.id] = {
            "date": date,
            "submitted_at": discord_timestamp(),
            "scope": self.scope_added.value.strip(),
            "materials": [],
        }
        draft = drafts[interaction.user.id]
        view = DraftView(interaction.user.id)
        embed = _draft_embed(interaction.user, draft)
        await interaction.response.send_message(
            content="Draft created! Add materials below, then click **Done** when finished.",
            embed=embed,
            view=view
        )

        # Store the message reference so on_timeout can edit it
        view.message = await interaction.original_response()


# ---------------------------------------------------------------------------
# Modal 2: Single material entry
# ---------------------------------------------------------------------------
class AddMaterialModal(discord.ui.Modal, title="Add Material"):

    item_name = discord.ui.TextInput(
        label="Item Name",
        placeholder="e.g.  20A Breaker",
        required=True,
        max_length=100,
    )
    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="e.g.  3",
        required=True,
        max_length=20,
    )

    def __init__(self, user_id: int, message: discord.Message):
        super().__init__()
        self.user_id = user_id
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        qty = self.quantity.value.strip()
        try:
            float(qty)
        except ValueError:
            log.warning(
                "Invalid quantity '%s' entered by %s (%d)",
                qty, interaction.user, interaction.user.id
            )
            await interaction.response.send_message(
                f"⚠️ Quantity must be a number (you entered `{qty}`). Please try again.",
                ephemeral=True,
            )
            return

        draft = drafts.get(self.user_id)
        if not draft:
            log.warning(
                "Draft not found for user %s (%d) on material add", 
                interaction.user, interaction.user.id
            )
            await interaction.response.send_message(
                "⚠️ Your draft expired. Please run `/changeorderpro` again.",
                ephemeral=True,
            )
            return

        draft["materials"].append((self.item_name.value.strip(), qty))
        await interaction.response.defer()
        await self.message.edit(
            embed=_draft_embed(interaction.user, draft),
            view=DraftView(self.user_id),
        )


# ---------------------------------------------------------------------------
# Shared embed builders (thin wrappers around the shared util)
# ---------------------------------------------------------------------------
def _draft_embed(user, draft):
    return build_change_order_embed(
        user=user,
        date=draft["date"],
        submitted_at=draft["submitted_at"],
        scope=draft["scope"],
        material_list=draft["materials"],
        title="📋 Change Order Draft",
        color=discord.Color.blue(),
    )

def _final_embed(user, draft):
    return build_change_order_embed(
        user=user,
        date=draft["date"],
        submitted_at=draft["submitted_at"],
        scope=draft["scope"],
        material_list=draft["materials"],
        title="✅ Change Order — Submitted",
        color=discord.Color.green(),
    )


# ---------------------------------------------------------------------------
# View: buttons attached to the draft message
# ---------------------------------------------------------------------------
class DraftView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=3600)
        self.user_id = user_id
        self.message: discord.Message | None = None
    
    async def on_timeout(self):
        """
        Auto clean-up draft on timeout to avoid memory leaks and user lockout
        """
        drafts.pop(self.user_id, None)
        if self.message:
            for child in self.children:
                child.disabled = True
            try:
                await self.message.edit(
                    content="⏱️ Change order expired due to inactivity.",
                    embed=None,
                    view=self,
                )
            except discord.NotFound:
                pass  # Message was deleted — nothing to edit

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "⚠️ Only the person who started this change order can modify it.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="➕ Add Material", style=discord.ButtonStyle.primary)
    async def add_material(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in drafts:
            await interaction.response.send_message(
                "⚠️ Draft not found. Please run `/changeorderpro` again.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            AddMaterialModal(user_id=interaction.user.id, message=interaction.message)
        )

    @discord.ui.button(label="↩️ Undo Last", style=discord.ButtonStyle.secondary)
    async def undo_last(self, interaction: discord.Interaction, button: discord.ui.Button):
        draft = drafts.get(interaction.user.id)
        if not draft or not draft["materials"]:
            await interaction.response.send_message("Nothing to undo.", ephemeral=True)
            return
        draft["materials"].pop()
        await interaction.response.defer()
        await interaction.message.edit(
            embed=_draft_embed(interaction.user, draft),
            view=DraftView(self.user_id),
        )

    @discord.ui.button(label="✅ Done", style=discord.ButtonStyle.success)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        draft = drafts.pop(interaction.user.id, None)
        if not draft:
            await interaction.response.send_message("⚠️ Draft not found.", ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        await interaction.response.defer()
        await interaction.message.edit(
            content="✅ Change order submitted!",
            embed=_final_embed(interaction.user, draft),
            view=self,
        )

    @discord.ui.button(label="🗑️ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        drafts.pop(interaction.user.id, None)
        for child in self.children:
            child.disabled = True
        await interaction.response.defer()
        await interaction.message.edit(content="🗑️ Change order cancelled.", embed=None, view=self)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class ChangeOrderMultiStep(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="changeorderpro",
        description="Submit a change order (add materials one at a time with + button)",
    )
    async def change_order_pro(self, interaction: discord.Interaction):
        if interaction.user.id in drafts:
            await interaction.response.send_message(
                "⚠️ You already have a change order in progress. Finish or cancel it before starting a new one.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(ScopeModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(ChangeOrderMultiStep(bot))