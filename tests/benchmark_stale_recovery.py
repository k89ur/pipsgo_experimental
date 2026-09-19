"""Benchmark 5-day vs 10-day stale recovery on the same fresh 2Y snapshot."""

from __future__ import annotations

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rs_engine


def main() -> None:
    symbols = rs_engine.get_nse_symbols()
    data = {}
    started = time.perf_counter()

    for start in range(0, len(symbols), 150):
        group = symbols[start:start + 150]
        data.update(rs_engine._download_batch(group, retries=3, threads=True, period="2y"))

    initial_seconds = time.perf_counter() - started
    dates = [rs_engine._latest_date(frame) for frame in data.values()]
    dates = [d for d in dates if d]
    target = max(dates)
    stale = [s for s, frame in data.items() if rs_engine._latest_date(frame) < target]

    print(f"Universe: {len(symbols):,}")
    print(f"Initial downloaded: {len(data):,}")
    print(f"Initial 2Y time: {initial_seconds:.2f}s")
    print(f"Target date: {target}")
    print(f"Stale symbols: {len(stale):,}")
    print()
    print("Recovery window | time_s | received | exact_target_date")

    results = []
    for days in (10, 5):
        t0 = time.perf_counter()
        recovered = {}
        for start in range(0, len(stale), 50):
            recovered.update(
                rs_engine._download_batch(
                    stale[start:start + 50],
                    retries=2,
                    threads=True,
                    period=f"{days}d",
                )
            )
        elapsed = time.perf_counter() - t0
        exact = sum(
            1 for frame in recovered.values()
            if rs_engine._latest_date(frame) == target
        )
        results.append((days, elapsed, len(recovered), exact))
        print(f"{days:>14} | {elapsed:>6.2f} | {len(recovered):>8} | {exact:>17}")

    ten, five = results
    assert five[3] == ten[3], (
        f"5D exact recovery differs: 5D={five[3]} vs 10D={ten[3]}"
    )


if __name__ == "__main__":
    main()
