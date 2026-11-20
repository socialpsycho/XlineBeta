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
