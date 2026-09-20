from __future__ import annotations

import os

import pandas as pd
import pytest

import rs_engine

NSE_BHAVCOPY_URLS = [
    "https://archives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv",
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv",
]

RUN = os.getenv("RUN_BZ_UNIVERSE_AUDIT") == "1"


def _fetch_latest_nse_bhavcopy() -> tuple[str, pd.DataFrame]:
    # Reuse the production NSE parser/source selection so this audit measures
    # the same authoritative bhavcopy used by the scanner.
    return rs_engine._fetch_nse_bhavcopy(
        max_lookback_days=5,
        require_today=False,
        equity_only=False,
    )



@pytest.mark.skipif(
    not RUN,
    reason="Set RUN_BZ_UNIVERSE_AUDIT=1 to run this network diagnostic",
)
def test_bz_universe_membership_audit() -> None:
    universe = rs_engine.get_nse_symbols()
    nse_date, listing = _fetch_latest_nse_bhavcopy()

    universe_df = pd.DataFrame({"SYMBOL": universe})
    joined = universe_df.merge(
        listing[["SYMBOL", "SERIES"]].drop_duplicates(
            "SYMBOL", keep="last"
        ),
        on="SYMBOL",
        how="left",
        validate="one_to_one",
    )

    missing_series = joined["SERIES"].isna()
    counts = (
        joined["SERIES"]
        .fillna("MISSING")
        .value_counts()
        .sort_index()
    )

    bz = joined.loc[joined["SERIES"].eq("BZ"), "SYMBOL"].sort_values().tolist()
    be = joined.loc[joined["SERIES"].eq("BE"), "SYMBOL"].sort_values().tolist()
    eq = joined.loc[joined["SERIES"].eq("EQ"), "SYMBOL"].sort_values().tolist()

    print("\n" + "=" * 78)
    print("BZ UNIVERSE MEMBERSHIP AUDIT #14.2")
    print("=" * 78)
    print(f"Scanner universe                 : {len(universe):,}")
    print(f"NSE bhavcopy date                : {nse_date}")
    print(f"NSE bhavcopy rows                : {len(listing):,}")
    print(
        f"Universe symbols with series     : "
        f"{int((~missing_series).sum()):,}"
    )
    print(
        f"Universe symbols missing series  : "
        f"{int(missing_series.sum()):,}"
    )

    print("\nSeries distribution inside scanner universe:")
    for series, count in counts.items():
        print(f"  {series:<10}: {int(count):,}")

    print("\nRelevant series:")
    print(f"  EQ                           : {len(eq):,}")
    print(f"  BE                           : {len(be):,}")
    print(f"  BZ                           : {len(bz):,}")

    print("\nBZ symbols:")
    print(", ".join(bz) if bz else "(none)")
    print("=" * 78)

    assert len(universe) >= 1000
    assert not missing_series.any(), (
        "Scanner universe contains symbols absent from the authoritative "
        f"NSE bhavcopy: {joined.loc[missing_series, 'SYMBOL'].tolist()[:50]}"
    )
