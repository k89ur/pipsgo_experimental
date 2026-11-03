from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

IST = ZoneInfo("Asia/Kolkata")
NSE_HOME = "https://www.nseindia.com/"
NSE_HOLIDAY_URL = "https://www.nseindia.com/api/holiday-master"
DISPLAY_COLUMNS = [
    "Symbol",
    "Index",
    "Industry",
    "LTP",
    "RS Rating",
    "3M %",
    "6M %",
    "9M %",
    "12M %",
    "52W High",
    "From 52W High %",
    "TradingView",
    "GoCharting",
]


def fetch_nse_holidays(year: int) -> set[date]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,*/*",
            "Referer": NSE_HOME,
        }
    )
    session.get(NSE_HOME, timeout=10)
    response = session.get(NSE_HOLIDAY_URL, params={"type": "trading"}, timeout=20)
    response.raise_for_status()
    holidays = response.json().get("CM")
    if not isinstance(holidays, list):
        raise RuntimeError("NSE trading holiday calendar has an unexpected format")

    result = set()
    for holiday in holidays:
        value = holiday.get("tradingDate") or holiday.get("date")
        parsed = None
        for date_format in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(str(value), date_format).date()
                break
            except ValueError:
                continue
        if parsed is None:
            raise RuntimeError(f"NSE holiday date could not be parsed: {value!r}")
        if parsed.year == year:
            result.add(parsed)
    return result


def is_nse_trading_day(day: date, holiday_fetcher=fetch_nse_holidays) -> bool:
    if day.weekday() >= 5:
        return False
    return day not in holiday_fetcher(day.year)


def stock_results_csv(data: pd.DataFrame) -> bytes:
    columns = [column for column in DISPLAY_COLUMNS if column in data.columns]
    output = data[columns].copy()
    output.insert(0, "S.No", range(1, len(output) + 1))
    return output.to_csv(index=False).encode("utf-8")


def run_stock_rs_scan() -> tuple[pd.DataFrame, dict]:
    import rs_engine
    from fno_stocks import filter_fno_results
    from nse_latest_data import install_nse_latest_close
    from snapshot_cache import install as install_persistent_snapshot

    install_persistent_snapshot(rs_engine)
    install_nse_latest_close(rs_engine)
    scan_data, stats = rs_engine.run_scan(
        min_rs=80,
        max_rs=100,
        near_high_pct=5,
        min_price=100.0,
        use_min_rs=True,
        use_near_high=True,
        use_min_price=True,
        use_minervini=True,
        use_ma_rising=False,
        rising_days=20,
        batch_size=rs_engine.DEFAULT_BATCH_SIZE,
        snapshot_mode="eod",
    )
    try:
        fno_data = filter_fno_results(scan_data)
        fno_symbols = (
            set(fno_data["Symbol"].astype(str).str.strip().str.upper())
            if fno_data is not None and not fno_data.empty
            else set()
        )
        stock_data = scan_data.loc[
            ~scan_data["Symbol"].astype(str).str.strip().str.upper().isin(fno_symbols)
        ].copy()
    except Exception:
        stock_data = scan_data.copy()
    return stock_data, stats


def send_telegram_document(token: str, chat_id: str, content: bytes, caption: str) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendDocument",
        data={"chat_id": chat_id, "caption": caption},
        files={"document": ("nse_stock_rs_scan.csv", content, "text/csv")},
        timeout=60,
    )
    response.raise_for_status()
    if not response.json().get("ok"):
        raise RuntimeError("Telegram did not accept the Stock RS CSV")


def main() -> int:
    now = datetime.now(IST)
    if not is_nse_trading_day(now.date()):
        print(f"Skipping Stock RS scan: {now.date()} is not an NSE trading day.")
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured")

    results, stats = run_stock_rs_scan()
    caption = f"NSE Stock RS Scan - {stats.get('data_date', now.date().isoformat())} - {len(results)} stocks"
    send_telegram_document(token, chat_id, stock_results_csv(results), caption)
    print(f"Sent {len(results)} Stock RS results to Telegram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
