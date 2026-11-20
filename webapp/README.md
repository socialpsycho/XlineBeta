# XLINE Mini App — standalone platform preview

This is a browser-only prototype of the XLINE digital platform interface. The game modes have been removed. The preview contains a wallet mockup, profile, navigation and digital product catalog.

## Publish with GitHub Pages

1. Open the repository on GitHub.
2. Go to **Settings → Pages**.
3. Under **Build and deployment**, choose **Deploy from a branch**.
4. Select branch **main** and folder **/(root)**, then save.
5. Open the URL shown in GitHub Pages. The root page redirects to `/webapp/`.

## Important limits

- This prototype has no server-side account system or Telegram authentication.
- Displayed wallet values are local demo values and are not connected to the Telegram bot or SQLite.
- No real payments, transfers or withdrawals are implemented in this preview.
- A production Telegram Mini App requires HTTPS hosting, backend validation of Telegram `initData`, and secure server-side storage.
- Legacy database files and historical records are preserved; game functionality has been removed from the running application.
