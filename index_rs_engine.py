from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Callable, Optional
import numpy as np
import pandas as pd
import requests

# Exact 28 aliases from the supplied Pine Script.
# The values are the actual NSE index names used by NSE's historical-index endpoint.
INDEX_UNIVERSE = [
    ("BANKNIFTY", "NIFTY BANK"),
    ("CNXAUTO", "NIFTY AUTO"),
    ("CNXCONSUMPTION", "NIFTY INDIA CONSUMPTION"),
    ("CNXENERGY", "NIFTY ENERGY"),
    ("CNXFINANCE", "NIFTY FINANCIAL SERVICES"),
    ("CNXFMCG", "NIFTY FMCG"),
    ("CNXINFRA", "NIFTY INFRASTRUCTURE"),
    ("CNXIT", "NIFTY IT"),
    ("CNXMETAL", "NIFTY METAL"),
    ("CNXPHARMA", "NIFTY PHARMA"),
    ("CNXPSE", "NIFTY PSE"),
    ("CNXPSUBANK", "NIFTY PSU BANK"),
    ("CNXREALTY", "NIFTY REALTY"),
    ("CNXSERVICE", "NIFTY SERVICES SECTOR"),
    ("CPSE", "NIFTY CPSE"),
    ("NIFTYPVTBANK", "NIFTY PRIVATE BANK"),
    ("NIFTY_CAPITAL_MKT", "NIFTY CAPITAL MARKETS"),
    ("NIFTY_CEMENT", "NIFTY CEMENT"),
    ("NIFTY_CHEMICALS", "NIFTY CHEMICALS"),
    ("NIFTY_CONSR_DURBL", "NIFTY CONSUMER DURABLES"),
    ("NIFTY_EV", "NIFTY EV & NEW AGE AUTOMOTIVE"),
    ("NIFTY_HEALTHCARE", "NIFTY HEALTHCARE INDEX"),
    ("NIFTY_IND_DEFENCE", "NIFTY INDIA DEFENCE"),
    ("NIFTY_IND_DIGITAL", "NIFTY INDIA DIGITAL"),
    ("NIFTY_IND_TOURISM", "NIFTY INDIA TOURISM"),
    ("NIFTY_IPO", "NIFTY IPO"),
    ("NIFTY_OIL_AND_GAS", "NIFTY OIL & GAS"),
    ("NIFTY_TRANS_LOGIS", "NIFTY TRANSPORTATION & LOGISTICS"),
]

BENCHMARK = "NIFTY 50"
BASE_URL = "https://www.nseindia.com/api/historical/indicesHistory"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}


def _fetch_nse(index_name: str, from_date: str, to_date: str) -> pd.Series:
    """Fetch daily NSE index closes. NSE requires a homepage session before the API call."""
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get("https://www.nseindia.com/", timeout=10)
        r = session.get(
            BASE_URL,
            params={"indexType": index_name, "from": from_date, "to": to_date},
            timeout=20,
        )
        if r.status_code == 401:
            session.get("https://www.nseindia.com/", timeout=10)
            r = session.get(
                BASE_URL,
                params={"indexType": index_name, "from": from_date, "to": to_date},
                timeout=20,
            )
        r.raise_for_status()
        payload = r.json()
        records = payload.get("data", {}).get("indexCloseOnlineRecords", [])
        if not records:
            return pd.Series(dtype=float)
        frame = pd.DataFrame(records)
        date_col = "EOD_TIMESTAMP"
        close_col = "EOD_CLOSE_INDEX_VAL"
        if date_col not in frame or close_col not in frame:
            return pd.Series(dtype=float)
        frame["Date"] = pd.to_datetime(frame[date_col], format="%d-%b-%Y", errors="coerce")
        frame["Close"] = pd.to_numeric(frame[close_col], errors="coerce")
        frame = frame.dropna(subset=["Date", "Close"]).sort_values("Date")
        return frame.drop_duplicates("Date").set_index("Date")["Close"].astype(float)
    finally:
        session.close()


def _pine_score(close: pd.Series, benchmark: pd.Series) -> dict[str, float]:
    """Mirror the supplied Pine script's daily c[63]/[126]/[189]/[252] logic."""
    calendar = benchmark.index.sort_values().unique()
    c = close.reindex(calendar).ffill()
    b = benchmark.reindex(calendar).ffill()
    periods = [("3M %", 63, 0.40), ("6M %", 126, 0.20), ("9M %", 189, 0.20), ("12M %", 252, 0.20)]
    result: dict[str, float] = {}
    total = 0.0
    for label, bars, weight in periods:
        if len(c) <= bars or len(b) <= bars:
            return {"3M %": np.nan, "6M %": np.nan, "9M %": np.nan, "12M %": np.nan, "Raw RS": np.nan}
        current_c, old_c = c.iloc[-1], c.iloc[-bars - 1]
        current_b, old_b = b.iloc[-1], b.iloc[-bars - 1]
        if any(pd.isna(v) for v in (current_c, old_c, current_b, old_b)) or old_c == 0 or old_b == 0:
            return {"3M %": np.nan, "6M %": np.nan, "9M %": np.nan, "12M %": np.nan, "Raw RS": np.nan}
        stock_return = (float(current_c) / float(old_c) - 1.0) * 100.0
        bench_return = (float(current_b) / float(old_b) - 1.0) * 100.0
        relative = stock_return - bench_return
        result[label] = relative
        total += relative * weight
    result["Raw RS"] = total
    return result


def _rating(value: float, scores: list[float]):
    valid = [x for x in scores if pd.notna(x)]
    if pd.isna(value) or len(valid) <= 1:
        return np.nan
    below = sum(x < value for x in valid)
    percentile = below / (len(valid) - 1.0)
    return int(round(1.0 + percentile * 98.0))


def run_index_scan(progress_callback: Optional[Callable[[int, int, str], None]] = None):
    # 550 calendar days comfortably covers 252 NSE trading bars plus holidays.
    end = date.today()
    start = end - timedelta(days=550)
    from_date, to_date = start.strftime("%d-%m-%Y"), end.strftime("%d-%m-%Y")

    targets = [("__BENCHMARK__", BENCHMARK)] + INDEX_UNIVERSE
    results: dict[str, pd.Series] = {}
    completed = 0
    total_targets = len(targets)

    if progress_callback:
        progress_callback(0, total_targets, "Connecting to NSE")

    # Limited concurrency keeps the scan fast without hammering NSE.
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_fetch_nse, nse_name, from_date, to_date): key for key, nse_name in targets}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception:
                results[key] = pd.Series(dtype=float)
            completed += 1
            if progress_callback:
                progress_callback(completed, total_targets, "Downloading NSE index history")

    benchmark = results.get("__BENCHMARK__", pd.Series(dtype=float))
    if benchmark.empty:
        raise RuntimeError("NSE did not return NIFTY 50 historical data. Try again in a few seconds.")

    rows = []
    for alias, nse_name in INDEX_UNIVERSE:
        close = results.get(alias, pd.Series(dtype=float))
        if close.empty:
            rows.append({"INDEX": alias, "NSE Index": nse_name, "Status": "Data unavailable", "Raw RS": np.nan})
            continue
        metrics = _pine_score(close, benchmark)
        rows.append({
            "INDEX": alias,
            "NSE Index": nse_name,
            "LTP": float(close.iloc[-1]),
            **metrics,
            "Bars": len(close),
            "Status": "OK" if pd.notna(metrics["Raw RS"]) else "Insufficient history",
        })

    df = pd.DataFrame(rows)
    scores = df["Raw RS"].tolist()
    df["RS 1-99"] = [_rating(float(x), scores) if pd.notna(x) else np.nan for x in scores]
    df = df.sort_values(["RS 1-99", "Raw RS"], ascending=False, na_position="last").reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))

    stats = {
        "universe": len(INDEX_UNIVERSE),
        "available": int(df["Raw RS"].notna().sum()),
        "as_of": benchmark.index[-1],
        "source": "NSE historical index data",
    }
    return df, stats
