import streamlit as st

WATCHLIST_KEY = "watchlist_symbols"


def _ensure():
    if WATCHLIST_KEY not in st.session_state:
        st.session_state[WATCHLIST_KEY] = []
    return st.session_state[WATCHLIST_KEY]


def get_watchlist():
    return list(_ensure())


def is_watched(symbol):
    symbol = str(symbol).strip().upper()
    return symbol in {s.upper() for s in _ensure()}


def add_stock(symbol):
    symbol = str(symbol).strip().upper()
    if symbol and not is_watched(symbol):
        _ensure().append(symbol)
    return symbol


def remove_stock(symbol):
    symbol = str(symbol).strip().upper()
    st.session_state[WATCHLIST_KEY] = [s for s in _ensure() if s.upper() != symbol]
    return symbol


def toggle_stock(symbol):
    if is_watched(symbol):
        return remove_stock(symbol), False
    return add_stock(symbol), True
