# NIFTY Index Relative Strength

Minimal Streamlit app that reproduces the supplied Pine Script's 28-index IBD-style RS calculation.

## Calculation

- Exact 28-index universe from the supplied script
- NIFTY 50 benchmark
- 63 trading bars: 40%
- 126 trading bars: 20%
- 189 trading bars: 20%
- 252 trading bars: 20%
- Relative performance = index return minus NIFTY 50 return
- RS 1–99 = the supplied Pine percentile/ranking formula

## Data

The app uses NSE historical index data as the primary source rather than guessing Yahoo Finance ticker mappings. Missing NSE series are reported as unavailable; they are never replaced with another instrument.

## Run in GitHub Codespaces

```bash
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Open forwarded port **8501**.

The first page load automatically runs the scan. **Refresh RS** forces a fresh NSE download.

## Daily Stock RS Telegram CSV

The `Daily Stock RS Telegram` GitHub Actions workflow runs the Stock RS EOD scan at 21:00 IST every day. It skips weekends and dates listed as NSE Capital Market trading holidays. It sends the main Stock RS results CSV (not the separate F&O results) to Telegram.

To enable delivery, add the repository Actions secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. The bot must be able to message the target chat. The workflow can also be started manually from the Actions tab.

## Important

This is an IBD-style approximation based on the supplied Pine formula. It is not IBD's proprietary RS Rating.

## Daily Stock RS CSV to Telegram

A GitHub Actions workflow runs only the **Stock RS** after-market scan at **21:00 India time** (`15:30 UTC`). It uses the page's default filters (RS 80–100, within 5% of the 52-week high, minimum price ₹100, Minervini MA trend on, MA rising off), sends the main Stock RS results as a CSV, and excludes the separately displayed F&O rows. Saturdays and Sundays are skipped. On weekdays, it scans only when NSE's Capital Market status reports today's date as the latest trade date; if NSE cannot confirm the date, the job fails without scanning.

To enable delivery after pushing this repository to GitHub:

1. Create a Telegram bot with [@BotFather](https://t.me/BotFather), then start a chat with the bot (or add it to the destination group).
2. In the repository's **Settings → Secrets and variables → Actions**, add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as repository secrets.
3. Ensure Actions are enabled. The `Daily Stock RS Telegram CSV` workflow can be run manually with **Run workflow** to verify setup.

The scheduled run requires the repository to be hosted on GitHub and the workflow to exist on its default branch. GitHub Actions schedules can start a little later than the configured minute during high load. NSE status, market data, and Telegram must be reachable for a successful run. A manual workflow run on a non-trading day also skips based on NSE's current trade date.
