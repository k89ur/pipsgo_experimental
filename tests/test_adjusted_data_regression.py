"""Isolated regression checks for Yahoo adjusted-price reconstruction.

This module intentionally does not modify production scanner code.
Run with:
    python -m pytest tests/test_adjusted_data_regression.py -q
or:
    python tests/test_adjusted_data_regression.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
import yfinance as yf


FIXTURES = (
    "RELIANCE",
    "ITC",
    "TCS",
    "WIPRO",
    "QMSMEDI",
)


@dataclass
class Comparison:
    symbol: str
    rows_old: int
    rows_new: int
    max_abs: float
    max_rel: float
    status: str


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    x = frame.copy()
    idx = pd.to_datetime(x.index, errors="coerce")
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    x.index = idx
    x = x[~x.index.isna()].sort_index()
    x = x[~x.index.duplicated(keep="last")]
    for col in x.columns:
        x[col] = pd.to_numeric(x[col], errors="coerce")
    return x.replace([np.inf, -np.inf], np.nan)


def _extract(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    ticker = f"{symbol}.NS"
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = set(raw.columns.get_level_values(0))
        level1 = set(raw.columns.get_level_values(1))
        if ticker in level0:
            return _clean(raw[ticker])
        if ticker in level1:
            return _clean(raw.xs(ticker, axis=1, level=1))
        return pd.DataFrame()
    return _clean(raw)


def _download(symbols: Iterable[str], auto_adjust: bool) -> dict[str, pd.DataFrame]:
    symbols = list(symbols)
    raw = yf.download(
        tickers=[f"{s}.NS" for s in symbols],
        period="2y",
        interval="1d",
        auto_adjust=auto_adjust,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    return {s: _extract(raw, s) for s in symbols}


def _reconstruct(raw_frame: pd.DataFrame) -> pd.DataFrame:
    x = raw_frame.copy()
    required = {"Open", "High", "Low", "Close", "Adj Close"}
    missing = required - set(x.columns)
    if missing:
        raise AssertionError(f"Missing columns: {sorted(missing)}")

    raw_close = pd.to_numeric(x["Close"], errors="coerce")
    adj_close = pd.to_numeric(x["Adj Close"], errors="coerce")
    factor = adj_close / raw_close
    if factor.replace([np.inf, -np.inf], np.nan).dropna().empty:
        raise AssertionError("No valid adjustment factor")

    for col in ("Open", "High", "Low", "Close"):
        values = pd.to_numeric(x[col], errors="coerce")
        x[col] = values * factor

    return x


def _download_raw_adjusted(symbols: Iterable[str]) -> dict[str, pd.DataFrame]:
    symbols = list(symbols)
    raw = yf.download(
        tickers=[f"{s}.NS" for s in symbols],
        period="2y",
        interval="1d",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    return {s: _extract(raw, s) for s in symbols}


def _metrics(close: pd.Series, high: pd.Series) -> dict[str, float]:
    close = pd.to_numeric(close, errors="coerce").dropna().astype(float)
    high = pd.to_numeric(high, errors="coerce").dropna().astype(float)
    if len(close) < 200 or len(high) < 253:
        return {}

    def ret(days: int) -> float:
        if len(close) <= days:
            return math.nan
        return (float(close.iloc[-1]) / float(close.iloc[-days - 1]) - 1.0) * 100.0

    d50 = close.rolling(50).mean()
    d150 = close.rolling(150).mean()
    d200 = close.rolling(200).mean()
    previous_high = float(high.iloc[-253:-1].max())
    ltp = float(close.iloc[-1])

    return {
        "3M %": ret(63),
        "6M %": ret(126),
        "9M %": ret(189),
        "12M %": ret(252),
        "50 DMA": float(d50.iloc[-1]),
        "150 DMA": float(d150.iloc[-1]),
        "200 DMA": float(d200.iloc[-1]),
        "52W High": previous_high,
        "From 52W High %": (ltp - previous_high) / previous_high * 100.0,
    }


def compare_fixture(symbol: str, old: pd.DataFrame, reconstructed: pd.DataFrame) -> Comparison:
    common = old.index.intersection(reconstructed.index)
    if len(common) == 0:
        return Comparison(symbol, len(old), len(reconstructed), math.inf, math.inf, "FAIL")

    cols = [c for c in ("Open", "High", "Low", "Close") if c in old.columns and c in reconstructed.columns]
    old_values = old.loc[common, cols].to_numpy(dtype=float)
    new_values = reconstructed.loc[common, cols].to_numpy(dtype=float)
    diff = np.abs(old_values - new_values)
    scale = np.maximum(np.abs(old_values), 1e-12)
    rel = diff / scale

    max_abs = float(np.nanmax(diff))
    max_rel = float(np.nanmax(rel))
    ok = (
        len(common) == len(old) == len(reconstructed)
        and np.isfinite(max_abs)
        and max_abs <= 1e-8
        and max_rel <= 1e-8
    )
    return Comparison(
        symbol,
        len(old),
        len(reconstructed),
        max_abs,
        max_rel,
        "PASS" if ok else "FAIL",
    )


def run_regression(symbols: Iterable[str] = FIXTURES) -> list[Comparison]:
    symbols = tuple(dict.fromkeys(symbols))
    old = _download(symbols, auto_adjust=True)
    raw = _download_raw_adjusted(symbols)

    comparisons: list[Comparison] = []
    for symbol in symbols:
        reconstructed = _reconstruct(raw[symbol])
        comparisons.append(compare_fixture(symbol, old[symbol], reconstructed))

        old_metrics = _metrics(old[symbol]["Close"], old[symbol]["High"])
        new_metrics = _metrics(reconstructed["Close"], reconstructed["High"])
        for key in old_metrics:
            a = old_metrics[key]
            b = new_metrics.get(key, math.nan)
            if not math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-8):
                raise AssertionError(
                    f"{symbol}: metric mismatch {key}: old={a}, new={b}"
                )

    return comparisons


def main() -> int:
    print("=" * 64)
    print("PIPSGOX ADJUSTED-DATA REGRESSION — BASELINE")
    print("=" * 64)
    results = run_regression()
    for item in results:
        print(
            f"{item.symbol:10s} {item.status:4s} "
            f"rows old/new={item.rows_old}/{item.rows_new} "
            f"max_abs={item.max_abs:.12g} max_rel={item.max_rel:.12g}"
        )

    failed = [item for item in results if item.status != "PASS"]
    print("-" * 64)
    print("OVERALL:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
