from __future__ import annotations

import os
import time

import pandas as pd
import pytest

import fno_stocks
import nse_latest_data
import rs_engine

RUN = os.getenv("RUN_BZ_POLICY_AUDIT") == "1"


def _prepare_metrics(
    symbols: list[str],
    snapshot: dict,
    rising_days: int = 20,
) -> pd.DataFrame:
    stale = set(snapshot.get("stale_data_symbols", []))
    rows: list[dict] = []

    for symbol in symbols:
        if symbol in stale:
            continue
        frame = snapshot["data"].get(symbol)
        if frame is None or frame.empty:
            continue
        try:
            metric = rs_engine._metrics(
                symbol,
                frame,
                rising_days=rising_days,
                calculate_ma_rising=False,
                snapshot_mode="eod",
            )
        except Exception:
            continue
        if metric:
            rows.append(metric)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.dropna(
        subset=["3M %", "6M %", "9M %", "12M %"]
    ).copy()
    df["Raw RS Score"] = (
        df["3M %"] * 0.40
        + df["6M %"] * 0.20
        + df["9M %"] * 0.20
        + df["12M %"] * 0.20
    )
    df["RS Rating"] = rs_engine._percentile_rating(df["Raw RS Score"])

    df["Pass Min Price"] = df["LTP"] >= 100.0
    df["Pass Near High"] = df["From 52W High %"] >= -5.0
    df["Pass RS"] = df["RS Rating"] >= 80
    df["Pass Minervini"] = (
        (df["LTP"] > df["50 DMA"])
        & (df["LTP"] > df["150 DMA"])
        & (df["LTP"] > df["200 DMA"])
    )
    df["Final Match"] = (
        df["Pass Min Price"]
        & df["Pass Near High"]
        & df["Pass RS"]
        & df["Pass Minervini"]
    )
    return df.set_index("Symbol", drop=False)


@pytest.mark.skipif(
    not RUN,
    reason="Set RUN_BZ_POLICY_AUDIT=1 to run this network-heavy diagnostic",
)
def test_bz_policy_impact() -> None:
    started = time.perf_counter()

    all_symbols = rs_engine.get_nse_symbols()
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
    bz_symbols = sorted(
        symbol for symbol in all_symbols
        if series_map.get(symbol) == "BZ"
    )
    eq_be_symbols = [
        symbol for symbol in all_symbols
        if symbol not in set(bz_symbols)
    ]

    snapshot = rs_engine._download_universe(
        all_symbols,
        batch_size=150,
        snapshot_mode="eod",
        force_refresh=False,
        bypass_memory_cache=False,
    )
    snapshot = nse_latest_data.patch_snapshot(snapshot)

    current = _prepare_metrics(all_symbols, snapshot)
    candidate = _prepare_metrics(eq_be_symbols, snapshot)

    common = sorted(set(current.index) & set(candidate.index))
    current_common = current.loc[common]
    candidate_common = candidate.loc[common]

    print("\n" + "=" * 82)
    print("BZ POLICY IMPACT AUDIT #14.3")
    print("=" * 82)
    print(f"NSE bhavcopy date             : {nse_date}")
    print(f"Current universe              : {len(all_symbols):,}")
    print(f"BZ symbols removed            : {len(bz_symbols):,}")
    print(f"Candidate EQ+BE universe      : {len(eq_be_symbols):,}")
    print(f"Current metric rows           : {len(current):,}")
    print(f"Candidate metric rows         : {len(candidate):,}")
    print(f"Common metric rows            : {len(common):,}")

    raw_rs_changed = 0
    if common:
        raw_rs_changed = int(
            (~current_common["Raw RS Score"].sub(
                candidate_common["Raw RS Score"]
            ).abs().le(1e-10)).sum()
        )

    rs_rating_changed = 0
    if common:
        rs_rating_changed = int(
            (current_common["RS Rating"] != candidate_common["RS Rating"]).sum()
        )

    print(f"Raw RS changes on common rows : {raw_rs_changed:,}")
    print(f"RS Rating changes             : {rs_rating_changed:,}")

    filter_names = [
        ("Min price", "Pass Min Price"),
        ("Within 5% high", "Pass Near High"),
        ("RS >= 80", "Pass RS"),
        ("Minervini", "Pass Minervini"),
        ("Final scan", "Final Match"),
    ]

    for label, column in filter_names:
        current_count = int(current[column].sum())
        candidate_count = int(candidate[column].sum())
        common_changed = 0
        if common:
            common_changed = int(
                (current_common[column] != candidate_common[column]).sum()
            )
        print(
            f"{label:<22}: current={current_count:4d} "
            f"candidate={candidate_count:4d} "
            f"common_changed={common_changed:4d}"
        )

    current_final = set(current.index[current["Final Match"]])
    candidate_final = set(candidate.index[candidate["Final Match"]])
    candidate_only = sorted(candidate_final - current_final)
    current_only = sorted(current_final - candidate_final)

    print(f"Candidate-only matches       : {len(candidate_only):,}")
    print(f"Current-only matches          : {len(current_only):,}")
    print(f"Candidate-only symbols        : {candidate_only[:50]}")
    print(f"Current-only symbols          : {current_only[:50]}")

    fno = fno_stocks.load_fno_symbols()
    current_fno = current_final & fno
    candidate_fno = candidate_final & fno
    current_main = current_final - fno
    candidate_main = candidate_final - fno

    print("\nF&O partition impact:")
    print(
        f"F&O matches                   : current={len(current_fno):,} "
        f"candidate={len(candidate_fno):,}"
    )
    print(
        f"Main Results matches          : current={len(current_main):,} "
        f"candidate={len(candidate_main):,}"
    )

    print(f"Audit elapsed seconds         : {time.perf_counter() - started:.2f}")
    print("=" * 82)

    assert len(all_symbols) >= 1000
    assert len(bz_symbols) >= 0
    assert set(candidate_final).issubset(set(eq_be_symbols))
