import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime


class MaterialsModal(discord.ui.Modal, title="Change Order - Materials"):
    """
    A modal that collects all change order fields.
    Materials are entered as one item per line in the format: Name - Quantity
    Example:
        20A Breaker - 3
        12 AWG Wire (250ft) - 2
        Junction Box - 5
    """

    date_requested = discord.ui.TextInput(
        label="Date Requested",
        placeholder="MM/DD/YYYY  (leave blank to use today's date)",
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

    materials = discord.ui.TextInput(
        label="Materials  (Name - Quantity, one per line)",
        placeholder="20A Breaker - 3\n12 AWG Wire (250ft) - 2\nJunction Box - 5",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Resolve date
        raw_date = self.date_requested.value.strip()
        if raw_date:
            date_str = raw_date
        else:
            date_str = datetime.today().strftime("%m/%d/%Y")

        # Parse materials into a clean list
        material_lines = [
            line.strip()
            for line in self.materials.value.strip().splitlines()
            if line.strip()
        ]

        material_list = []
        parse_errors = []

        for line in material_lines:
            if " - " in line:
                parts = line.split(" - ", 1)
                material_list.append((parts[0].strip(), parts[1].strip()))
            else:
                parse_errors.append(line)

        # Warn about any lines that didn't parse correctly
        if parse_errors:
            error_msg = "\n".join(f"• `{e}`" for e in parse_errors)
            await interaction.response.send_message(
                f"⚠️ Some material lines couldn't be parsed (expected `Name - Quantity`):\n{error_msg}\n\n"
                "Please run `/changeorder` again and use the format `Name - Quantity` on each line.",
                ephemeral=True,
            )
            return

        # Build the formatted change order embed
        embed = discord.Embed(
            title="📋 Change Order",
            color=discord.Color.yellow(),
            timestamp=datetime.utcnow(),
        )

        embed.add_field(name="📅 Date Requested", value=date_str, inline=True)
        embed.add_field(
            name="👤 Submitted By",
            value=interaction.user.mention,
            inline=True,
        )
        embed.add_field(
            name="🔧 Scope Added",
            value=self.scope_added.value.strip(),
            inline=False,
        )

        # Format material list
        if material_list:
            materials_formatted = "\n".join(
                f"`{name}` — **{qty}**" for name, qty in material_list
            )
        else:
            materials_formatted = "_No materials listed._"

        embed.add_field(
            name=f"📦 Materials ({len(material_list)} item{'s' if len(material_list) != 1 else ''})",
            value=materials_formatted,
            inline=False,
        )

        embed.set_footer(text="Change Order System")

        await interaction.response.send_message(embed=embed)


class ChangeOrder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="changeorder",
        description="Submit a new change order",
    )
    async def change_order(self, interaction: discord.Interaction):
        await interaction.response.send_modal(MaterialsModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(ChangeOrder(bot))
