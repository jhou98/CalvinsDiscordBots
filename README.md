# Calvins Discord Bots 

## Setup
1. Setup python and venv 
2. run `pip install requirements.txt` 
3. Run `cp .env_template` `.env` and enter your personal token for DISCORD_TOKEN={}` in the .env (ask Jack if you need the Discord Token)
4. Run `python main.py` to start the bot locally
5. Run `pytest` for unit testing

## Project Structure
```
├── src/
│   └── cogs/
│       ├── change_order.py           # /changeorder (single modal)
│       └── change_order_multistep.py # /changeorderpro (multi-step + buttons)
│   └── helpers/
│       └── helpers.py                # Shared utilities
├── tests/
│   ├── conftest.py                   # Shared pytest fixtures
│   └── cogs/
│       ├── change_order_test.py
│       └── change_order_multistep_test.py
│   └── helpers/
│       └── helpers_test.py            
├── main.py
└── requirements.txt
```
Each subfolder has its own `README.md` which provides an overview and context.

## Commands
| Command | Description |
|---|---|
| `/changeorder` | Submit a change order via a single modal |
| `/changeorderpro` | Submit a change order with multi-step material entry and draft editing |