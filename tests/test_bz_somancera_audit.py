from __future__ import annotations

import os

import pandas as pd
import pytest

import nse_latest_data
import rs_engine

RUN = os.getenv("RUN_BZ_SOMANCERA_AUDIT") == "1"
TARGET = "SOMANYCERA"


@pytest.mark.skipif(
    not RUN,
    reason="Set RUN_BZ_SOMANCERA_AUDIT=1 to run this network diagnostic",
)
def test_bz_somancera_classification() -> None:
    universe = rs_engine.get_nse_symbols()
    nse_date, bhavcopy = nse_latest_data._fetch_nse_bhavcopy(
        max_lookback_days=5,
        require_today=False,
        equity_only=False,
    )

    rows = bhavcopy.loc[bhavcopy["SYMBOL"].eq(TARGET)].copy()
    rows["SERIES"] = (
        rows["SERIES"].astype(str).str.strip().str.upper()
    )
    rows["CLOSE_PRICE"] = pd.to_numeric(
        rows["CLOSE_PRICE"], errors="coerce"
    )

    series_map = (
        bhavcopy[["SYMBOL", "SERIES"]]
        .drop_duplicates("SYMBOL", keep="last")
        .set_index("SYMBOL")["SERIES"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    universe_set = set(universe)
    bz_symbols = {
        symbol for symbol in universe
        if series_map.get(symbol) == "BZ"
    }
    candidate_symbols = universe_set - bz_symbols

    latest = rows.sort_values("DATE1").iloc[-1] if not rows.empty else None

    print("\n" + "=" * 88)
    print("SOMANYCERA BZ CLASSIFICATION AUDIT #14.6")
    print("=" * 88)
    print(f"NSE bhavcopy date        : {nse_date}")
    print(f"Scanner universe count   : {len(universe):,}")
    print(f"SOMANYCERA in universe    : {TARGET in universe_set}")
    print(f"SOMANYCERA row present    : {not rows.empty}")
    print(
        f"SOMANYCERA raw series     : "
        f"{sorted(rows['SERIES'].dropna().unique().tolist()) if not rows.empty else []}"
    )
    print(f"Series-map classification: {series_map.get(TARGET, 'MISSING')}")
    print(f"Classified as BZ         : {TARGET in bz_symbols}")
    print(f"Candidate EQ+BE universe : {TARGET in candidate_symbols}")

    if latest is not None:
        print(
            f"Latest NSE row           : "
            f"series={latest.get('SERIES')} "
            f"close={latest.get('CLOSE_PRICE')} "
            f"prev_close={latest.get('PREV_CLOSE')}"
        )

    print("\nAll SOMANYCERA bhavcopy rows:")
    if rows.empty:
        print("  NONE")
    else:
        cols = [
            c for c in [
                "SYMBOL", "SERIES", "DATE1", "PREV_CLOSE",
                "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE",
                "CLOSE_PRICE", "TTL_TRD_QTY",
            ] if c in rows.columns
        ]
        print(rows[cols].to_string(index=False))

    print("=" * 88)

    assert TARGET in universe_set
    assert not rows.empty
    assert TARGET not in bz_symbols
    # The earlier #14.3 output named SOMANCERA, which is not the NSE symbol
    # for Somany Ceramics.
    assert "SOMANCERA" not in universe_set
