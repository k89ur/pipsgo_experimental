# NSE Relative Strength Scanner

Minimal Streamlit app for an IBD-style relative strength ranking of NSE equities.

## What it does

1. Loads the NSE equity universe.
2. Downloads up to 2 years of daily data from Yahoo Finance.
3. Calculates 3M, 6M, 9M and 12M returns.
4. Creates a weighted raw RS score:
   - 3M: 40%
   - 6M: 20%
   - 9M: 20%
   - 12M: 20%
5. Converts the score to a 1–99 percentile-style RS Rating.
6. Filters by RS, 52-week high distance and optional MA trend conditions.
7. Exports the result as CSV.

This is an IBD-style approximation. IBD's exact RS Rating methodology is proprietary.

## Run in GitHub Codespaces

Open the repository in a Codespace, then run:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0
```

Codespaces should offer to open/forward port 8501.

## GitHub workflow

```bash
git add .
git commit -m "Initial NSE RS scanner"
git push
```

## Notes

- Yahoo Finance can throttle or temporarily fail requests.
- NSE can occasionally block automated downloads. The app includes `symbols.csv` as a fallback universe.
- For a production-grade scanner, add caching, retry/backoff, a persistent data store and a more reliable market-data provider.
