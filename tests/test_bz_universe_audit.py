from __future__ import annotations

import io
import os

import pandas as pd
import pytest
import requests

import rs_engine

NSE_BHAVCOPY_URLS = [
    "https://archives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv",
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv",
]

RUN = os.getenv("RUN_BZ_UNIVERSE_AUDIT") == "1"


def _fetch_latest_nse_bhavcopy() -> tuple[str, pd.DataFrame]:
    today = pd.Timestamp.now(tz="Asia/Kolkata").date()
    last_error = None

    for offset in range(0, 6):
        day = today - pd.Timedelta(days=offset)
        date_str = day.strftime("%d%m%Y")

        for template in NSE_BHAVCOPY_URLS:
            try:
                response = requests.get(
                    template.format(date=date_str),
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "text/csv,*/*",
                    },
                    timeout=20,
                )
                response.raise_for_status()

                if (
                    not response.content
                    or response.content.lstrip().startswith(b"<")
                ):
                    raise ValueError("NSE returned non-CSV content")

                frame = pd.read_csv(io.BytesIO(response.content))
                required = {"SYMBOL", "SERIES", "DATE1"}
                missing = required - set(frame.columns)
                if missing:
                    raise ValueError(
                        f"NSE bhavcopy missing columns: {sorted(missing)}"
                    )

                frame["SYMBOL"] = (
                    frame["SYMBOL"].astype("string").str.strip().str.upper()
                )
                frame["SERIES"] = (
                    frame["SERIES"].astype("string").str.strip().str.upper()
                )
                frame = frame.dropna(subset=["SYMBOL", "SERIES"])

                actual = pd.to_datetime(frame["DATE1"], errors="coerce").dropna()
                if actual.empty:
                    raise ValueError("NSE bhavcopy has no valid DATE1")

                return actual.iloc[0].date().isoformat(), frame

            except Exception as exc:
                last_error = exc

    raise RuntimeError(f"Unable to retrieve recent NSE bhavcopy: {last_error}")


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
