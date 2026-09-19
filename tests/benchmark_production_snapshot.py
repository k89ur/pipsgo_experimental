"""Benchmark the production EOD snapshot path at batch sizes 100 and 150.

Fresh-download benchmark only: cache is bypassed so both candidates are
measured under the same conditions. Uses the production snapshot loader,
NSE EOD close patch, and RS/technical loop. No production setting changes.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nse_latest_data
import rs_engine


def run(batch_size: int) -> dict[str, float | int]:
    rs_engine.clear_stock_data_cache()
    started = time.perf_counter()

    snapshot = rs_engine._download_universe(
        rs_engine.get_nse_symbols(),
        batch_size=batch_size,
        snapshot_mode="eod",
        force_refresh=True,
        bypass_memory_cache=True,
    )
    download_elapsed = time.perf_counter() - started

    patch_started = time.perf_counter()
    snapshot = nse_latest_data.patch_snapshot(snapshot)
    patch_elapsed = time.perf_counter() - patch_started

    stale = set(snapshot.get("stale_data_symbols", []))
    calc_started = time.perf_counter()
    rows = 0
    for symbol, frame in snapshot["data"].items():
        if symbol in stale:
            continue
        try:
            if rs_engine._metrics(
                symbol,
                frame,
                rising_days=20,
                calculate_ma_rising=False,
                snapshot_mode="eod",
            ):
                rows += 1
        except Exception:
            continue
    calc_elapsed = time.perf_counter() - calc_started

    return {
        "batch": batch_size,
        "download_seconds": download_elapsed,
        "nse_patch_seconds": patch_elapsed,
        "rs_seconds": calc_elapsed,
        "total_seconds": time.perf_counter() - started,
        "universe": snapshot["universe"],
        "downloaded": snapshot["downloaded"],
        "usable": snapshot["usable"],
        "stale": snapshot["stale_data_count"],
        "rows": rows,
    }


def main() -> None:
    results = [run(100), run(150)]

    print("\nProduction-path EOD benchmark")
    print("batch | download_s | NSE_patch_s | RS_s | total_s | downloaded | usable | stale | rows")
    for r in results:
        print(
            f"{r['batch']:>5} | {r['download_seconds']:>10.2f} | "
            f"{r['nse_patch_seconds']:>11.2f} | {r['rs_seconds']:>4.2f} | "
            f"{r['total_seconds']:>7.2f} | {r['downloaded']:>10} | "
            f"{r['usable']:>6} | {r['stale']:>5} | {r['rows']:>4}"
        )

    a, b = results
    assert a["downloaded"] == b["downloaded"], "downloaded count differs"
    assert a["usable"] == b["usable"], "usable count differs"
    assert a["rows"] == b["rows"], "metric row count differs"


if __name__ == "__main__":
    main()
