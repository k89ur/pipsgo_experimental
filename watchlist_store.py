import json
from datetime import datetime, timedelta, timezone

import streamlit as st
from streamlit_cookies_controller import CookieController

WATCHLIST_KEY = "watchlist_symbols"
WATCHLIST_COOKIE = "pipsgo_watchlist_v1"
WATCHLIST_DAYS = 15


def _controller():
    return CookieController(key="pipsgo_watchlist_cookie")


def _now():
    return datetime.now(timezone.utc)


def _normalise_records(records):
    now = _now()
    cleaned = []
    seen = set()
    for record in records or []:
        if isinstance(record, str):
            symbol = record.strip().upper()
            added_at = now
        elif isinstance(record, dict):
            symbol = str(record.get("symbol", "")).strip().upper()
            try:
                added_at = datetime.fromisoformat(str(record.get("added_at", "")))
                if added_at.tzinfo is None:
                    added_at = added_at.replace(tzinfo=timezone.utc)
            except Exception:
                added_at = now
        else:
            continue
        if not symbol or symbol in seen:
            continue
        if now - added_at < timedelta(days=WATCHLIST_DAYS):
            cleaned.append({"symbol": symbol, "added_at": added_at.isoformat()})
            seen.add(symbol)
    return cleaned


def _save(records):
    records = _normalise_records(records)
    st.session_state[WATCHLIST_KEY] = records
    controller = _controller()
    if records:
        latest_expiry = max(
            datetime.fromisoformat(record["added_at"]).replace(tzinfo=timezone.utc)
            + timedelta(days=WATCHLIST_DAYS)
            for record in records
        )
        controller.set(
            WATCHLIST_COOKIE,
            {
                "value": json.dumps(records, separators=(",", ":")),
                "expiry_date": latest_expiry.isoformat(),
            },
        )
    else:
        controller.remove(WATCHLIST_COOKIE)
    return records


def _load():
    if WATCHLIST_KEY in st.session_state and st.session_state.get("watchlist_loaded"):
        return _normalise_records(st.session_state[WATCHLIST_KEY])

    controller = _controller()
    raw = controller.get(WATCHLIST_COOKIE)
    records = []
    if raw:
        try:
            if isinstance(raw, dict):
                raw = raw.get("value")
            records = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            records = []

    # One-time migration from the original session-only Watchlist.
    if not records and st.session_state.get(WATCHLIST_KEY):
        records = st.session_state[WATCHLIST_KEY]

    records = _normalise_records(records)
    st.session_state[WATCHLIST_KEY] = records
    st.session_state.watchlist_loaded = True
    if records:
        # Refresh the cookie after cleanup/migration while keeping each stock's own age.
        _save(records)
    elif raw:
        controller.remove(WATCHLIST_COOKIE)
    return records


def get_watchlist_records():
    return list(_load())


def get_watchlist():
    return [record["symbol"] for record in _load()]


def is_watched(symbol):
    symbol = str(symbol).strip().upper()
    return symbol in {record["symbol"] for record in _load()}


def add_stock(symbol):
    symbol = str(symbol).strip().upper()
    records = _load()
    if symbol and symbol not in {record["symbol"] for record in records}:
        records.append({"symbol": symbol, "added_at": _now().isoformat()})
        _save(records)
    return symbol


def remove_stock(symbol):
    symbol = str(symbol).strip().upper()
    records = [record for record in _load() if record["symbol"] != symbol]
    _save(records)
    return symbol


def toggle_stock(symbol):
    if is_watched(symbol):
        return remove_stock(symbol), False
    return add_stock(symbol), True
