from __future__ import annotations

from typing import Callable, Optional
import numpy as np
import pandas as pd
import yfinance as yf

# Exact 28-name universe from the supplied Pine Script.
# Yahoo symbols are only a transport layer; missing/invalid symbols are never
# replaced with unrelated instruments.
INDEX_UNIVERSE = [
    ("BANKNIFTY", "^NSEBANK"),
    ("CNXAUTO", "^CNXAUTO"),
    ("CNXCONSUMPTION", "^CNXCONSUMPTION"),
    ("CNXENERGY", "^CNXENERGY"),
    ("CNXFINANCE", "^CNXFINANCE"),
    ("CNXFMCG", "^CNXFMCG"),
    ("CNXINFRA", "^CNXINFRA"),
    ("CNXIT", "^CNXIT"),
    ("CNXMETAL", "^CNXMETAL"),
    ("CNXPHARMA", "^CNXPHARMA"),
    ("CNXPSE", "^CNXPSE"),
    ("CNXPSUBANK", "^CNXPSUBANK"),
    ("CNXREALTY", "^CNXREALTY"),
    ("CNXSERVICE", "^CNXSERVICE"),
    ("CPSE", "^CNXCPSE"),
    ("NIFTYPVTBANK", "^NIFTYPVTBANK"),
    ("NIFTY_CAPITAL_MKT", "NIFTY_CAPITAL_MKT.NS"),
    ("NIFTY_CEMENT", "NIFTY_CEMENT.NS"),
    ("NIFTY_CHEMICALS", "NIFTY_CHEMICALS.NS"),
    ("NIFTY_CONSR_DURBL", "NIFTY_CONSR_DURBL.NS"),
    ("NIFTY_EV", "NIFTY_EV.NS"),
    ("NIFTY_HEALTHCARE", "NIFTY_HEALTHCARE.NS"),
    ("NIFTY_IND_DEFENCE", "NIFTY_IND_DEFENCE.NS"),
    ("NIFTY_IND_DIGITAL", "NIFTY_IND_DIGITAL.NS"),
    ("NIFTY_IND_TOURISM", "NIFTY_IND_TOURISM.NS"),
    ("NIFTY_IPO", "NIFTY_IPO.NS"),
    ("NIFTY_OIL_AND_GAS", "NIFTY_OIL_AND_GAS.NS"),
    ("NIFTY_TRANS_LOGIS", "NIFTY_TRANS_LOGIS.NS"),
]
BENCHMARK = "^NSEI"


def _download(tickers: list[str]) -> dict[str, pd.Series]:
    raw = yf.download(
        tickers=tickers,
        period="2y",
        interval="1d",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    if raw is None or raw.empty:
        return {}
    out: dict[str, pd.Series] = {}
    if isinstance(raw.columns, pd.MultiIndex):
        l0 = set(raw.columns.get_level_values(0))
        l1 = set(raw.columns.get_level_values(1))
        for ticker in tickers:
            try:
                if ticker in l0:
                    x = raw[ticker]["Close"]
                elif ticker in l1:
                    x = raw.xs(ticker, axis=1, level=1)["Close"]
                else:
                    continue
                x = pd.to_numeric(x, errors="coerce").dropna()
                if not x.empty:
                    x.index = pd.to_datetime(x.index).tz_localize(None)
                    out[ticker] = x.sort_index()
            except Exception:
                continue
    else:
        x = pd.to_numeric(raw["Close"], errors="coerce").dropna()
        if tickers and not x.empty:
            x.index = pd.to_datetime(x.index).tz_localize(None)
            out[tickers[0]] = x.sort_index()
    return out


def _pine_score(close: pd.Series, benchmark: pd.Series) -> dict[str, float]:
    """Replicate c[63]/[126]/[189]/[252] on a common daily trading calendar."""
    # Pine request.security() series are evaluated on the chart's daily bars.
    # Reindex both series to the benchmark trading calendar and forward-fill
    # gaps, approximating gaps_off for index series that miss a session.
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
        if pd.isna(current_c) or pd.isna(old_c) or pd.isna(current_b) or pd.isna(old_b) or old_c == 0 or old_b == 0:
            return {"3M %": np.nan, "6M %": np.nan, "9M %": np.nan, "12M %": np.nan, "Raw RS": np.nan}
        rel = ((float(current_c) / float(old_c) - 1.0) * 100.0) - ((float(current_b) / float(old_b) - 1.0) * 100.0)
        result[label] = rel
        total += rel * weight
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
    tickers = [BENCHMARK] + [ticker for _, ticker in INDEX_UNIVERSE]
    data = _download(tickers)
    benchmark = data.get(BENCHMARK)
    if benchmark is None or benchmark.empty:
        raise RuntimeError("NIFTY 50 benchmark data could not be loaded.")

    rows = []
    for i, (name, ticker) in enumerate(INDEX_UNIVERSE, 1):
        close = data.get(ticker)
        if close is None or close.empty:
            rows.append({"INDEX": name, "Yahoo Symbol": ticker, "Status": "Data unavailable", "Raw RS": np.nan})
        else:
            metrics = _pine_score(close, benchmark)
            rows.append({
                "INDEX": name,
                "Yahoo Symbol": ticker,
                "LTP": float(close.iloc[-1]),
                **metrics,
                "Bars": len(close),
                "Status": "OK" if pd.notna(metrics["Raw RS"]) else "Insufficient history",
            })
        if progress_callback:
            progress_callback(i, len(INDEX_UNIVERSE), "Calculating RS")

    df = pd.DataFrame(rows)
    scores = df["Raw RS"].tolist()
    df["RS 1-99"] = [_rating(float(x), scores) if pd.notna(x) else np.nan for x in scores]
    df = df.sort_values(["RS 1-99", "Raw RS"], ascending=False, na_position="last").reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))

    stats = {
        "universe": len(INDEX_UNIVERSE),
        "available": int(df["Raw RS"].notna().sum()),
        "as_of": benchmark.index[-1],
    }
    return df, stats
