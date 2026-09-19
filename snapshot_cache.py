from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

IST = ZoneInfo("Asia/Kolkata")


@st.cache_data(show_spinner=False, persist="disk", max_entries=200)
def _cached_stock_batch(
    symbols_tuple: tuple[str, ...],
    retries: int,
    threads: bool,
    period: str,
    cache_day: str,
    _download_fn,
    _diagnostics,
) -> dict:
    """Persist one complete Yahoo batch independently of the browser session."""
    # This function body executes only on a cache miss.  Recording the miss
    # here lets the caller distinguish a persistent-cache hit from a real
    # Yahoo request without relying on Streamlit internals.
    _diagnostics["Yahoo cache misses"] = int(_diagnostics.get("Yahoo cache misses", 0)) + 1
    result = _download_fn(
        list(symbols_tuple),
        retries=retries,
        threads=threads,
        period=period,
    )
    if len(result) < len(symbols_tuple):
        raise RuntimeError("Incomplete batch; do not cache partial market data")
    return result


def install(engine_module) -> None:
    """Persist stock market-data batches while keeping the engine progress callbacks."""
    if getattr(engine_module, "_persistent_snapshot_installed", False):
        return

    original_download_batch = engine_module._download_batch
    original_download_universe = engine_module._download_universe
    original_clear_cache = engine_module.clear_stock_data_cache

    def cached_download_batch(symbols, retries=3, threads=True, period="2y"):
        symbols = list(symbols)
        if not symbols:
            return {}
        diagnostics = getattr(engine_module, "_DOWNLOAD_DIAGNOSTICS", None)
        if diagnostics is not None:
            diagnostics["Yahoo cache lookups"] = int(diagnostics.get("Yahoo cache lookups", 0)) + 1
        cache_day = f"{datetime.now(IST).date().isoformat()}:raw-adjusted-v1"
        try:
            result = _cached_stock_batch(
                tuple(symbols),
                int(retries),
                bool(threads),
                str(period),
                cache_day,
                original_download_batch,
                diagnostics,
            )
            if diagnostics is not None:
                lookups = int(diagnostics.get("Yahoo cache lookups", 0))
                misses = int(diagnostics.get("Yahoo cache misses", 0))
                diagnostics["Yahoo cache hits"] = max(0, lookups - misses)
            return result
        except RuntimeError:
            # Never persist partial batches; let the engine's recovery logic handle them.
            result = original_download_batch(
                symbols,
                retries=retries,
                threads=threads,
                period=period,
            )
            if diagnostics is not None:
                lookups = int(diagnostics.get("Yahoo cache lookups", 0))
                misses = int(diagnostics.get("Yahoo cache misses", 0))
                diagnostics["Yahoo cache hits"] = max(0, lookups - misses)
            return result

    def wrapped_download_universe(
        symbols,
        batch_size=100,
        snapshot_mode="eod",
        force_refresh=False,
        progress_callback=None,
    ):
        if force_refresh:
            _cached_stock_batch.clear()
        # The original engine owns snapshot orchestration and progress reporting.
        # Its calls to _download_batch now transparently use the persistent batch cache.
        return original_download_universe(
            symbols,
            batch_size=batch_size,
            snapshot_mode=snapshot_mode,
            force_refresh=force_refresh,
            progress_callback=progress_callback,
        )

    def clear_all_stock_data_cache():
        original_clear_cache()
        _cached_stock_batch.clear()

    diagnostics = getattr(engine_module, "_DOWNLOAD_DIAGNOSTICS", None)
    if diagnostics is not None:
        diagnostics.setdefault("Yahoo cache lookups", 0)
        diagnostics.setdefault("Yahoo cache hits", 0)
        diagnostics.setdefault("Yahoo cache misses", 0)

    engine_module._download_batch = cached_download_batch
    engine_module._download_universe = wrapped_download_universe
    engine_module.clear_stock_data_cache = clear_all_stock_data_cache
    engine_module._persistent_snapshot_installed = True
