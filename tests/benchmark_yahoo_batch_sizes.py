"""Benchmark Yahoo 2Y batch sizes without changing production settings."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rs_engine


def run_batch_size(symbols: list[str], batch_size: int) -> tuple[float, float, int, int]:
    timings = []
    received = 0
    calls = 0

    for start in range(0, len(symbols), batch_size):
        group = symbols[start:start + batch_size]
        t0 = time.perf_counter()
        data = rs_engine._download_batch(group, retries=2, threads=True, period="2y")
        elapsed = time.perf_counter() - t0
        timings.append(elapsed)
        received += len(data)
        calls += 1

    total = sum(timings)
    avg = total / len(timings) if timings else 0.0
    return total, avg, max(timings, default=0.0), received, calls


def main() -> None:
    symbols = rs_engine.get_nse_symbols()
    print(f"Universe: {len(symbols):,}")
    print("Batch size | total_s | avg_batch_s | max_batch_s | received | calls")

    results = {}
    for batch_size in (100, 150, 200):
        total, avg, max_batch, received, calls = run_batch_size(symbols, batch_size)
        results[batch_size] = (total, avg, max_batch, received, calls)
        print(
            f"{batch_size:>10} | {total:>7.2f} | {avg:>11.2f} | "
            f"{max_batch:>11.2f} | {received:>8} | {calls:>5}"
        )

    expected = len(symbols)
    for batch_size, result in results.items():
        assert result[3] == expected, (
            f"{batch_size}-stock batches received {result[3]} of {expected}"
        )


if __name__ == "__main__":
    main()
