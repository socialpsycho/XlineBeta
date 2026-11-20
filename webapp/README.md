# XLINE Mini App — standalone demo

This is a browser-only prototype for checking the visual interface and four free-play demonstrations: Mines, Tower, Rocket, and Blackjack.

## Run locally

From the repository root:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/webapp/` in a browser.

## Publish a browser preview with GitHub Pages

1. Open the repository on GitHub.
2. Go to **Settings → Pages**.
3. Under **Build and deployment**, choose **Deploy from a branch**.
4. Select branch **main** and folder **/(root)**, then save.
5. After GitHub Pages finishes publishing, open the URL shown in that section. It redirects to `/webapp/`.

## Important limits

- This prototype has no server, account system, or Telegram authentication.
- XP is a local decorative counter only. It is not connected to the Telegram bot, SQLite, deposits, withdrawals, Telegram Stars, or CryptoBot.
- It does not save progress between devices or browser resets.
- It is not yet a Telegram Mini App. A Telegram launch requires HTTPS hosting, a separate backend that validates Telegram `initData`, and a bot-side launch button.
- Do not connect this demo to money, crypto, Stars, paid credits, wagers, or cash-out functionality.

The existing Telegram bot is separate. This static preview does not change its handlers, payment code, database, or Amvera deployment.
