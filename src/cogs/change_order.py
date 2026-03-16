import discord
import logging
from discord import app_commands
from discord.ext import commands
from src.helpers.helpers import resolve_date, discord_timestamp, parse_materials, build_change_order_embed

log = logging.getLogger(__name__)

class MaterialsModal(discord.ui.Modal, title="Change Order"):

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
        material_list, parse_errors = parse_materials(self.materials.value)

        if parse_errors:
            log.warning(
                "Parse errors for user %s (%d): %s",
                interaction.user, interaction.user.id, parse_errors
            )
            error_msg = "\n".join(f"• `{e}`" for e in parse_errors)
            await interaction.response.send_message(
                f"⚠️ Some material lines couldn't be parsed (expected `Name - Quantity`):\n{error_msg}\n\n"
                "Please run `/changeorder` again and use the format `Name - Quantity` on each line.",
                ephemeral=True,
            )
            return

        try:
            date = resolve_date(self.date_requested.value)
        except ValueError as e:
            log.warning(
                "Date error for user %s, (%d): %s",
                interaction.user, interaction.user.id, e
            )
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return

        embed = build_change_order_embed(
            user=interaction.user,
            date=date,
            submitted_at=discord_timestamp(),
            scope=self.scope_added.value.strip(),
            material_list=material_list,
        )

        await interaction.response.send_message(embed=embed)


class ChangeOrder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="changeorder", description="Submit a new change order")
    async def change_order(self, interaction: discord.Interaction):
        log.info("/changeorder called by %s (%d)", interaction.user, interaction.user.id)
        await interaction.response.send_modal(MaterialsModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(ChangeOrder(bot))