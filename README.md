# Calvins Discord Bots 

Making discord bots for my friend Calvin. 

## Local Setup
1. Setup python and virtual env 
2. Run `pip install -r requirements.txt` 
3. Add environment variables by first running `cp .env_template` `.env` and enter your personal token for `DISCORD_TOKEN={}` in the .env (ask Jack if you need a Discord Token)
4. Run `python src/main.py` to start the bot locally
5. Run `pytest` for unit testing
6. Run ` ruff format` and `ruff check --fix` for formatting and lint checks 

## Project Structure
```
├── .github                           # Github settings 
├── src/
│   ├── cogs/                         # individual endpoints
│   ├── helpers/                      # shared helper functions
│   ├── models/                       # data models
│   ├── views/                        # shared views
|   └── main.py                       # entry point
├── tests/
│   └── conftest.py                   # Shared pytest fixtures
├── .env_template                     # copy of .env without values     
├── .gitignore                                            
├── Makefile                     
├── pyproject.toml                    # Project settings 
└── requirements.txt
```
Each subfolder has its own `README.md` which provides an overview and context.

## Commands
| Command | Description |
|---|---|
| `/changeorder` | Submit a change order with multi-step material entry and draft editing |
| `/inspectionreq` | Submit an inspection request |
| `/matorder` | Submit a material order with multi-step material entry and editing |
| `/rfi` | Submit a request for information (RFI) with multi-modal steps and drop-downs |