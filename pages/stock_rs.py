import streamlit as st
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo
import rs_engine
from nse_latest_data import install_nse_latest_close, source_check
from snapshot_cache import install as install_persistent_snapshot

install_nse_latest_close(rs_engine)
install_persistent_snapshot(rs_engine)
run_scan = rs_engine.run_scan
DEFAULT_BATCH_SIZE = rs_engine.DEFAULT_BATCH_SIZE
clear_stock_data_cache = rs_engine.clear_stock_data_cache
IST = ZoneInfo("Asia/Kolkata")
NSE_OPEN = time(9, 15)
NSE_CLOSE = time(15, 30)

if "stock_result" not in st.session_state:
    st.session_state.stock_result = None
if "stock_full_table" not in st.session_state:
    st.session_state.stock_full_table = False

@st.dialog("Reset scan")
def refresh_market_data_dialog():
    st.warning("Downloaded market data will be cleared and must be downloaded again.")
    st.write("Are you sure you want to clear the data?")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Confirm reset", type="primary", use_container_width=True, key="confirm_stock_refresh"):
            clear_stock_data_cache()
            st.session_state.stock_result = None
            st.session_state.pop("stock_stats", None)
            st.session_state.pop("source_check", None)
            st.session_state["stock_refresh_message"] = "Market data cleared."
            st.rerun()
    with c2:
        if st.button("Cancel", use_container_width=True, key="cancel_stock_refresh"):
            st.rerun()

# ... existing Stock RS UI below remains unchanged ...
