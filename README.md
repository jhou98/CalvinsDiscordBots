# Calvins Discord Bots 

## Local Setup
1. Setup python and virtual env 
2. Run `pip install -r requirements.txt` 
3. Add environment variables by first running `cp .env_template` `.env` and enter your personal token for `DISCORD_TOKEN={}` in the .env (ask Jack if you need a Discord Token)
4. Run `python src/main.py` to start the bot locally
5. Run `pytest` for unit testing

## Project Structure
```
├── src/
│   └── cogs/
│       └── change_order.py           # /changeorder 
│   └── helpers/
│       └── helpers.py                # Shared utilities
│   └── models/
│       └── draft_change_order.py     # Data model for draft change orders
|   └── main.py                       # entry point
├── tests/
│   ├── conftest.py                   # Shared pytest fixtures
│   └── cogs/
│       ├── change_order_test.py
│       └── change_order_multistep_test.py
│   └── helpers/
│       └── helpers_test.py            
└── requirements.txt
```
Each subfolder has its own `README.md` which provides an overview and context.

## Commands
| Command | Description |
|---|---|
| `/changeorder` | Submit a change order via a single modal |
| `/changeorderpro` | Submit a change order with multi-step material entry and draft editing |