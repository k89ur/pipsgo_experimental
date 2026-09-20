from __future__ import annotations

import os
import time

import pandas as pd
import pytest

import fno_stocks
import nse_latest_data
import rs_engine

RUN = os.getenv("RUN_BZ_DETAIL_AUDIT") == "1"


def _metrics_for_symbols(symbols: list[str], snapshot: dict) -> pd.DataFrame:
    stale = set(snapshot.get("stale_data_symbols", []))
    rows = []
    for symbol in symbols:
        if symbol in stale:
            continue
        frame = snapshot["data"].get(symbol)
        if frame is None or frame.empty:
            continue
        try:
            m = rs_engine._metrics(
                symbol,
                frame,
                rising_days=20,
                calculate_ma_rising=False,
                snapshot_mode="eod",
            )
        except Exception:
            continue
        if m:
            rows.append(m)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["3M %", "6M %", "9M %", "12M %"]).copy()
    df["Raw RS Score"] = (
        df["3M %"] * 0.40
        + df["6M %"] * 0.20
        + df["9M %"] * 0.20
        + df["12M %"] * 0.20
    )
    df["RS Rating"] = rs_engine._percentile_rating(df["Raw RS Score"])
    df["Min Price"] = df["LTP"] >= 100
    df["Near 52W High"] = df["From 52W High %"] >= -5
    df["RS >= 80"] = df["RS Rating"] >= 80
    df["Minervini"] = (
        (df["LTP"] > df["50 DMA"])
        & (df["LTP"] > df["150 DMA"])
        & (df["LTP"] > df["200 DMA"])
    )
    df["Final Match"] = (
        df["Min Price"]
        & df["Near 52W High"]
        & df["RS >= 80"]
        & df["Minervini"]
    )
    return df.set_index("Symbol", drop=False)


@pytest.mark.skipif(
    not RUN,
    reason="Set RUN_BZ_DETAIL_AUDIT=1 to run this network diagnostic",
)
def test_bz_detail_audit() -> None:
    started = time.perf_counter()
    universe = rs_engine.get_nse_symbols()

    nse_date, bhavcopy = nse_latest_data._fetch_nse_bhavcopy(
        max_lookback_days=5,
        require_today=False,
        equity_only=False,
    )
    series_map = (
        bhavcopy[["SYMBOL", "SERIES"]]
        .drop_duplicates("SYMBOL", keep="last")
        .set_index("SYMBOL")["SERIES"]
        .astype(str)
        .str.strip()
        .str.upper()
    )
    bz = sorted(s for s in universe if series_map.get(s) == "BZ")

    snapshot = rs_engine._download_universe(
        universe,
        batch_size=150,
        snapshot_mode="eod",
        force_refresh=False,
        bypass_memory_cache=False,
    )
    snapshot = nse_latest_data.patch_snapshot(snapshot)

    metrics = _metrics_for_symbols(bz, snapshot)
    fno = fno_stocks.load_fno_symbols()

    columns = [
        "Symbol", "LTP", "History Days", "Raw RS Score", "RS Rating",
        "3M %", "6M %", "9M %", "12M %",
        "52W High", "From 52W High %",
        "50 DMA", "150 DMA", "200 DMA",
        "Min Price", "Near 52W High", "RS >= 80", "Minervini", "Final Match",
    ]

    print("\n" + "=" * 120)
    print("BZ DETAIL AUDIT #14.5")
    print("=" * 120)
    print(f"NSE bhavcopy date : {nse_date}")
    print(f"BZ universe count : {len(bz):,}")
    print(f"Metric rows       : {len(metrics):,}")
    print(f"F&O BZ rows       : {len(set(bz) & fno):,}")

    if metrics.empty:
        print("No BZ symbols produced usable metric rows.")
    else:
        detail = metrics[columns].copy()
        detail["F&O"] = detail["Symbol"].isin(fno)
        detail = detail.sort_values(
            ["Final Match", "RS Rating", "Raw RS Score"],
            ascending=[False, False, False],
        )
        print("\nBZ stock details:")
        print(detail.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

        final = detail.loc[detail["Final Match"], "Symbol"].tolist()
        print("\nBZ final matches:", final)

    print(f"Audit elapsed seconds : {time.perf_counter() - started:.2f}")
    print("=" * 120)

    assert len(universe) >= 1000
    assert len(bz) >= 0
