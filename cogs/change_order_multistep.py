"""
change_order_multistep.py

Multi-step change order flow:
1. /changeorderpro  →  Modal: Date + Scope
2. Bot posts a live "draft" embed + "Add Material" / "Done" buttons
3. "Add Material" opens a small modal: Item Name + Quantity
4. Each submission updates the live draft embed
5. "Done" locks the order and posts the final formatted change order
6. Workers can also "Cancel" to discard a draft

State is held in memory (a dict keyed by user ID). Fine for MVP — if the
bot restarts, in-progress drafts are lost, but completed orders are posted
in the channel as embeds.
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

# ---------------------------------------------------------------------------
# In-memory draft store  { user_id: { date, scope, materials: [(name, qty)] } }
# ---------------------------------------------------------------------------
drafts: dict[int, dict] = {}


# ---------------------------------------------------------------------------
# Helper: build the live draft embed
# ---------------------------------------------------------------------------
def build_draft_embed(user: discord.User | discord.Member, draft: dict) -> discord.Embed:
    embed = discord.Embed(
        title="📋 Change Order Draft",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow(),
    )
    embed.add_field(name="📅 Date Requested", value=draft["date"], inline=True)
    embed.add_field(name="👤 Submitted By", value=user.mention, inline=True)
    embed.add_field(name="🔧 Scope Added", value=draft["scope"], inline=False)

    materials = draft["materials"]
    if materials:
        mat_text = "\n".join(f"`{name}` — **{qty}**" for name, qty in materials)
    else:
        mat_text = "_No materials added yet. Use **Add Material** below._"

    embed.add_field(
        name=f"📦 Materials ({len(materials)} item{'s' if len(materials) != 1 else ''})",
        value=mat_text,
        inline=False,
    )
    embed.set_footer(text="Change Order Draft  •  Use the buttons below to add materials or finish")
    return embed


# ---------------------------------------------------------------------------
# Helper: build the final (locked) embed
# ---------------------------------------------------------------------------
def build_final_embed(user: discord.User | discord.Member, draft: dict) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Change Order — Submitted",
        color=discord.Color.green(),
        timestamp=datetime.utcnow(),
    )
    embed.add_field(name="📅 Date Requested", value=draft["date"], inline=True)
    embed.add_field(name="👤 Submitted By", value=user.mention, inline=True)
    embed.add_field(name="🔧 Scope Added", value=draft["scope"], inline=False)

    materials = draft["materials"]
    if materials:
        mat_text = "\n".join(f"`{name}` — **{qty}**" for name, qty in materials)
    else:
        mat_text = "_No materials listed._"

    embed.add_field(
        name=f"📦 Materials ({len(materials)} item{'s' if len(materials) != 1 else ''})",
        value=mat_text,
        inline=False,
    )
    embed.set_footer(text="Change Order System  •  Submitted")
    return embed


# ---------------------------------------------------------------------------
# Modal 1: Date + Scope  (opens on /changeorderpro)
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
        raw_date = self.date_requested.value.strip()
        date_str = raw_date if raw_date else datetime.today().strftime("%m/%d/%Y")

        # Store draft in memory
        drafts[interaction.user.id] = {
            "date": date_str,
            "scope": self.scope_added.value.strip(),
            "materials": [],
        }

        draft = drafts[interaction.user.id]
        embed = build_draft_embed(interaction.user, draft)
        view = DraftView(interaction.user.id)

        await interaction.response.send_message(
            content="Draft created! Add materials below, then click **Done** when finished.",
            embed=embed,
            view=view,
            ephemeral=False,   # visible to the channel so supervisors can watch
        )


# ---------------------------------------------------------------------------
# Modal 2: Single material entry  (opens on "Add Material" button)
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
        self.message = message  # reference to the draft message so we can edit it

    async def on_submit(self, interaction: discord.Interaction):
        name = self.item_name.value.strip()
        qty = self.quantity.value.strip()

        # Validate quantity is numeric
        try:
            float(qty)  # allow decimals like 1.5 boxes
        except ValueError:
            await interaction.response.send_message(
                f"⚠️ Quantity must be a number (you entered `{qty}`). Please try again.",
                ephemeral=True,
            )
            return

        draft = drafts.get(self.user_id)
        if not draft:
            await interaction.response.send_message(
                "⚠️ Your draft expired. Please run `/changeorderpro` again.",
                ephemeral=True,
            )
            return

        draft["materials"].append((name, qty))

        # Update the live embed in place
        embed = build_draft_embed(interaction.user, draft)
        view = DraftView(self.user_id)

        await interaction.response.defer()
        await self.message.edit(embed=embed, view=view)


# ---------------------------------------------------------------------------
# View: buttons attached to the draft message
# ---------------------------------------------------------------------------
class DraftView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=3600)  # 1 hour timeout
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the original submitter can use these buttons."""
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
                "⚠️ Draft not found. Please run `/changeorderpro` again.",
                ephemeral=True,
            )
            return
        modal = AddMaterialModal(user_id=interaction.user.id, message=interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="↩️ Undo Last", style=discord.ButtonStyle.secondary)
    async def undo_last(self, interaction: discord.Interaction, button: discord.ui.Button):
        draft = drafts.get(interaction.user.id)
        if not draft or not draft["materials"]:
            await interaction.response.send_message(
                "Nothing to undo.",
                ephemeral=True,
            )
            return

        removed = draft["materials"].pop()
        embed = build_draft_embed(interaction.user, draft)
        view = DraftView(interaction.user.id)

        await interaction.response.defer()
        await interaction.message.edit(embed=embed, view=view)

    @discord.ui.button(label="✅ Done", style=discord.ButtonStyle.success)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        draft = drafts.pop(interaction.user.id, None)
        if not draft:
            await interaction.response.send_message(
                "⚠️ Draft not found.",
                ephemeral=True,
            )
            return

        embed = build_final_embed(interaction.user, draft)

        # Disable all buttons on the draft message
        for child in self.children:
            child.disabled = True

        await interaction.response.defer()
        await interaction.message.edit(
            content="✅ Change order submitted!",
            embed=embed,
            view=self,
        )

    @discord.ui.button(label="🗑️ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        drafts.pop(interaction.user.id, None)

        for child in self.children:
            child.disabled = True

        await interaction.response.defer()
        await interaction.message.edit(
            content="🗑️ Change order cancelled.",
            embed=None,
            view=self,
        )


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
        # If user already has an in-progress draft, warn them
        if interaction.user.id in drafts:
            await interaction.response.send_message(
                "⚠️ You already have a change order in progress. "
                "Finish or cancel it before starting a new one.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(ScopeModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(ChangeOrderMultiStep(bot))
