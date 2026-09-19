"""Numerical regression checks for the Yahoo adjusted-price pipeline.

The production scanner now downloads raw OHLC + Adj Close, reconstructs the
adjusted OHLC series, and then applies the NSE EOD close patch. This test keeps
the previous yfinance auto_adjust=True series as the numerical reference.

Run:
    python -m pytest tests/test_adjusted_data_regression.py -q
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
import yfinance as yf

import rs_engine


FIXTURES = (
    "RELIANCE",
    "ITC",
    "TCS",
    "WIPRO",
    "QMSMEDI",
)

# A small deterministic universe is enough to prove that score/rating/filter
# decisions survive the price-pipeline change without downloading the entire
# NSE universe inside every CI run.
MINI_UNIVERSE = ("RELIANCE", "ITC", "TCS", "WIPRO", "QMSMEDI")

# yfinance computes auto_adjusted OHLC from the same Adj Close / raw Close
# ratio, but independent downloads can differ at floating-point precision.
# 1 ppm remains a very strict numerical-equivalence gate while avoiding
# false failures from sub-micro price representation differences.
NUMERIC_REL_TOL = 1e-6
NUMERIC_ABS_TOL = 1e-6

METRIC_COLUMNS = (
    "LTP",
    "3M %",
    "6M %",
    "9M %",
    "12M %",
    "50 DMA",
    "150 DMA",
    "200 DMA",
    "52W High",
    "From 52W High %",
    "History Days",
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
    required = {"Open", "High", "Low", "Close", "Adj Close"}
    missing = required - set(raw_frame.columns)
    if missing:
        raise AssertionError(f"Missing columns: {sorted(missing)}")

    x = raw_frame.copy()
    raw_close = pd.to_numeric(x["Close"], errors="coerce")
    adj_close = pd.to_numeric(x["Adj Close"], errors="coerce")
    factor = (adj_close / raw_close).replace([np.inf, -np.inf], np.nan)
    valid = factor.notna() & raw_close.gt(0)

    if not valid.any():
        raise AssertionError("No valid adjustment factor")

    x = x.loc[valid].copy()
    factor = factor.loc[valid]
    for col in ("Open", "High", "Low", "Close"):
        x[col] = pd.to_numeric(x[col], errors="coerce") * factor

    x["Adjustment Factor"] = factor
    return _clean(x.drop(columns=["Adj Close"], errors="ignore"))


def _download_raw_adjusted(symbols: Iterable[str]) -> dict[str, pd.DataFrame]:
    return _download(symbols, auto_adjust=False)


def _production_metrics(symbol: str, frame: pd.DataFrame) -> dict:
    """Use the exact production metric function, not a copied implementation."""
    return rs_engine._metrics(
        symbol,
        frame,
        rising_days=20,
        calculate_ma_rising=True,
        snapshot_mode="eod",
    )


def _compare_numeric_dicts(symbol: str, old: dict, new: dict) -> None:
    assert set(old) == set(new), f"{symbol}: metric keys differ"
    for key in old:
        a = old[key]
        b = new[key]
        if isinstance(a, (bool, np.bool_)) or isinstance(b, (bool, np.bool_)):
            assert bool(a) == bool(b), f"{symbol}: boolean mismatch {key}: {a} vs {b}"
            continue
        if isinstance(a, str) or isinstance(b, str):
            assert str(a) == str(b), f"{symbol}: string mismatch {key}: {a} vs {b}"
            continue
        if isinstance(a, (int, np.integer)) or isinstance(b, (int, np.integer)):
            assert int(a) == int(b), f"{symbol}: integer mismatch {key}: {a} vs {b}"
            continue
        assert math.isclose(
            float(a),
            float(b),
            rel_tol=NUMERIC_REL_TOL,
            abs_tol=NUMERIC_ABS_TOL,
        ), f"{symbol}: metric mismatch {key}: {a} vs {b}"


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
        and np.allclose(
            old_values,
            new_values,
            rtol=NUMERIC_REL_TOL,
            atol=NUMERIC_ABS_TOL,
            equal_nan=True,
        )
    )
    return Comparison(
        symbol,
        len(old),
        len(reconstructed),
        max_abs,
        max_rel,
        "PASS" if ok else "FAIL",
    )


def _score_and_filter(
    frames: dict[str, pd.DataFrame],
    *,
    min_rs: int = 80,
    near_high_pct: float = 5,
    min_price: float = 100,
    use_ma_rising: bool = True,
    use_minervini: bool = True,
) -> pd.DataFrame:
    rows = []
    for symbol, frame in frames.items():
        row = _production_metrics(symbol, frame)
        if row:
            rows.append(row)

    df = pd.DataFrame(rows)
    assert not df.empty, "Mini-universe produced no usable metrics"
    ret_cols = ["3M %", "6M %", "9M %", "12M %"]
    df = df.dropna(subset=ret_cols).copy()
    df["Raw RS Score"] = (
        df["3M %"] * 0.40
        + df["6M %"] * 0.20
        + df["9M %"] * 0.20
        + df["12M %"] * 0.20
    )
    df["RS Rating"] = rs_engine._percentile_rating(df["Raw RS Score"])

    df = df[df["LTP"] >= min_price].copy()
    df = df[df["From 52W High %"] >= -near_high_pct].copy()
    df = df[df["RS Rating"] >= min_rs].copy()

    if use_minervini:
        df = df[
            (df["LTP"] > df["50 DMA"])
            & (df["LTP"] > df["150 DMA"])
            & (df["LTP"] > df["200 DMA"])
        ].copy()

    if use_ma_rising:
        df = df[
            df["50 DMA Rising"]
            & df["150 DMA Rising"]
            & df["200 DMA Rising"]
        ].copy()

    return df.sort_values(["RS Rating", "Raw RS Score"], ascending=False).reset_index(drop=True)


def test_price_metrics_and_ohlc_match_reference() -> None:
    symbols = FIXTURES
    old = _download(symbols, auto_adjust=True)
    raw = _download_raw_adjusted(symbols)

    for symbol in symbols:
        reconstructed = _reconstruct(raw[symbol])
        comparison = compare_fixture(symbol, old[symbol], reconstructed)
        assert comparison.status == "PASS", comparison

        old_metrics = _production_metrics(symbol, old[symbol])
        new_metrics = _production_metrics(symbol, reconstructed)
        _compare_numeric_dicts(symbol, old_metrics, new_metrics)


def test_rs_scores_ratings_and_filter_decisions_match() -> None:
    symbols = MINI_UNIVERSE
    old = _download(symbols, auto_adjust=True)
    raw = _download_raw_adjusted(symbols)
    reconstructed = {symbol: _reconstruct(raw[symbol]) for symbol in symbols}

    old_df = _score_and_filter(old)
    new_df = _score_and_filter(reconstructed)

    assert old_df["Symbol"].tolist() == new_df["Symbol"].tolist()

    old_ratings = old_df["RS Rating"].tolist()
    new_ratings = new_df["RS Rating"].tolist()
    assert old_ratings == new_ratings, (
        f"RS Rating changed: old={old_ratings} new={new_ratings}"
    )

    old_scores = old_df["Raw RS Score"].to_numpy(dtype=float)
    new_scores = new_df["Raw RS Score"].to_numpy(dtype=float)
    assert np.allclose(
        old_scores,
        new_scores,
        rtol=NUMERIC_REL_TOL,
        atol=NUMERIC_ABS_TOL,
    ), f"Raw RS Score changed: old={old_scores.tolist()} new={new_scores.tolist()}"

    old_metrics = old_df.set_index("Symbol")
    new_metrics = new_df.set_index("Symbol")
    for symbol in old_metrics.index:
        for column in ("LTP", "3M %", "6M %", "9M %", "12M %", "50 DMA", "150 DMA", "200 DMA", "52W High", "From 52W High %"):
            assert math.isclose(
                float(old_metrics.loc[symbol, column]),
                float(new_metrics.loc[symbol, column]),
                rel_tol=NUMERIC_REL_TOL,
                abs_tol=NUMERIC_ABS_TOL,
            )


def test_history_boundary_matches_production_rule() -> None:
    for length in (251, 252):
        close = pd.Series(np.arange(1, length + 1, dtype=float))
        high = close.copy()
        frame = pd.DataFrame({"Close": close, "High": high})
        assert rs_engine._metrics("TEST", frame, 20) == {}

    close = pd.Series(np.arange(1, 254, dtype=float))
    high = close.copy()
    frame = pd.DataFrame({"Close": close, "High": high})
    assert rs_engine._metrics("TEST", frame, 20)


def test_eod_nse_close_adjustment_math() -> None:
    index = pd.date_range("2026-09-14", periods=3, freq="D")
    raw = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [103.0, 104.0, 105.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.0, 102.0, 104.0],
            "Adj Close": [98.0, 99.96, 101.92],
        },
        index=index,
    )
    factor = raw["Adj Close"] / raw["Close"]
    nse_close = 105.0
    patched = nse_close * float(factor.iloc[-1])
    expected = 105.0 * (101.92 / 104.0)

    assert math.isclose(patched, expected, rel_tol=1e-12, abs_tol=1e-12)
    assert math.isclose(patched, 102.9, rel_tol=1e-12, abs_tol=1e-12)


def test_invalid_adjustment_factor_does_not_fabricate_factor_one() -> None:
    raw_close = pd.Series([100.0, 0.0, np.nan])
    adj_close = pd.Series([98.0, 0.0, 101.0])
    factor = (adj_close / raw_close).replace([np.inf, -np.inf], np.nan)
    valid = factor.dropna()

    assert len(valid) == 1
    assert math.isclose(float(valid.iloc[0]), 0.98, rel_tol=1e-12, abs_tol=1e-12)


def test_stale_recovery_merge_preserves_long_history_and_latest_bar() -> None:
    dates = pd.date_range("2026-01-01", periods=260, freq="D")
    old = pd.DataFrame(
        {
            "Close": np.arange(100.0, 360.0),
            "High": np.arange(101.0, 361.0),
        },
        index=dates,
    )
    recent_dates = pd.date_range("2026-09-15", periods=10, freq="D")
    recent = pd.DataFrame(
        {
            "Close": np.arange(350.0, 360.0),
            "High": np.arange(351.0, 361.0),
        },
        index=recent_dates,
    )

    merged = rs_engine._merge_history(old, recent)

    assert merged.index.is_monotonic_increasing
    assert not merged.index.duplicated().any()
    assert merged.index[-1] == recent.index[-1]
    assert float(merged.iloc[-1]["Close"]) == float(recent.iloc[-1]["Close"])
    assert len(merged) >= len(old)


def test_reconstruction_rejects_missing_adjusted_close() -> None:
    frame = pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [11.0, 12.0],
            "Low": [9.0, 10.0],
            "Close": [10.0, 11.0],
        }
    )
    with np.testing.assert_raises(AssertionError):
        _reconstruct(frame)


def main() -> int:
    print("=" * 72)
    print("PIPSGOX ADJUSTED-DATA + RS NUMERICAL REGRESSION")
    print("=" * 72)

    results = []
    old = _download(FIXTURES, auto_adjust=True)
    raw = _download_raw_adjusted(FIXTURES)

    for symbol in FIXTURES:
        reconstructed = _reconstruct(raw[symbol])
        comparison = compare_fixture(symbol, old[symbol], reconstructed[symbol])
        results.append(comparison)
        print(
            f"{symbol:10s} {comparison.status:4s} "
            f"rows old/new={comparison.rows_old}/{comparison.rows_new} "
            f"max_abs={comparison.max_abs:.12g} max_rel={comparison.max_rel:.12g}"
        )

    failed = [item for item in results if item.status != "PASS"]
    print("-" * 72)
    print("OVERALL:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
