# XLINE Platform

## Architecture
- \`main.py\` — starts the Telegram bot and the HTTP API.
- \`xlinebot/config.py\` — environment configuration.
- \`xlinebot/db.py\` — existing SQLite storage; legacy records are preserved.
- \`xlinebot/miniapp_api.py\` — authenticated Telegram Mini App API and persistent demo game engine.
- \`xlinebot/routers/\` — Telegram handlers.
- \`webapp/\` — responsive XLINE Mini App interface.

## Setup
1. Python 3.10+.
2. Install: \`pip install -r requirements.txt\`.
3. Set \`BOT_TOKEN\` in the hosting environment.
4. Expose the HTTP service port (the app uses \`PORT\`, falling back to \`8080\`).
5. Start command: \`python main.py\`.

The default SQLite database is \`play.db\`. If the existing \`casino.db\` is present and \`play.db\` does not exist, startup renames the database file automatically to preserve its data. If both files exist, \`play.db\` is used and the old file is left untouched.

## Mini App API deployment
The Mini App static page is hosted separately from the bot, so the API needs a public HTTPS address.
- Set \`MINIAPP_CORS_ORIGIN=https://socialpsycho.github.io\` in the bot host.
- The host must route public HTTPS traffic to the process port configured by \`PORT\` (default \`8080\`).
- In \`webapp/index.html\`, set \`window.XLINE_API_URL = "https://YOUR-PUBLIC-API-HOST";\` before the application script. Do not put the bot token or any secret in the web page.
- The API authenticates each request using Telegram Web App \`initData\` and rejects unsigned, expired, or forged user data.

Available endpoints:
- \`GET /api/me\` — demo points and current active round.
- \`GET /api/history\` — recent demo-game history.
- \`POST /api/game/start\` — start Mines, Tower, Rocket, Slots, or Blackjack.
- \`POST /api/game/action\` — perform a game action.
- \`POST /api/game/cancel\` — surrender an active round.

## Demo game mode
- Every player receives a separate starting balance of 1,000 virtual points.
- Bets are integer virtual points; no deposits, withdrawals, crypto payments, cash prizes, or conversion to money are enabled.
- Demo points are stored in separate \`miniapp_demo_*\` tables. Existing monetary balances, withdrawals, and transaction history are not used or modified by the demo games.
- Game state is stored server-side in SQLite, so active rounds survive a bot process restart.
- Mines retains the 5×5 board, 5–24 mine selection, safe-cell probability multiplier, and cashout.
- Tower retains all five original difficulty layouts, floor counts, bomb counts, and multiplier formula.
- Rocket retains the original crash-point distribution and +0.12 multiplier progression per second.
- Slots retains the original symbols, weighted random selection, and payout table.
- Blackjack retains the four-deck shoe, ace scoring, dealer draws below 17, and original 2×/2.5×/push payouts.
- Results and random game state are generated on the server; hidden mines, bombs, and the crash point are not returned while a round is active.

## Telegram Mini App
- Browser preview: https://socialpsycho.github.io/XlineBeta/
- Configure \`WEBAPP_URL\` in the hosting environment if the Mini App URL changes.
- Open the bot and use \`/miniapp\` to launch the Mini App.
