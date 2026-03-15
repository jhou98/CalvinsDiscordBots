import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.load_extension("cogs.change_order")           # /changeorder      (single modal)
    await bot.load_extension("cogs.change_order_multistep") # /changeorderpro  (multi-step + buttons)
    await bot.tree.sync()
    # await bot.tree.sync(guild=discord.Object(id=436728989651042304))  # instant sync with specific server-id
    print(f"Logged in as {bot.user}")
    print("Commands registered:")
    print("  /changeorder      — single modal, freeform material list")
    print("  /changeorderpro  — multi-step, add materials one at a time")

bot.run(os.getenv("DISCORD_TOKEN"))
