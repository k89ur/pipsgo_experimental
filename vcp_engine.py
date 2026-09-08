from __future__ import annotations
from typing import Callable, Optional
import numpy as np
import pandas as pd
import rs_engine
from nse_latest_data import install_nse_latest_close
from vcp_structure import QUALITY_SWING_RULES, clean_ohlcv, build_contractions, choose_longest_sequence, breakout_info

install_nse_latest_close(rs_engine)
DEFAULT_BATCH_SIZE = rs_engine.DEFAULT_BATCH_SIZE
QUALITY_PRESETS = {
    "Strict": {"progress_tolerance": .10, "volume_tolerance": .05},
    "Standard": {"progress_tolerance": .18, "volume_tolerance": .10},
    "Loose": {"progress_tolerance": .28, "volume_tolerance": .18},
}


def _clean(frame):
    return clean_ohlcv(frame)


def _candidate_contractions(x, quality, lookback=180):
    return build_contractions(x, quality=quality, lookback=lookback)


def _choose_sequence(candidates, minimum, maximum, first_max, final_max, tolerance):
    return choose_longest_sequence(candidates, minimum, maximum, first_max, final_max, tolerance)


def _trend_ok(x):
    c = x.Close
    m50, m150, m200 = c.rolling(50).mean(), c.rolling(150).mean(), c.rolling(200).mean()
    if any(pd.isna(v) for v in (m50.iloc[-1], m150.iloc[-1], m200.iloc[-1])):
        return False
    return bool(c.iloc[-1] > m50.iloc[-1] > m150.iloc[-1] > m200.iloc[-1])


def analyze_vcp(symbol, frame, min_contractions=2, max_contractions=4, first_max=25., final_max=5., final_min_tightness=0., volume_required=True, near_high_pct=7., min_price=100., min_avg_volume=0., trend_filter=True, near_pivot_pct=5., breakout_already_occurred=False, quality="Standard", final_contraction_max_age=20):
    x = _clean(frame)
    if len(x) < 253:
        return {}
    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["Standard"])
    candidates = _candidate_contractions(x, quality)
    seq = _choose_sequence(candidates, min_contractions, max_contractions, first_max, final_max, preset["progress_tolerance"])
    close, today_high = float(x.Close.iloc[-1]), float(x.High.iloc[-1])
    avgvol = float(x.Volume.tail(50).mean())
    prior = float(x.High.iloc[-253:-1].max())
    from52 = (today_high - prior) / prior * 100 if prior else np.nan

    if seq:
        depths = [c["depth"] for c in seq]
        vols = [c["avg_volume"] for c in seq]
        pivot = max(c["recovery_high"] for c in seq)
        pdist = (pivot - close) / pivot * 100 if pivot else np.nan
        final = depths[-1]
        volcontract = all(vols[i + 1] <= vols[i] * (1 + preset["volume_tolerance"]) for i in range(len(vols) - 1))
        bo = breakout_info(close, pivot, seq)
        breakout, breakout_status = bo["breakout"], bo["status"]
        finaltight = final_min_tightness <= final <= final_max
        # Require the latest/qualifying contraction to have started recently.
        # The age is measured in trading bars from its starting swing high to the latest bar.
        final_age = max(0, len(x) - 1 - int(seq[-1]["high_i"]))
        recent_final = final_age <= int(final_contraction_max_age)
        stage = {2: "Early", 3: "Developing", 4: "Mature"}.get(len(seq), "VCP")
    else:
        depths = []
        pivot = pdist = final = np.nan
        final_age = np.nan
        recent_final = False
        volcontract = breakout = finaltight = False
        stage = "—"
        breakout_status = "No VCP"
        bo = {"breakout_contractions": np.nan}

    trend = _trend_ok(x)
    highok = from52 >= -near_high_pct
    pivotok = bool(np.isfinite(pdist) and pdist <= near_pivot_pct and pdist >= -25)
    breakoutok = breakout if breakout_already_occurred else not breakout
    qualified = bool(seq and recent_final and finaltight and (volcontract if volume_required else True) and close >= min_price and avgvol >= min_avg_volume and highok and pivotok and breakoutok and (trend or not trend_filter))
    score = min(30, len(seq) * 10) + (20 if depths and all(depths[i + 1] <= depths[i] * 1.10 for i in range(len(depths) - 1)) else 0) + (20 if finaltight else 0) + (15 if volcontract else 0) + (10 if trend else 0) + (5 if pivotok else 0)

    return {
        "Symbol": symbol, "LTP": close, "VCP": qualified, "Quality": quality,
        "VCP Stage": stage, "Contractions": len(seq),
        "C1 %": depths[0] if depths else np.nan, "C2 %": depths[1] if len(depths) > 1 else np.nan,
        "C3 %": depths[2] if len(depths) > 2 else np.nan, "C4 %": depths[3] if len(depths) > 3 else np.nan,
        "Final Contraction %": final, "Final Contraction Age": final_age,
        "Pivot": pivot, "From Pivot %": pdist,
        "52W High": prior, "From 52W High %": from52, "Avg Volume 50D": avgvol,
        "Volume Contracting": volcontract, "Trend OK": trend, "Breakout": breakout,
        "Breakout Status": breakout_status, "Breakout Contractions": bo["breakout_contractions"],
        "VCP Score": score, "History Days": len(x),
    }


def run_scan(min_contractions=2, max_contractions=4, first_max=25., final_max=5., final_min_tightness=0., volume_required=True, near_high_pct=7., min_price=100., min_avg_volume=0., trend_filter=True, near_pivot_pct=5., breakout_already_occurred=False, quality="Standard", final_contraction_max_age=20, batch_size=DEFAULT_BATCH_SIZE, snapshot_mode="eod", force_refresh=False, progress_callback: Optional[Callable] = None):
    symbols = rs_engine.get_nse_symbols()
    snap = rs_engine._download_universe(symbols, batch_size=batch_size, snapshot_mode=snapshot_mode, force_refresh=force_refresh, progress_callback=progress_callback)
    rows = []
    for done, (symbol, frame) in enumerate(snap["data"].items(), 1):
        try:
            r = analyze_vcp(symbol, frame, min_contractions, max_contractions, first_max, final_max, final_min_tightness, volume_required, near_high_pct, min_price, min_avg_volume, trend_filter, near_pivot_pct, breakout_already_occurred, quality, final_contraction_max_age)
            if r:
                rows.append(r)
        except Exception:
            pass
        if progress_callback and (done == 1 or done % 100 == 0 or done == len(snap["data"])):
            progress_callback(done, max(len(symbols), len(snap["data"])), f"Analysing VCP · {done:,}/{len(snap['data']):,}")
    if not rows:
        raise RuntimeError("No usable stock data was returned for VCP analysis.")
    df = pd.DataFrame(rows)
    df = df[df.VCP].copy().sort_values(["VCP Score", "Contractions", "From Pivot %"], ascending=[False, False, True]).reset_index(drop=True)
    if not df.empty:
        meta = rs_engine._sector_industry_results(df.Symbol.astype(str).tolist())
        inds = rs_engine._stock_index_results(df.Symbol.astype(str).tolist())
        df["Industry"] = [meta.get(s, ("Not Available", "Not Available"))[1] for s in df.Symbol.astype(str)]
        df["Index"] = [" • ".join(v for v in inds.get(s, ("Not Available",) * 5) if v != "Not Available") or "Not Available" for s in df.Symbol.astype(str)]
    df["TradingView"] = "https://www.tradingview.com/chart/?symbol=NSE%3A" + df.Symbol.astype(str)
    cols = ["Symbol", "Index", "Industry", "LTP", "VCP Score", "Quality", "VCP Stage", "Contractions", "C1 %", "C2 %", "C3 %", "C4 %", "Final Contraction %", "Final Contraction Age", "Pivot", "From Pivot %", "52W High", "From 52W High %", "Avg Volume 50D", "Volume Contracting", "Trend OK", "Breakout", "Breakout Status", "Breakout Contractions", "History Days", "TradingView"]
    df = df[[c for c in cols if c in df.columns]]
    stats = {"universe": len(symbols), "downloaded": snap["downloaded"], "coverage": snap["usable_coverage"], "usable": snap["usable"], "missing_count": snap["missing_count"], "short_history_count": snap["short_history_count"], "stale_data_count": snap["stale_data_count"], "data_date": snap["data_date"], "snapshot_mode": snap["mode"], "snapshot_day": snap["snapshot_day"], "downloaded_at": snap["downloaded_at"], "total_candidates": len(rows), "matches": len(df)}
    return df, stats
