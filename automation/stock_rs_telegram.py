"""Run the Stock RS page's default after-market scan and send its CSV to Telegram."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

import rs_engine
from fno_stocks import filter_fno_results
from nse_latest_data import _fetch_nse_market_status, install_nse_latest_close
from snapshot_cache import install as install_persistent_snapshot

IST = ZoneInfo("Asia/Kolkata")
DISPLAY_COLUMNS = [
    "Symbol", "Index", "Industry", "LTP", "RS Rating", "3M %", "6M %",
    "9M %", "12M %", "52W High", "From 52W High %", "TradingView", "GoCharting",
]


def confirmed_trading_day(today) -> bool:
    """Use NSE's reported trade date; unknown status is an error, never a scan."""
    if today.weekday() >= 5:
        print(f"Skipping {today}: weekend")
        return False
    state = _fetch_nse_market_status()
    trade_date = pd.to_datetime(state.get("tradeDate"), errors="coerce", dayfirst=True)
    if pd.isna(trade_date):
        raise RuntimeError("NSE did not return a usable Capital Market tradeDate")
    if trade_date.date() != today:
        print(f"Skipping {today}: NSE reports latest trade date {trade_date.date()}")
        return False
    return True


def send_csv(csv_bytes: bytes, today) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendDocument",
        data={"chat_id": chat_id, "caption": f"Stock RS scan · {today.isoformat()}"},
        files={"document": (f"stock_rs_{today.isoformat()}.csv", csv_bytes, "text/csv")},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram rejected the CSV: {payload}")


def main() -> int:
    today = datetime.now(IST).date()
    if not confirmed_trading_day(today):
        return 0
    install_persistent_snapshot(rs_engine)
    install_nse_latest_close(rs_engine)
    # Match the Stock RS page defaults exactly.
    result, stats = rs_engine.run_scan(
        min_rs=80, max_rs=100, near_high_pct=5, min_price=100,
        rising_days=20, use_min_rs=True, use_near_high=True,
        use_min_price=True, use_ma_rising=False, use_minervini=True,
        batch_size=rs_engine.DEFAULT_BATCH_SIZE, snapshot_mode="eod",
    )
    try:
        fno_result = filter_fno_results(result)
        fno_symbols = (
            set(fno_result["Symbol"].astype(str).str.strip().str.upper())
            if fno_result is not None and not fno_result.empty else set()
        )
        stock_result = result.loc[
            ~result["Symbol"].astype(str).str.strip().str.upper().isin(fno_symbols)
        ].copy()
    except Exception:
        # The page falls back to its unpartitioned result if its F&O list is down.
        stock_result = result.copy()
    columns = [column for column in DISPLAY_COLUMNS if column in stock_result.columns]
    csv_bytes = stock_result[columns].to_csv(index=False).encode("utf-8")
    send_csv(csv_bytes, today)
    print(f"Sent {len(stock_result)} Stock RS rows for {today}; scan data date: {stats.get('data_date', 'unknown')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Stock RS automation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
