from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import numpy as np
import pandas as pd
from tvDatafeed import TvDatafeed, Interval

# These are the EXACT 28 TradingView aliases from the supplied Pine Script.
# Using TradingView itself is intentional: it removes the data-vendor mismatch
# that caused the earlier Yahoo/NSE/NiftyIndices implementations to disagree
# with the Pine script.
INDEX_UNIVERSE = [
    ("BANKNIFTY", "BANKNIFTY"),
    ("CNXAUTO", "CNXAUTO"),
    ("CNXCONSUMPTION", "CNXCONSUMPTION"),
    ("CNXENERGY", "CNXENERGY"),
    ("CNXFINANCE", "CNXFINANCE"),
    ("CNXFMCG", "CNXFMCG"),
    ("CNXINFRA", "CNXINFRA"),
    ("CNXIT", "CNXIT"),
    ("CNXMETAL", "CNXMETAL"),
    ("CNXPHARMA", "CNXPHARMA"),
    ("CNXPSE", "CNXPSE"),
    ("CNXPSUBANK", "CNXPSUBANK"),
    ("CNXREALTY", "CNXREALTY"),
    ("CNXSERVICE", "CNXSERVICE"),
    ("CPSE", "CPSE"),
    ("NIFTYPVTBANK", "NIFTYPVTBANK"),
    ("NIFTY_CAPITAL_MKT", "NIFTY_CAPITAL_MKT"),
    ("NIFTY_CEMENT", "NIFTY_CEMENT"),
    ("NIFTY_CHEMICALS", "NIFTY_CHEMICALS"),
    ("NIFTY_CONSR_DURBL", "NIFTY_CONSR_DURBL"),
    ("NIFTY_EV", "NIFTY_EV"),
    ("NIFTY_HEALTHCARE", "NIFTY_HEALTHCARE"),
    ("NIFTY_IND_DEFENCE", "NIFTY_IND_DEFENCE"),
    ("NIFTY_IND_DIGITAL", "NIFTY_IND_DIGITAL"),
    ("NIFTY_IND_TOURISM", "NIFTY_IND_TOURISM"),
    ("NIFTY_IPO", "NIFTY_IPO"),
    ("NIFTY_OIL_AND_GAS", "NIFTY_OIL_AND_GAS"),
    ("NIFTY_TRANS_LOGIS", "NIFTY_TRANS_LOGIS"),
]

BENCHMARK_SYMBOL = "NIFTY"
EXCHANGE = "NSE"
BARS = 500


def _empty_result() -> pd.Series:
    return pd.Series(dtype=float)


def _fetch_tv(symbol: str) -> pd.Series:
    """Fetch daily closes from TradingView without requiring user credentials."""
    try:
        tv = TvDatafeed()
        frame = tv.get_hist(
            symbol=symbol,
            exchange=EXCHANGE,
            interval=Interval.in_daily,
            n_bars=BARS,
            extended_session=False,
        )
        if frame is None or frame.empty or "close" not in frame.columns:
            return _empty_result()

        close = pd.to_numeric(frame["close"], errors="coerce").dropna()
        if close.empty:
            return _empty_result()
        close.index = pd.to_datetime(close.index).tz_localize(None)
        return close.sort_index().astype(float)
    except Exception:
        return _empty_result()


def _pine_score(close: pd.Series, benchmark: pd.Series) -> dict[str, float]:
    """Mirror the supplied Pine code: c[63], c[126], c[189], c[252]."""
    # Pine request.security() is evaluated on the benchmark/chart's daily bars.
    # Align each index to the NIFTY daily calendar and carry the latest value
    # forward for any non-trading day in that index's own series.
    calendar = benchmark.index.sort_values().unique()
    c = close.reindex(calendar).ffill()
    b = benchmark.reindex(calendar).ffill()

    periods = [
        ("3M %", 63, 0.40),
        ("6M %", 126, 0.20),
        ("9M %", 189, 0.20),
        ("12M %", 252, 0.20),
    ]
    result: dict[str, float] = {}
    total = 0.0

    for label, bars, weight in periods:
        if len(c) <= bars or len(b) <= bars:
            return {
                "3M %": np.nan,
                "6M %": np.nan,
                "9M %": np.nan,
                "12M %": np.nan,
                "Raw RS": np.nan,
            }

        current_c, old_c = c.iloc[-1], c.iloc[-bars - 1]
        current_b, old_b = b.iloc[-1], b.iloc[-bars - 1]

        if any(pd.isna(v) for v in (current_c, old_c, current_b, old_b)):
            return {
                "3M %": np.nan,
                "6M %": np.nan,
                "9M %": np.nan,
                "12M %": np.nan,
                "Raw RS": np.nan,
            }

        if old_c == 0 or old_b == 0:
            return {
                "3M %": np.nan,
                "6M %": np.nan,
                "9M %": np.nan,
                "12M %": np.nan,
                "Raw RS": np.nan,
            }

        stock_return = (float(current_c) / float(old_c) - 1.0) * 100.0
        benchmark_return = (float(current_b) / float(old_b) - 1.0) * 100.0
        relative = stock_return - benchmark_return
        result[label] = relative
        total += relative * weight

    result["Raw RS"] = total
    return result


def _rating(value: float, scores: list[float]):
    """Exact rating function from the supplied Pine Script."""
    valid = [x for x in scores if pd.notna(x)]
    if pd.isna(value) or len(valid) <= 1:
        return np.nan

    below = sum(x < value for x in valid)
    percentile = below / (len(valid) - 1.0)
    return int(round(1.0 + percentile * 98.0))


def run_index_scan(progress_callback: Optional[Callable[[int, int, str], None]] = None):
    targets = [("__BENCHMARK__", BENCHMARK_SYMBOL)] + INDEX_UNIVERSE
    results: dict[str, pd.Series] = {}

    if progress_callback:
        progress_callback(0, len(targets), "Connecting to TradingView")

    # Keep concurrency conservative. TradingView can throttle anonymous
    # WebSocket sessions if many connections are opened simultaneously.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_fetch_tv, symbol): key
            for key, symbol in targets
        }
        completed = 0
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception:
                results[key] = _empty_result()
            completed += 1
            if progress_callback:
                progress_callback(completed, len(targets), "Downloading TradingView daily bars")

    benchmark = results.get("__BENCHMARK__", _empty_result())
    if benchmark.empty:
        raise RuntimeError(
            "TradingView did not return NIFTY 50 daily bars. "
            "The anonymous TradingView data session may be temporarily limited; try Refresh RS once."
        )

    rows = []
    for alias, symbol in INDEX_UNIVERSE:
        close = results.get(alias, _empty_result())
        if close.empty:
            rows.append({
                "INDEX": alias,
                "TradingView": f"NSE:{symbol}",
                "Status": "Data unavailable",
                "Raw RS": np.nan,
            })
            continue

        metrics = _pine_score(close, benchmark)
        rows.append({
            "INDEX": alias,
            "TradingView": f"NSE:{symbol}",
            "LTP": float(close.iloc[-1]),
            **metrics,
            "Bars": len(close),
            "Status": "OK" if pd.notna(metrics["Raw RS"]) else "Insufficient history",
        })

    df = pd.DataFrame(rows)
    scores = df["Raw RS"].tolist()
    df["RS 1-99"] = [
        _rating(float(x), scores) if pd.notna(x) else np.nan
        for x in scores
    ]

    df = df.sort_values(
        ["RS 1-99", "Raw RS"],
        ascending=False,
        na_position="last",
    ).reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))

    return df, {
        "universe": len(INDEX_UNIVERSE),
        "available": int(df["Raw RS"].notna().sum()),
        "as_of": benchmark.index[-1],
        "source": "TradingView daily bars (same symbols as Pine)",
    }
