import discord
from discord.ext import commands
import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

class CalvinBot(commands.Bot):
    async def setup_hook(self):
        await self.load_extension("src.cogs.change_order")
        await self.load_extension("src.cogs.change_order_multistep")
        await self.tree.sync()

intents = discord.Intents.default()
bot = CalvinBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print("Commands registered:")
    print("  /changeorder      — single modal, freeform material list")
    print("  /changeorderpro  — multi-step, add materials one at a time")

bot.run(os.getenv("DISCORD_TOKEN"))
