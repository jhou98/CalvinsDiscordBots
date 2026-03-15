# Calvins Discord Bots 

## Setup
1. Setup python and venv 
2. run `pip install requirements.txt` 
3. Add `DISCORD_TOKEN={}` in a .env (ask Jack if you need the Discord Token)
4. Run `python main.py` to start the bot locally

## Project Structure
```
main.py                        # Bot entry point — loads cogs, syncs slash commands
cogs/                          # cog commands
helpers/                       # shared helpers
```
Each subfolder has its own `README.md` which provides an overview and context.

## Commands
| Command | Description |
|---|---|
| `/changeorder` | Submit a change order via a single modal |
| `/changeorderpro` | Submit a change order with multi-step material entry and draft editing |