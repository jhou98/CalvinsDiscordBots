"""
/calvinhelp — Lists all available commands with descriptions.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)

COMMANDS = [
    (
        "/changeorder",
        "Submit a change order with scope and materials.",
        "Opens a form to enter the date, scope of work, and optional materials. "
        "Review your draft, add more materials if needed, then submit.",
    ),
    (
        "/inspectionreq",
        "Submit an inspection request.",
        "Pick an inspection type (Rough-in, Underground, Temporary Power, Final, "
        "Service, or Other), then fill in the inspection date, AM/PM preference, "
        "and site contact info. Review your draft, then submit.",
    ),
    (
        "/matorder",
        "Submit a material order.",
        "Fill in who's requesting, the required date, site contact, delivery notes, "
        "and materials. Review your draft, add more materials if needed, then submit.",
    ),
    (
        "/rfi",
        "Submit a Request for Information.",
        "Pick an impact level (Work stops, Delay to other trades, Minor, or Other), "
        "then enter dates, your question, the issue, and an optional proposed solution. "
        "Review your draft, then submit.",
    ),
]


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="calvinhelp", description="Show all available commands and how to use them"
    )
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Calvin Bot — Commands",
            description="Here are all available commands. Each one guides you through a form to fill out and review before submitting.",
            color=discord.Color.blurple(),
        )
        for name, short, detail in COMMANDS:
            embed.add_field(name=f"{name} — {short}", value=detail, inline=False)
        embed.set_footer(text="Tip: You can only have one active draft per command per channel.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        log.info("Help shown to user %s (%s)", interaction.user, interaction.user.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
