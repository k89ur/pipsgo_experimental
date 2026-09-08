from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import pandas as pd

import rs_engine
from nse_latest_data import install_nse_latest_close

install_nse_latest_close(rs_engine)

DEFAULT_BATCH_SIZE = rs_engine.DEFAULT_BATCH_SIZE

QUALITY_PRESETS = {
    "Strict": {"swing_window": 4, "depth_tolerance": 0.10, "progress_tolerance": 0.10, "volume_tolerance": 0.05},
    "Standard": {"swing_window": 4, "depth_tolerance": 0.18, "progress_tolerance": 0.18, "volume_tolerance": 0.10},
    "Loose": {"swing_window": 3, "depth_tolerance": 0.28, "progress_tolerance": 0.28, "volume_tolerance": 0.18},
}


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty or not {"Close", "High", "Low", "Volume"}.issubset(frame.columns):
        return pd.DataFrame()
    x = frame[["Close", "High", "Low", "Volume"]].copy()
    x.index = pd.to_datetime(x.index, errors="coerce")
    if getattr(x.index, "tz", None) is not None:
        x.index = x.index.tz_localize(None)
    x = x[~x.index.isna()].sort_index()
    for col in x.columns:
        x[col] = pd.to_numeric(x[col], errors="coerce")
    x = x.replace([np.inf, -np.inf], np.nan).dropna(subset=["Close", "High", "Low"])
    x = x[x["Close"] > 0]
    x["Volume"] = x["Volume"].fillna(0).clip(lower=0)
    return x


def _extrema(x: pd.DataFrame, window: int) -> list[tuple[int, str, float]]:
    highs = x["High"].rolling(window * 2 + 1, center=True).max()
    lows = x["Low"].rolling(window * 2 + 1, center=True).min()
    points: list[tuple[int, str, float]] = []
    for i in range(window, len(x) - window):
        h = float(x["High"].iloc[i])
        lo = float(x["Low"].iloc[i])
        if np.isfinite(h) and h >= float(highs.iloc[i]) * (1 - 1e-9):
            points.append((i, "H", h))
        if np.isfinite(lo) and lo <= float(lows.iloc[i]) * (1 + 1e-9):
            points.append((i, "L", lo))
    points.sort(key=lambda z: z[0])
    # Collapse consecutive same-type extrema, retaining the more meaningful one.
    collapsed: list[tuple[int, str, float]] = []
    for point in points:
        if not collapsed or collapsed[-1][1] != point[1]:
            collapsed.append(point)
            continue
        old = collapsed[-1]
        better = point if ((point[1] == "H" and point[2] >= old[2]) or (point[1] == "L" and point[2] <= old[2])) else old
        collapsed[-1] = better
    return collapsed


def _candidate_contractions(x: pd.DataFrame, window: int, lookback: int = 180) -> list[dict]:
    start = max(0, len(x) - lookback)
    y = x.iloc[start:].reset_index(drop=False)
    points = _extrema(y, window)
    contractions: list[dict] = []
    for j in range(len(points) - 2):
        p1, p2, p3 = points[j:j + 3]
        if p1[1] != "H" or p2[1] != "L" or p3[1] != "H":
            continue
        if not (p1[0] < p2[0] < p3[0]):
            continue
        high = float(p1[2])
        low = float(p2[2])
        recovery_high = float(p3[2])
        if high <= 0 or low <= 0:
            continue
        depth = (high - low) / high * 100.0
        if depth < 1.0 or depth > 40.0:
            continue
        segment = y.iloc[p1[0]:p3[0] + 1]
        avg_vol = float(segment["Volume"].mean()) if not segment.empty else np.nan
        contractions.append({
            "high_i": start + p1[0],
            "low_i": start + p2[0],
            "recover_i": start + p3[0],
            "high": high,
            "low": low,
            "recovery_high": recovery_high,
            "depth": depth,
            "avg_volume": avg_vol,
        })
    return contractions


def _choose_sequence(candidates: list[dict], minimum: int, maximum: int, first_max: float, final_max: float, tolerance: float) -> list[dict]:
    if not candidates:
        return []
    best: list[dict] = []
    for end in range(len(candidates)):
        for start in range(max(0, end - 6), end + 1):
            seq = candidates[start:end + 1]
            if not (minimum <= len(seq) <= maximum):
                continue
            # Adjacent contractions must be chronological and meaningfully separated.
            if any(seq[k]["recover_i"] >= seq[k + 1]["high_i"] for k in range(len(seq) - 1)):
                continue
            depths = [c["depth"] for c in seq]
            if depths[0] > first_max or depths[-1] > final_max:
                continue
            if any(depths[k + 1] > depths[k] * (1 + tolerance) for k in range(len(depths) - 1)):
                continue
            # A contraction should normally recover toward the prior high; do not accept
            # sequences whose recovery collapses materially lower than the prior swing.
            if any(seq[k + 1]["recovery_high"] < seq[k]["recovery_high"] * (0.75 - tolerance) for k in range(len(seq) - 1)):
                continue
            if len(seq) > len(best) or (len(seq) == len(best) and seq[-1]["recover_i"] > (best[-1]["recover_i"] if best else -1)):
                best = seq
    return best


def _trend_ok(x: pd.DataFrame) -> bool:
    close = x["Close"]
    ma50 = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()
    if any(pd.isna(v) for v in (ma50.iloc[-1], ma150.iloc[-1], ma200.iloc[-1])):
        return False
    return bool(close.iloc[-1] > ma50.iloc[-1] > ma150.iloc[-1] > ma200.iloc[-1])


def analyze_vcp(
    symbol: str,
    frame: pd.DataFrame,
    min_contractions: int = 2,
    max_contractions: int = 4,
    first_max: float = 25.0,
    final_max: float = 5.0,
    final_min_tightness: float = 0.0,
    volume_required: bool = True,
    near_high_pct: float = 7.0,
    min_price: float = 100.0,
    min_avg_volume: float = 0.0,
    trend_filter: bool = True,
    near_pivot_pct: float = 5.0,
    breakout_already_occurred: bool = False,
    quality: str = "Standard",
) -> dict:
    x = _clean(frame)
    if len(x) < 253:
        return {}
    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["Standard"])
    contractions = _candidate_contractions(x, preset["swing_window"])
    seq = _choose_sequence(contractions, min_contractions, max_contractions, first_max, final_max, preset["progress_tolerance"])
    close = float(x["Close"].iloc[-1])
    high = float(x["High"].iloc[-1])
    low = float(x["Low"].iloc[-1])
    avg_volume_50 = float(x["Volume"].tail(50).mean())
    prior_52w_high = float(x["High"].iloc[-253:-1].max())
    from_52w = (high - prior_52w_high) / prior_52w_high * 100.0 if prior_52w_high else np.nan
    if seq:
        pivot = max(c["recovery_high"] for c in seq)
        final_depth = seq[-1]["depth"]
        first_depth = seq[0]["depth"]
        depths = [c["depth"] for c in seq]
        volumes = [c["avg_volume"] for c in seq]
        volume_contracting = all(volumes[i + 1] <= volumes[i] * (1 + preset["volume_tolerance"]) for i in range(len(volumes) - 1)) if len(volumes) > 1 else True
        pivot_distance = (pivot - close) / pivot * 100.0 if pivot else np.nan
        breakout = close > pivot * 1.005
        final_tight_enough = final_depth >= final_min_tightness and final_depth <= final_max
    else:
        pivot = np.nan
        final_depth = np.nan
        first_depth = np.nan
        depths = []
        volume_contracting = False
        pivot_distance = np.nan
        breakout = False
        final_tight_enough = False
    trend = _trend_ok(x)
    price_ok = close >= min_price
    avg_volume_ok = avg_volume_50 >= min_avg_volume
    high_ok = from_52w >= -near_high_pct
    pivot_ok = bool(np.isfinite(pivot_distance) and pivot_distance <= near_pivot_pct and pivot_distance >= -25.0)
    breakout_ok = breakout if breakout_already_occurred else not breakout
    volume_ok = volume_contracting if volume_required else True
    qualified = bool(
        seq
        and final_tight_enough
        and volume_ok
        and price_ok
        and avg_volume_ok
        and high_ok
        and pivot_ok
        and breakout_ok
        and (trend or not trend_filter)
    )
    # Quality score is diagnostic, not an alternate pass/fail rule.
    score = 0
    score += min(30, len(seq) * 10)
    if depths and all(depths[i + 1] <= depths[i] * 1.10 for i in range(len(depths) - 1)):
        score += 20
    if final_tight_enough:
        score += 20
    if volume_contracting:
        score += 15
    if trend:
        score += 10
    if pivot_ok:
        score += 5
    return {
        "Symbol": symbol,
        "LTP": close,
        "VCP": qualified,
        "Quality": quality,
        "Contractions": len(seq),
        "C1 %": depths[0] if depths else np.nan,
        "C2 %": depths[1] if len(depths) > 1 else np.nan,
        "C3 %": depths[2] if len(depths) > 2 else np.nan,
        "C4 %": depths[3] if len(depths) > 3 else np.nan,
        "Final Contraction %": final_depth,
        "Pivot": pivot,
        "From Pivot %": pivot_distance,
        "52W High": prior_52w_high,
        "From 52W High %": from_52w,
        "Avg Volume 50D": avg_volume_50,
        "Volume Contracting": volume_contracting,
        "Trend OK": trend,
        "Breakout": breakout,
        "VCP Score": score,
        "History Days": len(x),
    }


def run_scan(
    min_contractions: int = 2,
    max_contractions: int = 4,
    first_max: float = 25.0,
    final_max: float = 5.0,
    final_min_tightness: float = 0.0,
    volume_required: bool = True,
    near_high_pct: float = 7.0,
    min_price: float = 100.0,
    min_avg_volume: float = 0.0,
    trend_filter: bool = True,
    near_pivot_pct: float = 5.0,
    breakout_already_occurred: bool = False,
    quality: str = "Standard",
    batch_size: int = DEFAULT_BATCH_SIZE,
    snapshot_mode: str = "eod",
    force_refresh: bool = False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
):
    symbols = rs_engine.get_nse_symbols()
    snapshot = rs_engine._download_universe(
        symbols,
        batch_size=batch_size,
        snapshot_mode=snapshot_mode,
        force_refresh=force_refresh,
        progress_callback=progress_callback,
    )
    data = snapshot["data"]
    rows = []
    total = len(symbols)
    for done, (symbol, frame) in enumerate(data.items(), start=1):
        try:
            row = analyze_vcp(
                symbol, frame,
                min_contractions=min_contractions,
                max_contractions=max_contractions,
                first_max=first_max,
                final_max=final_max,
                final_min_tightness=final_min_tightness,
                volume_required=volume_required,
                near_high_pct=near_high_pct,
                min_price=min_price,
                min_avg_volume=min_avg_volume,
                trend_filter=trend_filter,
                near_pivot_pct=near_pivot_pct,
                breakout_already_occurred=breakout_already_occurred,
                quality=quality,
            )
            if row:
                rows.append(row)
        except Exception:
            continue
        if progress_callback and (done == 1 or done % 100 == 0 or done == len(data)):
            progress_callback(done, max(total, len(data)), f"Analysing VCP · {done:,}/{len(data):,}")
    if not rows:
        raise RuntimeError("No usable stock data was returned for VCP analysis.")
    df = pd.DataFrame(rows)
    df = df[df["VCP"]].copy()
    df = df.sort_values(["VCP Score", "Contractions", "From Pivot %"], ascending=[False, False, True]).reset_index(drop=True)
    if not df.empty:
        metadata = rs_engine._sector_industry_results(df["Symbol"].astype(str).tolist())
        indices = rs_engine._stock_index_results(df["Symbol"].astype(str).tolist())
        df["Industry"] = [metadata.get(s, ("Not Available", "Not Available"))[1] for s in df["Symbol"].astype(str)]
        df["Index"] = [" • ".join(v for v in indices.get(s, ("Not Available",) * 5) if v != "Not Available") or "Not Available" for s in df["Symbol"].astype(str)]
    df["TradingView"] = "https://www.tradingview.com/chart/?symbol=NSE%3A" + df["Symbol"].astype(str)
    columns = ["Symbol", "Index", "Industry", "LTP", "VCP Score", "Quality", "Contractions", "C1 %", "C2 %", "C3 %", "C4 %", "Final Contraction %", "Pivot", "From Pivot %", "52W High", "From 52W High %", "Avg Volume 50D", "Volume Contracting", "Trend OK", "Breakout", "History Days", "TradingView"]
    df = df[[c for c in columns if c in df.columns]]
    stats = {
        "universe": len(symbols),
        "downloaded": snapshot["downloaded"],
        "coverage": snapshot["usable_coverage"],
        "usable": snapshot["usable"],
        "missing_count": snapshot["missing_count"],
        "short_history_count": snapshot["short_history_count"],
        "stale_data_count": snapshot["stale_data_count"],
        "data_date": snapshot["data_date"],
        "snapshot_mode": snapshot["mode"],
        "snapshot_day": snapshot["snapshot_day"],
        "downloaded_at": snapshot["downloaded_at"],
        "total_candidates": len(rows),
        "matches": len(df),
    }
    return df, stats
