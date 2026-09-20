from __future__ import annotations

import os

import pandas as pd
import pytest

import rs_engine
from nse_latest_data import install_nse_latest_close
from snapshot_cache import install as install_persistent_snapshot


RUN = os.getenv("RUN_PRODUCTION_AUDIT") == "1"


@pytest.mark.skipif(not RUN, reason="production audit is opt-in")
def test_production_stock_rs_path():
    """
    Final production-path audit:
    - uses the same cache/EOD patch installation order as pages/stock_rs.py
    - executes a full NSE universe EOD scan
    - validates core output/data invariants
    - validates the production filter invariants
    - rebuilds through persistent Yahoo cache while bypassing only the
      in-memory snapshot cache and requires zero Yahoo downloads on the
      second pass
    """
    install_persistent_snapshot(rs_engine)
    install_nse_latest_close(rs_engine)

    # First pass: production defaults.
    df, stats = rs_engine.run_scan(
        min_rs=80,
        near_high_pct=5,
        min_price=100,
        use_min_rs=True,
        use_near_high=True,
        use_min_price=True,
        use_minervini=True,
        use_ma_rising=False,
        rising_days=20,
        batch_size=rs_engine.DEFAULT_BATCH_SIZE,
        snapshot_mode="eod",
        force_refresh=False,
        bypass_memory_cache=False,
    )

    universe = int(stats["universe"])
    downloaded = int(stats["downloaded"])
    missing_count = int(stats["missing_count"])
    usable = int(stats["usable"])

    print("\n" + "=" * 72)
    print("FINAL PRODUCTION AUDIT #16")
    print("=" * 72)
    print(f"Universe                  : {universe:,}")
    print(f"Downloaded                : {downloaded:,}")
    print(f"Missing                   : {missing_count:,}")
    print(f"Usable history            : {usable:,}")
    print(f"Coverage                  : {stats['coverage']:.2f}%")
    print(f"Data date                 : {stats['data_date']}")
    print(f"Stale symbols             : {stats['stale_data_count']:,}")
    print(f"Yahoo 10D recovery calls  : {stats['performance_timings'].get('Yahoo 10D recovery network calls', 0)}")
    print(f"Final scan rows            : {len(df):,}")

    # Universe / data integrity.
    assert universe >= 2000
    assert downloaded == universe
    assert missing_count == 0
    assert stats["data_date"] not in (None, "", "Unknown")
    assert usable > 0
    assert stats["coverage"] >= 75.0

    # The removed 10D recovery path must remain unused.
    assert int(stats["performance_timings"].get("Yahoo 10D recovery network calls", 0)) == 0

    required = {
        "Symbol",
        "LTP",
        "RS Rating",
        "Raw RS Score",
        "3M %",
        "6M %",
        "9M %",
        "12M %",
        "52W High",
        "From 52W High %",
        "50 DMA",
        "150 DMA",
        "200 DMA",
        "History Days",
    }
    assert required.issubset(df.columns)
    assert df["Symbol"].astype(str).str.strip().str.upper().is_unique
    assert not df["Symbol"].isna().any()
    assert not df["RS Rating"].isna().any()
    assert df["RS Rating"].between(1, 99).all()
    assert (df["LTP"] >= 100).all()
    assert (df["From 52W High %"] >= -5).all()
    assert (df["RS Rating"] >= 80).all()
    assert (df["LTP"] > df["50 DMA"]).all()
    assert (df["LTP"] > df["150 DMA"]).all()
    assert (df["LTP"] > df["200 DMA"]).all()
    assert (df["History Days"] >= 200).all()

    # Ranking must be ordered by RS, then raw score, as production expects.
    ranking = df[["RS Rating", "Raw RS Score"]].reset_index(drop=True)
    assert ranking["RS Rating"].is_monotonic_decreasing
    tied = ranking["RS Rating"].eq(ranking["RS Rating"].shift(1))
    if tied.any():
        tied_rows = ranking.loc[tied, "Raw RS Score"]
        previous = ranking["Raw RS Score"].shift(1).loc[tied]
        assert (previous >= tied_rows).all()

    # Second pass: same production engine, but bypass only the in-memory
    # snapshot cache. Persistent Yahoo batch cache must supply all 2Y data.
    _, cache_stats = rs_engine.run_scan(
        min_rs=80,
        near_high_pct=5,
        min_price=100,
        use_min_rs=False,
        use_near_high=False,
        use_min_price=False,
        use_minervini=False,
        use_ma_rising=False,
        rising_days=20,
        batch_size=rs_engine.DEFAULT_BATCH_SIZE,
        snapshot_mode="eod",
        force_refresh=False,
        bypass_memory_cache=True,
    )

    cache_t = cache_stats["performance_timings"]
    print(f"Persistent 2Y lookups    : {cache_t.get('Yahoo 2Y cache lookups', 0)}")
    print(f"Persistent 2Y hits       : {cache_t.get('Yahoo 2Y cache hits', 0)}")
    print(f"Persistent 2Y misses     : {cache_t.get('Yahoo 2Y cache misses', 0)}")
    print(f"Yahoo download calls     : {cache_t.get('Yahoo download calls', 0)}")

    expected_batches = (universe + rs_engine.DEFAULT_BATCH_SIZE - 1) // rs_engine.DEFAULT_BATCH_SIZE
    assert int(cache_t.get("Yahoo 2Y cache lookups", 0)) == expected_batches
    assert int(cache_t.get("Yahoo 2Y cache hits", 0)) == expected_batches
    assert int(cache_t.get("Yahoo 2Y cache misses", 0)) == 0
    assert int(cache_t.get("Yahoo download calls", 0)) == 0

    print("FINAL PRODUCTION AUDIT: ALL CHECKS PASSED")
    print("=" * 72)
