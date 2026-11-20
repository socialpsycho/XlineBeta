# Xline Bot

## Architecture
- `main.py` — startup and router registration only.
- `xlinebot/config.py` — environment configuration.
- `xlinebot/db.py` — SQLite transactions, balances and durable game history.
- `xlinebot/games/` — pure game-layout generation.
- `xlinebot/routers/` — Telegram handlers separated by feature.
- `xlinebot/keyboards.py` and `states.py` — shared UI and FSM definitions.

## Setup
1. Python 3.10+.
2. Install: `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set `BOT_TOKEN`.
4. Start: `python main.py`.

The default SQLite database is `play.db`. If the existing `casino.db` is present and `play.db` does not exist, startup renames the database file automatically to preserve its data. If both files exist, `play.db` is used and the old file is left untouched.

Completed rounds are recorded in `game_history`; Mines and Tower layouts are saved with the result. Active rounds remain in memory and reset on restart.


## Telegram Mini App (free demo)
- The published demo is available at `https://socialpsycho.github.io/XlineBeta/`.
- Set `WEBAPP_URL` to the HTTPS URL in the Amvera environment variables (the default in `xlinebot/config.py` is the GitHub Pages URL).
- The bot exposes `/miniapp` and adds an **🚀 XLINE Mini App** Web App button to the reply keyboard.
- Redeploy/restart the bot after pulling the latest `main` branch.
- This is a standalone front-end demo: XP is local to the browser and is not connected to Telegram identity, SQLite, deposits, withdrawals, Stars, or crypto payments. Do not treat client-side values as trusted account data.
- If a future version adds accounts or server-side data, validate Telegram Web App `initData` on the server before using the Telegram user identity.
