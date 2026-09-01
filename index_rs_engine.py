from __future__ import annotations

from typing import Callable, Optional
import numpy as np
import pandas as pd
import yfinance as yf

INDEX_UNIVERSE = [
    ("BANKNIFTY", "^NSEBANK"), ("CNXAUTO", "^CNXAUTO"),
    ("CNXCONSUMPTION", "^CNXCONSUMPTION"), ("CNXENERGY", "^CNXENERGY"),
    ("CNXFINANCE", "^CNXFINANCE"), ("CNXFMCG", "^CNXFMCG"),
    ("CNXINFRA", "^CNXINFRA"), ("CNXIT", "^CNXIT"),
    ("CNXMETAL", "^CNXMETAL"), ("CNXPHARMA", "^CNXPHARMA"),
    ("CNXPSE", "^CNXPSE"), ("CNXPSUBANK", "^CNXPSUBANK"),
    ("CNXREALTY", "^CNXREALTY"), ("CNXSERVICE", "^CNXSERVICE"),
    ("CPSE", "^CNXCPSE"), ("NIFTYPVTBANK", "^NIFTYPVTBANK"),
    ("NIFTY_CAPITAL_MKT", "NIFTY_CAPITAL_MKT.NS"),
    ("NIFTY_CEMENT", "NIFTY_CEMENT.NS"),
    ("NIFTY_CHEMICALS", "NIFTY_CHEMICALS.NS"),
    ("NIFTY_CONSR_DURBL", "NIFTY_CONSR_DURBL.NS"),
    ("NIFTY_EV", "NIFTY_EV.NS"), ("NIFTY_HEALTHCARE", "NIFTY_HEALTHCARE.NS"),
    ("NIFTY_IND_DEFENCE", "NIFTY_IND_DEFENCE.NS"),
    ("NIFTY_IND_DIGITAL", "NIFTY_IND_DIGITAL.NS"),
    ("NIFTY_IND_TOURISM", "NIFTY_IND_TOURISM.NS"),
    ("NIFTY_IPO", "NIFTY_IPO.NS"),
    ("NIFTY_OIL_AND_GAS", "NIFTY_OIL_AND_GAS.NS"),
    ("NIFTY_TRANS_LOGIS", "NIFTY_TRANS_LOGIS.NS"),
]
BENCHMARK = "^NSEI"


def _download(tickers: list[str]) -> dict[str, pd.Series]:
    raw = yf.download(tickers=tickers, period="2y", interval="1d", auto_adjust=False,
                       progress=False, group_by="ticker", threads=True)
    if raw is None or raw.empty:
        return {}
    out = {}
    if isinstance(raw.columns, pd.MultiIndex):
        l0, l1 = set(raw.columns.get_level_values(0)), set(raw.columns.get_level_values(1))
        for t in tickers:
            try:
                x = raw[t]["Close"] if t in l0 else raw.xs(t, axis=1, level=1)["Close"] if t in l1 else None
                if x is not None and not x.dropna().empty:
                    out[t] = pd.to_numeric(x, errors="coerce").dropna()
            except Exception:
                pass
    else:
        out[tickers[0]] = pd.to_numeric(raw["Close"], errors="coerce").dropna()
    return out


def _score(close: pd.Series, bench: pd.Series) -> dict:
    close, bench = close.align(bench, join="inner")
    periods = [("3M %", 63, .40), ("6M %", 126, .20), ("9M %", 189, .20), ("12M %", 252, .20)]
    result, total = {}, 0.0
    for label, bars, weight in periods:
        if len(close) <= bars or len(bench) <= bars:
            return {"3M %": np.nan, "6M %": np.nan, "9M %": np.nan, "12M %": np.nan, "Raw RS": np.nan}
        c0, b0 = float(close.iloc[-bars-1]), float(bench.iloc[-bars-1])
        if c0 == 0 or b0 == 0:
            return {"3M %": np.nan, "6M %": np.nan, "9M %": np.nan, "12M %": np.nan, "Raw RS": np.nan}
        rel = ((float(close.iloc[-1]) / c0 - 1) * 100) - ((float(bench.iloc[-1]) / b0 - 1) * 100)
        result[label] = rel
        total += rel * weight
    result["Raw RS"] = total
    return result


def _rating(value: float, scores: list[float]):
    valid = [x for x in scores if not np.isnan(x)]
    if np.isnan(value) or len(valid) <= 1:
        return np.nan
    below = sum(x < value for x in valid)
    return int(round(1 + (below / (len(valid) - 1.0)) * 98))


def run_index_scan(progress_callback: Optional[Callable[[int, int, str], None]] = None):
    tickers = [BENCHMARK] + [t for _, t in INDEX_UNIVERSE]
    data = _download(tickers)
    bench = data.get(BENCHMARK)
    if bench is None:
        raise RuntimeError("NIFTY 50 benchmark data could not be loaded.")
    rows = []
    for i, (name, ticker) in enumerate(INDEX_UNIVERSE, 1):
        close = data.get(ticker)
        if close is None:
            rows.append({"INDEX": name, "Yahoo Symbol": ticker, "Status": "Data unavailable", "Raw RS": np.nan})
        else:
            m = _score(close, bench)
            rows.append({"INDEX": name, "Yahoo Symbol": ticker, "LTP": float(close.iloc[-1]), **m,
                         "Bars": len(close), "Status": "OK" if pd.notna(m["Raw RS"]) else "Insufficient history"})
        if progress_callback:
            progress_callback(i, len(INDEX_UNIVERSE), "Calculating RS")
    df = pd.DataFrame(rows)
    scores = df["Raw RS"].tolist()
    df["RS 1-99"] = [_rating(float(x), scores) if pd.notna(x) else np.nan for x in scores]
    df = df.sort_values(["RS 1-99", "Raw RS"], ascending=False, na_position="last").reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))
    stats = {"universe": 28, "available": int(df["Raw RS"].notna().sum()), "as_of": max((s.index[-1] for s in data.values() if len(s)), default=None)}
    return df, stats
