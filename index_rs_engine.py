from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
import json
from typing import Callable, Optional

import numpy as np
import pandas as pd
import requests

# Exact 28 aliases from the supplied Pine Script, mapped to canonical Nifty
# Indices names. Aliases are tried in order because some names have changed
# presentation over time on the Nifty Indices site.
INDEX_UNIVERSE = [
    ("BANKNIFTY", ["NIFTY BANK"]),
    ("CNXAUTO", ["NIFTY AUTO"]),
    ("CNXCONSUMPTION", ["NIFTY INDIA CONSUMPTION"]),
    ("CNXENERGY", ["NIFTY ENERGY"]),
    ("CNXFINANCE", ["NIFTY FINANCIAL SERVICES"]),
    ("CNXFMCG", ["NIFTY FMCG"]),
    ("CNXINFRA", ["NIFTY INFRASTRUCTURE"]),
    ("CNXIT", ["NIFTY IT"]),
    ("CNXMETAL", ["NIFTY METAL"]),
    ("CNXPHARMA", ["NIFTY PHARMA"]),
    ("CNXPSE", ["NIFTY PSE"]),
    ("CNXPSUBANK", ["NIFTY PSU BANK"]),
    ("CNXREALTY", ["NIFTY REALTY"]),
    ("CNXSERVICE", ["NIFTY SERVICES SECTOR"]),
    ("CPSE", ["NIFTY CPSE"]),
    ("NIFTYPVTBANK", ["NIFTY PRIVATE BANK"]),
    ("NIFTY_CAPITAL_MKT", ["NIFTY CAPITAL MARKETS"]),
    ("NIFTY_CEMENT", ["NIFTY CEMENT"]),
    ("NIFTY_CHEMICALS", ["NIFTY CHEMICALS"]),
    ("NIFTY_CONSR_DURBL", ["NIFTY CONSUMER DURABLES", "NIFTY CONSR DURBL"]),
    ("NIFTY_EV", ["NIFTY EV & NEW AGE AUTOMOTIVE", "NIFTY EV AND NEW AGE AUTOMOTIVE"]),
    ("NIFTY_HEALTHCARE", ["NIFTY HEALTHCARE", "NIFTY HEALTHCARE INDEX"]),
    ("NIFTY_IND_DEFENCE", ["NIFTY INDIA DEFENCE"]),
    ("NIFTY_IND_DIGITAL", ["NIFTY INDIA DIGITAL"]),
    ("NIFTY_IND_TOURISM", ["NIFTY INDIA TOURISM"]),
    ("NIFTY_IPO", ["NIFTY IPO"]),
    ("NIFTY_OIL_AND_GAS", ["NIFTY OIL & GAS", "NIFTY OIL AND GAS"]),
    ("NIFTY_TRANS_LOGIS", ["NIFTY TRANSPORTATION & LOGISTICS"]),
]

BENCHMARK_NAMES = ["NIFTY 50"]
API_URL = "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"
REFERER = "https://www.niftyindices.com/reports/historical-data"
HEADERS = {
    "Content-Type": "application/json; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.niftyindices.com",
    "Referer": REFERER,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
}


def _empty_result() -> pd.Series:
    return pd.Series(dtype=float)


def _fetch_one(index_name: str, from_date: str, to_date: str) -> pd.Series:
    """Fetch price-index OHLC from NSE Indices' public historical-data service."""
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        # Bootstrap the site session; current Akamai protection generally permits
        # the API after a normal browser-like visit.
        try:
            session.get(REFERER, timeout=8)
        except requests.RequestException:
            pass

        cinfo = {
            "name": index_name,
            "startDate": from_date,
            "endDate": to_date,
            "indexName": index_name,
        }
        # ASP.NET ScriptService expects cinfo to be a JSON-like string with
        # single quotes, not a nested JSON object.
        payload = {"cinfo": "{" + ",".join(f"'{k}':'{v}'" for k, v in cinfo.items()) + "}"}

        for attempt in range(3):
            try:
                response = session.post(API_URL, json=payload, timeout=35)
                response.raise_for_status()
                body = response.json()
                raw = body.get("d", "[]")
                rows = json.loads(raw) if isinstance(raw, str) else raw
                if not rows:
                    return _empty_result()

                frame = pd.DataFrame(rows)
                if "HistoricalDate" not in frame.columns or "CLOSE" not in frame.columns:
                    return _empty_result()
                frame["Date"] = pd.to_datetime(frame["HistoricalDate"], format="%d %b %Y", errors="coerce")
                frame["Close"] = pd.to_numeric(frame["CLOSE"], errors="coerce")
                frame = frame.dropna(subset=["Date", "Close"]).sort_values("Date")
                if frame.empty:
                    return _empty_result()
                return frame.drop_duplicates("Date").set_index("Date")["Close"].astype(float)
            except (requests.RequestException, ValueError, json.JSONDecodeError):
                if attempt == 2:
                    return _empty_result()
        return _empty_result()
    finally:
        session.close()


def _fetch_aliases(aliases: list[str], from_date: str, to_date: str) -> tuple[str, pd.Series]:
    for name in aliases:
        series = _fetch_one(name, from_date, to_date)
        if not series.empty:
            return name, series
    return aliases[0], _empty_result()


def _pine_score(close: pd.Series, benchmark: pd.Series) -> dict[str, float]:
    """Mirror c[63]/[126]/[189]/[252] from the supplied Pine Script."""
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
        benchmark_return = (float(current_b) / float(old_b) - 1.0) * 100.0
        relative = stock_return - benchmark_return
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
    # 550 calendar days gives enough room for 252 daily NSE trading bars.
    end = date.today()
    start = end - timedelta(days=550)
    from_date = start.strftime("%d-%b-%Y")
    to_date = end.strftime("%d-%b-%Y")

    targets = [("__BENCHMARK__", BENCHMARK_NAMES)] + INDEX_UNIVERSE
    results: dict[str, pd.Series] = {}
    resolved_names: dict[str, str] = {}

    if progress_callback:
        progress_callback(0, len(targets), "Connecting to Nifty Indices")

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_fetch_aliases, aliases, from_date, to_date): key
            for key, aliases in targets
        }
        completed = 0
        for future in as_completed(futures):
            key = futures[future]
            try:
                resolved, series = future.result()
            except Exception:
                resolved, series = "", _empty_result()
            resolved_names[key] = resolved
            results[key] = series
            completed += 1
            if progress_callback:
                progress_callback(completed, len(targets), "Downloading index history")

    benchmark = results.get("__BENCHMARK__", _empty_result())
    if benchmark.empty:
        raise RuntimeError("Nifty Indices historical service did not return NIFTY 50. The data service may be temporarily blocking the Codespace; try Refresh RS once.")

    rows = []
    for alias, aliases in INDEX_UNIVERSE:
        close = results.get(alias, _empty_result())
        resolved = resolved_names.get(alias, aliases[0])
        if close.empty:
            rows.append({
                "INDEX": alias,
                "Nifty Index": resolved,
                "Status": "Data unavailable",
                "Raw RS": np.nan,
            })
            continue
        metrics = _pine_score(close, benchmark)
        rows.append({
            "INDEX": alias,
            "Nifty Index": resolved,
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

    return df, {
        "universe": len(INDEX_UNIVERSE),
        "available": int(df["Raw RS"].notna().sum()),
        "as_of": benchmark.index[-1],
        "source": "Nifty Indices historical price data",
    }
