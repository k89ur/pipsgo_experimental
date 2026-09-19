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

    # The current Yahoo 2Y snapshot can legitimately have zero stale symbols.
    # For a controlled recovery benchmark, create the same stale condition by
    # removing the latest row from 16 representative frames. Recovery must
    # restore the real target date.
    candidates = [
        symbol for symbol, frame in data.items()
        if rs_engine._latest_date(frame) == target and len(frame) > 10
    ]
    stale = candidates[:16]
    for symbol in stale:
        data[symbol] = data[symbol].iloc[:-1].copy()

    print(f"Universe: {len(symbols):,}")
    print(f"Initial downloaded: {len(data):,}")
    print(f"Initial 2Y time: {initial_seconds:.2f}s")
    print(f"Target date: {target}")
    print(f"Synthetic stale symbols: {len(stale):,}")
