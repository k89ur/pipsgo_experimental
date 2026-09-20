from __future__ import annotations

import os

import pandas as pd
import pytest

import nse_latest_data
import rs_engine

RUN = os.getenv("RUN_BZ_THRESHOLD_AUDIT") == "1"
TARGET = "SOMANYCERA"


def _metrics(symbols: list[str], snapshot: dict) -> pd.DataFrame:
    stale = set(snapshot.get("stale_data_symbols", []))
    rows = []
    for symbol in symbols:
        if symbol in stale:
            continue
        frame = snapshot["data"].get(symbol)
        if frame is None or frame.empty:
            continue
        try:
            row = rs_engine._metrics(
                symbol,
                frame,
                rising_days=20,
                calculate_ma_rising=False,
                snapshot_mode="eod",
            )
        except Exception:
            continue
        if row:
            rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.dropna(subset=["3M %", "6M %", "9M %", "12M %"]).copy()
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
    reason="Set RUN_BZ_THRESHOLD_AUDIT=1 to run this network diagnostic",
)
def test_bz_threshold_impact() -> None:
    universe = rs_engine.get_nse_symbols()
    _, bhavcopy = nse_latest_data._fetch_nse_bhavcopy(
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
    bz = {
        symbol for symbol in universe if series_map.get(symbol) == "BZ"
    }
    candidate_symbols = [symbol for symbol in universe if symbol not in bz]

    snapshot = rs_engine._download_universe(
        universe,
        batch_size=150,
        snapshot_mode="eod",
        force_refresh=False,
        bypass_memory_cache=False,
    )
    snapshot = nse_latest_data.patch_snapshot(snapshot)

    current = _metrics(universe, snapshot)
    candidate = _metrics(candidate_symbols, snapshot)

    common = sorted(set(current.index) & set(candidate.index))
    cur = current.loc[common]
    cand = candidate.loc[common]

    rs_changed = sorted(
        symbol for symbol in common
        if int(cur.loc[symbol, "RS Rating"]) != int(cand.loc[symbol, "RS Rating"])
    )
    rs_threshold_changed = sorted(
        symbol for symbol in common
        if bool(cur.loc[symbol, "Pass RS"]) != bool(cand.loc[symbol, "Pass RS"])
    )
    final_changed = sorted(
        symbol for symbol in common
        if bool(cur.loc[symbol, "Final Match"]) != bool(cand.loc[symbol, "Final Match"])
    )

    print("\n" + "=" * 90)
    print("BZ THRESHOLD IMPACT AUDIT #14.8")
    print("=" * 90)
    print(f"Universe                    : {len(universe):,}")
    print(f"BZ removed                  : {len(bz):,}")
    print(f"Common metric rows          : {len(common):,}")
    print(f"Raw RS changes              : {sum(abs(cur['Raw RS Score'] - cand['Raw RS Score']) > 1e-10):,}")
    print(f"RS Rating changes           : {len(rs_changed):,}")
    print(f"RS >=80 threshold changes   : {len(rs_threshold_changed):,}")
    print(f"Final-scan changes          : {len(final_changed):,}")

    print("\nExact RS >=80 threshold changes:")
    if not rs_threshold_changed:
        print("  NONE")
    else:
        for symbol in rs_threshold_changed:
            c = cur.loc[symbol]
            n = cand.loc[symbol]
            print(
                f"  {symbol:<16} "
                f"current_RS={int(c['RS Rating']):>2} "
                f"candidate_RS={int(n['RS Rating']):>2} "
                f"delta={int(n['RS Rating']) - int(c['RS Rating']):>+3} "
                f"raw_rs={float(c['Raw RS Score']):.9f} "
                f"min_price={bool(c['Pass Min Price'])} "
                f"near_high={bool(c['Pass Near High'])} "
                f"minervini={bool(c['Pass Minervini'])} "
                f"final={bool(c['Final Match'])}->{bool(n['Final Match'])}"
            )

    print("\nSOMANYCERA exact detail:")
    assert TARGET in cur.index, "SOMANYCERA missing from common metric rows"
    c = cur.loc[TARGET]
    n = cand.loc[TARGET]
    print(f"  Current RS Rating         : {int(c['RS Rating'])}")
    print(f"  Candidate RS Rating      : {int(n['RS Rating'])}")
    print(f"  RS Rating delta          : {int(n['RS Rating']) - int(c['RS Rating']):+d}")
    print(f"  Raw RS current           : {float(c['Raw RS Score']):.9f}")
    print(f"  Raw RS candidate         : {float(n['Raw RS Score']):.9f}")
    print(f"  LTP                      : {float(c['LTP']):.4f}")
    print(f"  52W High distance        : {float(c['From 52W High %']):.4f}%")
    print(f"  Min price                : {bool(c['Pass Min Price'])}")
    print(f"  Within 5% high           : {bool(c['Pass Near High'])}")
    print(f"  Minervini                : {bool(c['Pass Minervini'])}")
    print(f"  Final current -> candidate: {bool(c['Final Match'])} -> {bool(n['Final Match'])}")

    print("\nExact final-scan changes:")
    if not final_changed:
        print("  NONE")
    else:
        for symbol in final_changed:
            c = cur.loc[symbol]
            n = cand.loc[symbol]
            print(
                f"  {symbol:<16} "
                f"current_RS={int(c['RS Rating']):>2} "
                f"candidate_RS={int(n['RS Rating']):>2} "
                f"final={bool(c['Final Match'])}->{bool(n['Final Match'])}"
            )

    print("=" * 90)

    assert len(universe) >= 1000
    assert not (abs(cur["Raw RS Score"] - cand["Raw RS Score"]) > 1e-10).any()
    assert TARGET in current.index
    assert TARGET in candidate.index
