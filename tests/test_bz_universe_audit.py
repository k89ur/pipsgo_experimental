from __future__ import annotations

import io
import os

import pandas as pd
import requests
import pytest

import rs_engine

NSE_BHAVCOPY_URLS = [
    "https://archives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv",
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv",
]


RUN = os.getenv("RUN_BZ_UNIVERSE_AUDIT") == "1"


def _fetch_nse_equity_list() -> pd.DataFrame:
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"}
    response = requests.get(NSE_EQUITY_LIST_URL, headers=headers, timeout=30)
    response.raise_for_status()
    if not response.content:
        raise ValueError("NSE EQUITY_L.csv returned an empty response")
    frame = pd.read_csv(io.BytesIO(response.content))
    required = {"SYMBOL", "SERIES"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"NSE EQUITY_L.csv missing columns: {sorted(missing)}")
    frame["SYMBOL"] = frame["SYMBOL"].astype("string").str.strip().str.upper()
    frame["SERIES"] = frame["SERIES"].astype("string").str.strip().str.upper()
    frame = frame.dropna(subset=["SYMBOL", "SERIES"])
    return frame.drop_duplicates(subset=["SYMBOL"], keep="last")


@pytest.mark.skipif(
    not RUN,
    reason="Set RUN_BZ_UNIVERSE_AUDIT=1 to run this network diagnostic",
)
def test_bz_universe_membership_audit() -> None:
    universe = rs_engine.get_nse_symbols()
    nse_date, listing = _fetch_latest_nse_bhavcopy()

    universe_df = pd.DataFrame({"SYMBOL": universe})
    joined = universe_df.merge(
        listing[["SYMBOL", "SERIES"]].drop_duplicates("SYMBOL", keep="last"),
        on="SYMBOL",
        how="left",
        validate="one_to_one",
    )

    missing_series = joined["SERIES"].isna()
    counts = joined["SERIES"].fillna("MISSING").value_counts().sort_index()
    bz = joined.loc[joined["SERIES"].eq("BZ"), "SYMBOL"].sort_values().tolist()
    be = joined.loc[joined["SERIES"].eq("BE"), "SYMBOL"].sort_values().tolist()
    eq = joined.loc[joined["SERIES"].eq("EQ"), "SYMBOL"].sort_values().tolist()

    print("\n" + "=" * 78)
    print("BZ UNIVERSE MEMBERSHIP AUDIT #14.2")
    print("=" * 78)
    print(f"Scanner universe                 : {len(universe):,}")
    print(f"NSE bhavcopy date                : {nse_date}")\n    print(f"NSE bhavcopy rows                : {len(listing):,}")
    print(f"Universe symbols with series     : {int((~missing_series).sum()):,}")
    print(f"Universe symbols missing series  : {int(missing_series.sum()):,}")
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

    # This is an audit, not a production policy change. The key integrity
    # requirement is that every scanner-universe symbol can be classified
    # against the authoritative NSE equity list.
    assert len(universe) >= 1000
    assert not missing_series.any(), (
        "Scanner universe contains symbols absent from the authoritative "
        f"NSE equity list: {joined.loc[missing_series, 'SYMBOL'].tolist()[:50]}"
    )
