from __future__ import annotations

import io
import time
from typing import Callable, Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf

NSE_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"

def get_nse_symbols() -> list[str]:
    """Get the current NSE equity universe. Falls back to bundled symbols.csv."""
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/csv,*/*",
    }
    try:
        r = requests.get(NSE_URL, headers=headers, timeout=20)
        r.raise_for_status()
        df = pd.read_csv(io.BytesIO(r.content))
        col = next((c for c in ["SYMBOL", "Symbol", "symbol"] if c in df.columns), None)
        if not col:
            raise ValueError("NSE CSV has no SYMBOL column")
        symbols = (
            df[col].astype(str).str.strip()
            .replace("nan", np.nan).dropna().unique().tolist()
        )
        symbols = [s for s in symbols if s and s not in {"SYMBOL"}]
        if len(symbols) >= 100:
            return sorted(symbols)
    except Exception:
        pass

    try:
        fallback = pd.read_csv("symbols.csv")
        col = "Symbol" if "Symbol" in fallback.columns else fallback.columns[0]
        return sorted(fallback[col].dropna().astype(str).str.strip().unique())
    except Exception as e:
        raise RuntimeError(
            "Could not load NSE symbols. NSE may be temporarily blocking the request. "
            "Keep an updated symbols.csv beside app.py."
        ) from e


def _download_batch(symbols: list[str]) -> dict[str, pd.DataFrame]:
    tickers = [f"{s}.NS" for s in symbols]
    raw = yf.download(
        tickers=tickers,
        period="2y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )

    result = {}
    if raw is None or raw.empty:
        return result

    # Multiple tickers -> MultiIndex columns. Single ticker -> normal columns.
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = set(raw.columns.get_level_values(0))
        level1 = set(raw.columns.get_level_values(1))
        for s in symbols:
            t = f"{s}.NS"
            try:
                if t in level0:
                    x = raw[t].copy()
                elif t in level1:
                    x = raw.xs(t, axis=1, level=1).copy()
                else:
                    continue
                if "Close" in x.columns and not x["Close"].dropna().empty:
                    result[s] = x.dropna(subset=["Close"])
            except Exception:
                continue
    else:
        s = symbols[0]
        if "Close" in raw.columns:
            result[s] = raw.dropna(subset=["Close"])

    return result


def _return_at_days(close: pd.Series, days: int) -> float:
    if len(close) <= days:
        return np.nan
    now = float(close.iloc[-1])
    old = float(close.iloc[-days - 1])
    return (now / old - 1.0) * 100.0 if old else np.nan


def _metrics(symbol: str, x: pd.DataFrame, rising_days: int) -> dict:
    close = x["Close"].dropna().astype(float)
    if len(close) < 200:
        return {}

    ltp = float(close.iloc[-1])
    d50 = close.rolling(50).mean()
    d150 = close.rolling(150).mean()
    d200 = close.rolling(200).mean()

    # Rising = today's DMA greater than DMA N trading sessions ago.
    if len(d200.dropna()) <= rising_days:
        return {}

    high_52w = float(close.tail(252).max())
    from_high = (high_52w - ltp) / high_52w * 100.0 if high_52w else np.nan

    return {
        "Symbol": symbol,
        "LTP": ltp,
        "3M %": _return_at_days(close, 63),
        "6M %": _return_at_days(close, 126),
        "9M %": _return_at_days(close, 189),
        "12M %": _return_at_days(close, 252),
        "50 DMA": float(d50.iloc[-1]),
        "150 DMA": float(d150.iloc[-1]),
        "200 DMA": float(d200.iloc[-1]),
        "50 DMA Rising": float(d50.iloc[-1]) > float(d50.iloc[-1-rising_days]),
        "150 DMA Rising": float(d150.iloc[-1]) > float(d150.iloc[-1-rising_days]),
        "200 DMA Rising": float(d200.iloc[-1]) > float(d200.iloc[-1-rising_days]),
        "52W High": high_52w,
        "From 52W High %": from_high,
        "History Days": len(close),
    }


def _percentile_rating(scores: pd.Series) -> pd.Series:
    """Convert raw scores to a 1–99 percentile-style rating."""
    pct = scores.rank(method="average", pct=True) * 99
    return pct.round().clip(1, 99).astype(int)


def run_scan(
    min_rs: int = 80,
    near_high_pct: float = 5,
    min_price: float = 100,
    rising_days: int = 20,
    use_minervini: bool = True,
    batch_size: int = 50,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
):
    symbols = get_nse_symbols()
    total = len(symbols)
    rows = []
    successful = 0

    for start in range(0, total, batch_size):
        batch = symbols[start:start + batch_size]
        data = _download_batch(batch)
        successful += len(data)

        for symbol, x in data.items():
            try:
                m = _metrics(symbol, x, rising_days)
                if m:
                    rows.append(m)
            except Exception:
                continue

        done = min(start + len(batch), total)
        if progress_callback:
            progress_callback(done, total, "Downloading & calculating")
        time.sleep(0.05)

    if not rows:
        raise RuntimeError("No usable stock data was returned.")

    df = pd.DataFrame(rows)

    # Require complete multi-period returns.
    ret_cols = ["3M %", "6M %", "9M %", "12M %"]
    df = df.dropna(subset=ret_cols).copy()

    # IBD-style approximation: more weight on recent performance.
    df["Raw RS Score"] = (
        df["3M %"] * 0.40
        + df["6M %"] * 0.20
        + df["9M %"] * 0.20
        + df["12M %"] * 0.20
    )

    df["RS Rating"] = _percentile_rating(df["Raw RS Score"])

    # Core user filters.
    df = df[
        (df["LTP"] >= min_price)
        & (df["History Days"] >= 252)
        & (df["RS Rating"] >= min_rs)
        & (df["From 52W High %"] <= near_high_pct)
    ].copy()

    if use_minervini:
        df = df[
            (df["LTP"] > df["50 DMA"])
            & (df["LTP"] > df["150 DMA"])
            & (df["LTP"] > df["200 DMA"])
            & (df["50 DMA Rising"])
            & (df["150 DMA Rising"])
            & (df["200 DMA Rising"])
        ].copy()

    df = df.sort_values(["RS Rating", "Raw RS Score"], ascending=False)

    # Add chart URL for CSV/export use.
    df["TradingView"] = (
        "https://www.tradingview.com/chart/?symbol=NSE%3A"
        + df["Symbol"].astype(str)
    )

    columns = [
        "Symbol", "LTP", "RS Rating", "Raw RS Score",
        "3M %", "6M %", "9M %", "12M %",
        "50 DMA", "150 DMA", "200 DMA",
        "52W High", "From 52W High %",
        "History Days", "TradingView",
    ]
    df = df[columns].reset_index(drop=True)

    stats = {
        "universe": total,
        "coverage": (successful / total * 100) if total else 0,
    }
    return df, stats
