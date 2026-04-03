import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Setup path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        TimedRotatingFileHandler(
            filename="bot.log",
            when="D",
            interval=1,
            backupCount=7,  # 7 days
        ),
    ],
)
log = logging.getLogger(__name__)


class CalvinBot(commands.Bot):
    async def setup_hook(self):
        try:
            await self.load_extension("src.cogs.change_order")
            await self.load_extension("src.cogs.inspection_req")
            await self.load_extension("src.cogs.mat_order")
            # await self.load_extension("src.cogs.rfi")
            await self.tree.sync()
            log.info("-- Setup hook complete --")
        except Exception:
            log.exception("Failed to load extensions during setup_hook")


intents = discord.Intents.default()
bot = CalvinBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    log.info("Bot ready — logged in as %s", bot.user)
    log.info("Commands synced: /changeorder, /inspectionreq, /matorder, /rfi")


bot.run(os.getenv("DISCORD_TOKEN"))