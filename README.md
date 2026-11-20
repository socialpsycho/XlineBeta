# XLINE Platform

## Architecture
- `main.py` — bot startup and router registration.
- `xlinebot/config.py` — environment configuration.
- `xlinebot/db.py` — SQLite storage; legacy records are preserved.
- `xlinebot/routers/` — Telegram handlers for the platform, wallet, support and administration.
- `webapp/` — responsive XLINE Mini App interface.

## Setup
1. Python 3.10+.
2. Install: `pip install -r requirements.txt`.
3. Set `BOT_TOKEN` in Amvera environment variables.
4. Start command: `python main.py`.

The default SQLite database is `play.db`. If the existing `casino.db` is present and `play.db` does not exist, startup renames the database file automatically to preserve its data. If both files exist, `play.db` is used and the old file is left untouched.

## Telegram Mini App
- Browser preview: https://socialpsycho.github.io/XlineBeta/
- Configure `WEBAPP_URL` in Amvera if the address changes.
- The bot exposes `/miniapp` and a single **🚀 Открыть XLINE** reply-keyboard button.
- Current interface sections: Home, Wallet, Profile, History and digital product catalog.
- The game modes and their bot handlers have been removed. Existing database files and historical records are not deleted.
- The current Mini App remains a front-end prototype. Profile and wallet values are not yet connected to Telegram identity or the server database.
- Validate Telegram Web App `initData` on the backend before trusting account identity or adding account-specific features.
