from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

IST = ZoneInfo("Asia/Kolkata")


@st.cache_data(show_spinner="Preparing market snapshot…", persist="disk", max_entries=8)
def _cached_stock_snapshot(
    symbols_tuple: tuple[str, ...],
    batch_size: int,
    snapshot_mode: str,
    snapshot_day: str,
    _download_fn,
) -> dict:
    """Persist one complete daily market snapshot and resume through batch caches."""
    return _download_fn(
        list(symbols_tuple),
        batch_size=batch_size,
        snapshot_mode=snapshot_mode,
        force_refresh=False,
        progress_callback=None,
    )


def install(engine_module) -> None:
    """Make the stock snapshot independent of the browser session lifecycle."""
    if getattr(engine_module, "_persistent_snapshot_installed", False):
        return

    original_download_universe = engine_module._download_universe
    original_clear_cache = engine_module.clear_stock_data_cache

    def wrapped_download_universe(
        symbols,
        batch_size=100,
        snapshot_mode="eod",
        force_refresh=False,
        progress_callback=None,
    ):
        if force_refresh:
            _cached_stock_snapshot.clear()
            return original_download_universe(
                symbols,
                batch_size=batch_size,
                snapshot_mode=snapshot_mode,
                force_refresh=True,
                progress_callback=progress_callback,
            )

        mode = str(snapshot_mode).lower().strip()
        if mode not in {"intraday", "eod"}:
            mode = "eod"
        snapshot_day = datetime.now(IST).date().isoformat()
        total = len(symbols)

        if progress_callback:
            progress_callback(0, total, f"Loading saved {mode.upper()} market snapshot")

        snapshot = _cached_stock_snapshot(
            tuple(symbols),
            batch_size,
            mode,
            snapshot_day,
            original_download_universe,
        )

        if progress_callback:
            progress_callback(total, total, f"{mode.upper()} snapshot ready · reused market data")
        return snapshot

    def clear_all_stock_data_cache():
        original_clear_cache()
        _cached_stock_snapshot.clear()

    engine_module._download_universe = wrapped_download_universe
    engine_module.clear_stock_data_cache = clear_all_stock_data_cache
    engine_module._persistent_snapshot_installed = True
