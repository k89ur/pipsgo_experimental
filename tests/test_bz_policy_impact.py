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
    all_symbols_set = set(all_symbols)
    bz_symbols = sorted(
        symbol for symbol in all_symbols
        if series_map.get(symbol) == "BZ"
    )
    bz_set = set(bz_symbols)
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
    print("BZ POLICY IMPACT AUDIT #14.7")
    print("=" * 82)
    print(f"NSE bhavcopy date             : {nse_date}")
    print(f"Current universe              : {len(all_symbols):,}")
    print(f"BZ symbols removed            : {len(bz_symbols):,}")
    print(f"Candidate EQ+BE universe      : {len(eq_be_symbols):,}")
    print(f"Current metric rows           : {len(current):,}")
    print(f"Candidate metric rows         : {len(candidate):,}")
    print(f"Common metric rows            : {len(common):,}")
    print(f"Universe symbol integrity     : {len(all_symbols_set):,} unique")

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

    invalid_current = sorted(set(current.index) - all_symbols_set)
    invalid_candidate = sorted(set(candidate.index) - all_symbols_set)
    invalid_bz = sorted(bz_set - all_symbols_set)
    invalid_candidate_universe = sorted(set(eq_be_symbols) - all_symbols_set)
    invalid_current_only = sorted(set(current_only) - all_symbols_set)
    invalid_candidate_only = sorted(set(candidate_only) - all_symbols_set)
    print(f"Invalid current symbols      : {invalid_current}")
    print(f"Invalid candidate symbols    : {invalid_candidate}")
    print(f"Invalid BZ symbols           : {invalid_bz}")
    print(f"Invalid candidate-universe   : {invalid_candidate_universe}")
    print(f"Invalid current-only         : {invalid_current_only}")
    print(f"Invalid candidate-only       : {invalid_candidate_only}")

    rating_changed_symbols = []
    if common:
        changed_mask = current_common["RS Rating"] != candidate_common["RS Rating"]
        for symbol in current_common.index[changed_mask]:
            rating_changed_symbols.append({
                "Symbol": symbol,
                "Current RS": int(current_common.loc[symbol, "RS Rating"]),
                "Candidate RS": int(candidate_common.loc[symbol, "RS Rating"]),
                "Raw RS": float(current_common.loc[symbol, "Raw RS Score"]),
            })
    rating_changed_symbols = sorted(
        rating_changed_symbols,
        key=lambda row: (abs(row["Current RS"] - row["Candidate RS"]), row["Symbol"]),
        reverse=True,
    )
    print("\\nRS Rating changes caused by removing BZ:")
    for row in rating_changed_symbols[:20]:
        print(
            f"  {row['Symbol']:<16} current={row['Current RS']:>2} "
            f"candidate={row['Candidate RS']:>2} raw_rs={row['Raw RS']:.6f}"
        )

    print("\\nCurrent-only final-match detail:")
    for symbol in current_only:
        row = current.loc[symbol]
        candidate_row = candidate.loc[symbol] if symbol in candidate.index else None
        print(
            f"  {symbol:<16} RS={int(row['RS Rating'])} "
            f"raw_rs={row['Raw RS Score']:.6f} "
            f"near_high={bool(row['Pass Near High'])} "
            f"minervini={bool(row['Pass Minervini'])} "
            f"min_price={bool(row['Pass Min Price'])}"
        )
        if candidate_row is None:
            print("    Candidate universe: excluded (BZ)")

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
    assert len(all_symbols_set) == len(all_symbols)
    assert bz_set.issubset(all_symbols_set)
    assert set(eq_be_symbols).issubset(all_symbols_set)
    assert bz_set.isdisjoint(set(eq_be_symbols))
    assert bz_set | set(eq_be_symbols) == all_symbols_set
    assert set(current.index).issubset(all_symbols_set)
    assert set(candidate.index).issubset(all_symbols_set)
    assert set(current_final).issubset(all_symbols_set)
    assert set(candidate_final).issubset(set(eq_be_symbols))
    assert not invalid_current
    assert not invalid_candidate
    assert not invalid_bz
    assert not invalid_candidate_universe
    assert not invalid_current_only
    assert not invalid_candidate_only
