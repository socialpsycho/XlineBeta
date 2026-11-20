# XLINE Mini App demo

This folder contains a standalone, client-side Mini App prototype.

## Included
- Mines
- Tower
- Rocket
- Blackjack

All rounds are free-play demonstrations. The XP counter is decorative and is not connected to the Telegram bot, SQLite, deposits, withdrawals, Stars, CryptoBot, or any transferable value.

## Preview
Serve this folder over HTTPS with any static hosting provider. Open `index.html` in the browser for a local visual preview; Telegram Mini Apps require an HTTPS URL when attached to a bot.

## Before connecting to Telegram
This prototype has no backend and does not authenticate Telegram users. Do not use it to display or modify real account balances. A production Mini App needs a backend that validates Telegram `initData` server-side and stores only non-purchasable, non-transferable demo progress.

The existing bot remains a separate application. This prototype does not change its handlers, database, payment configuration, or deployment command.
