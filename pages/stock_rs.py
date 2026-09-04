import streamlit as st
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo
import rs_engine
from nse_latest_data import install_nse_latest_close, source_check, eod_scan_market_open

install_nse_latest_close(rs_engine)
run_scan = rs_engine.run_scan
DEFAULT_BATCH_SIZE = rs_engine.DEFAULT_BATCH_SIZE
clear_stock_data_cache = rs_engine.clear_stock_data_cache
IST = ZoneInfo("Asia/Kolkata")
NSE_OPEN = time(9, 15)
NSE_CLOSE = time(15, 30)

if "stock_result" not in st.session_state:
    st.session_state.stock_result = None

@st.dialog("Refresh market data")
def refresh_market_data_dialog():
    st.write("Clear the current market-data snapshots?")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Confirm", type="primary", use_container_width=True, key="confirm_stock_refresh"):
            clear_stock_data_cache()
            st.session_state.stock_result = None
            st.session_state.pop("stock_stats", None)
            st.session_state.pop("source_check", None)
            st.session_state["stock_refresh_message"] = "Market data cleared."
            st.rerun()
    with c2:
        if st.button("Cancel", use_container_width=True, key="cancel_stock_refresh"):
            st.rerun()

st.markdown('<div class="page-brand"><span>PIPS</span>GOX</div>', unsafe_allow_html=True)
st.markdown('<div class="page-head"><div class="page-title">Stock RS + Technical</div><div class="page-sub">IBD-style RS ranking with configurable scan filters</div></div>', unsafe_allow_html=True)

main, side = st.columns([4.7, 1.35], gap="large")
with side:
    with st.container(border=True):
        st.markdown('<div class="right-title">Scanner status</div>', unsafe_allow_html=True)
        status_slot = st.empty()
        stats_slot = st.empty()

with main:
    with st.container(border=True):
        st.markdown('<div class="section-title" style="margin-top:.05rem">Scan settings</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3, gap="medium")
        with c1:
            use_min_rs = st.checkbox("Minimum RS", value=True, key="stock_use_min_rs")
            min_rs = st.slider("RS threshold", 50, 99, 80, key="stock_min_rs", disabled=not use_min_rs)
        with c2:
            use_near_high = st.checkbox("Near 52W high", value=True, key="stock_use_near_high")
            near_high = st.slider("Maximum distance (%)", 1, 25, 5, key="stock_near_high", disabled=not use_near_high)
        with c3:
            use_min_price = st.checkbox("Minimum price", value=True, key="stock_use_min_price")
            min_price = st.number_input("Minimum LTP (₹)", min_value=1.0, value=100.0, step=10.0, key="stock_min_price", disabled=not use_min_price)
        st.markdown('<div style="height:.35rem"></div>', unsafe_allow_html=True)
        t1, t2 = st.columns(2, gap="medium")
        with t1:
            use_minervini = st.checkbox("Minervini MA trend", value=True, key="stock_minervini")
        with t2:
            use_ma_rising = st.checkbox("MA rising", value=False, key="stock_use_ma_rising")
            rising_days = st.slider("Rising days", 5, 40, 20, key="stock_rising_days", disabled=not use_ma_rising)
        st.markdown('<div style="height:.35rem"></div>', unsafe_allow_html=True)
        scan1, scan2, refresh = st.columns([1.45, 1.45, 1.55], gap="small")
        with scan1:
            run_intraday = st.button("▶  14:00 Scan", type="primary", use_container_width=True)
        with scan2:
            run_eod = st.button("▶  21:00 EOD Scan", use_container_width=True)
        with refresh:
            if st.button("↻  Refresh Data", use_container_width=True):
                refresh_market_data_dialog()

    if st.session_state.get("stock_refresh_message"):
        st.success(st.session_state.pop("stock_refresh_message"))

    scan_mode = "intraday" if run_intraday else ("eod" if run_eod else None)
    if scan_mode == "eod":
        now_ist = datetime.now(IST)
        if NSE_OPEN <= now_ist.time() < NSE_CLOSE:
            try:
                if eod_scan_market_open():
                    st.warning("⚠️ EOD Scan is unavailable while the NSE cash market is open (09:15–15:30 IST).")
                    scan_mode = None
            except Exception:
                # Let the NSE-backed engine make the final decision if the
                # market-status endpoint is temporarily unavailable.
                pass

    if scan_mode:
        progress = status_slot.progress(0, text=f"Starting {scan_mode.upper()} scan…")
        try:
            def stock_update(done, total, message):
                pct = min(done / max(total, 1), 1.0)
                progress.progress(pct, text=f"{message} · {done:,}/{total:,}")
                stats_slot.markdown(f"<div class='rstat'><div class='rstat-label'>Progress</div><div class='rstat-value'>{pct*100:.0f}%</div></div><div class='rstat'><div class='rstat-label'>Processed</div><div class='rstat-value'>{done:,} / {total:,}</div></div>", unsafe_allow_html=True)
            result, stats = run_scan(min_rs=min_rs, near_high_pct=near_high, min_price=min_price, rising_days=rising_days, use_min_rs=use_min_rs, use_near_high=use_near_high, use_min_price=use_min_price, use_ma_rising=use_ma_rising, use_minervini=use_minervini, batch_size=DEFAULT_BATCH_SIZE, snapshot_mode=scan_mode, progress_callback=stock_update)
            st.session_state.stock_result = result
            st.session_state.stock_stats = stats
            st.session_state.pop("source_check", None)
            progress.progress(1.0, text=f"{scan_mode.upper()} scan complete")
            stale_count = stats.get("stale_data_count", 0)
            date_status = stats.get("data_date", "—") if stale_count == 0 else f"{stats.get('data_date', '—')} · {stale_count} stale"
            stats_slot.markdown(f"<div class='rstat'><div class='rstat-label'>Status</div><div class='rstat-value score-strong'>Complete</div></div><div class='rstat'><div class='rstat-label'>Mode</div><div class='rstat-value'>{stats.get('snapshot_mode','—').upper()}</div></div><div class='rstat'><div class='rstat-label'>Matches</div><div class='rstat-value'>{len(result):,}</div></div><div class='rstat'><div class='rstat-label'>Universe</div><div class='rstat-value'>{stats.get('universe',0):,}</div></div><div class='rstat'><div class='rstat-label'>Coverage</div><div class='rstat-value'>{stats.get('coverage',0):.1f}%</div></div><div class='rstat'><div class='rstat-label'>Data</div><div class='rstat-value'>{stats.get('downloaded',0):,} / {stats.get('universe',0):,}</div></div><div class='rstat'><div class='rstat-label'>Data date</div><div class='rstat-value'>{date_status}</div></div><div class='rstat'><div class='rstat-label'>Snapshot</div><div class='rstat-value'>{stats.get('downloaded_at','—').replace('T',' ')}</div></div>", unsafe_allow_html=True)
            if stale_count:
                distribution = stats.get("date_distribution", {})
                if distribution:
                    with st.expander("Latest date distribution", expanded=False):
                        for date, count in list(distribution.items())[:10]:
                            st.write(f"**{date}** — {count:,}")
                        stale_symbols = stats.get("stale_data_symbols", [])
                        if stale_symbols:
                            st.caption("Stale symbols")
                            st.write(", ".join(stale_symbols))
        except Exception as e:
            progress.empty()
            status_slot.error("Scan failed")
            st.error(f"Stock scan failed: {e}")

    df = st.session_state.stock_result
    if df is None:
        status_slot.markdown('<div class="rstat"><div class="rstat-label">Status</div><div class="rstat-value">Waiting</div></div>', unsafe_allow_html=True)
    else:
        stats = st.session_state.get("stock_stats", {})
        matches = len(df)