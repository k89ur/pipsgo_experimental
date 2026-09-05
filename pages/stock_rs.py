import streamlit as st
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo
import rs_engine
from nse_latest_data import install_nse_latest_close, source_check

install_nse_latest_close(rs_engine)
run_scan = rs_engine.run_scan
DEFAULT_BATCH_SIZE = rs_engine.DEFAULT_BATCH_SIZE
clear_stock_data_cache = rs_engine.clear_stock_data_cache
IST = ZoneInfo("Asia/Kolkata")
NSE_OPEN = time(9, 15)
NSE_CLOSE = time(15, 30)

if "stock_result" not in st.session_state:
    st.session_state.stock_result = None

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
        s1, s2, s3, s4 = st.columns([1.45, 1.45, 1.25, 1.35], gap="small")
        with s1:
            use_min_rs = st.checkbox("Minimum RS", value=True, key="stock_use_min_rs")
            min_rs = st.slider("RS threshold", 50, 99, 80, key="stock_min_rs", disabled=not use_min_rs)
        with s2:
            use_near_high = st.checkbox("Near 52W high", value=True, key="stock_use_near_high")
            near_high = st.slider("Maximum distance (%)", 1, 25, 5, key="stock_near_high", disabled=not use_near_high)
        with s3:
            use_min_price = st.checkbox("Minimum price", value=True, key="stock_use_min_price")
            min_price = st.number_input("Minimum LTP (₹)", min_value=1.0, value=100.0, step=10.0, key="stock_min_price", disabled=not use_min_price)
        with s4:
            use_minervini = st.checkbox("Minervini MA trend", value=True, key="stock_minervini")
            use_ma_rising = st.checkbox("MA rising", value=False, key="stock_use_ma_rising")
            rising_days = st.slider("Rising days", 5, 40, 20, key="stock_rising_days", disabled=not use_ma_rising)
        st.markdown('<div style="height:.15rem"></div>', unsafe_allow_html=True)
        scan1, scan2, refresh = st.columns([1.45, 1.45, 1.55], gap="small")
        with scan1:
            run_intraday = st.button("▶  Live Market Scan", type="primary", use_container_width=True)
        with scan2:
            run_eod = st.button("▶  After Market Scan", use_container_width=True)
        with refresh:
            if st.button("↻  Reset Scan", use_container_width=True):
                refresh_market_data_dialog()

    if st.session_state.get("stock_refresh_message"):
        st.success(st.session_state.pop("stock_refresh_message"))

    scan_mode = "intraday" if run_intraday else ("eod" if run_eod else None)
    if scan_mode == "eod":
        now_ist = datetime.now(IST)
        if now_ist.weekday() < 5 and NSE_OPEN <= now_ist.time() < NSE_CLOSE:
            st.warning("⚠️ EOD Scan is available only after the NSE market closes at 15:30 IST and before the next market open at 09:15 IST.")
            scan_mode = None

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
            progress.progress(1.0, text=f"{'LIVE MARKET SCAN' if scan_mode == 'intraday' else 'AFTER MARKET SCAN'} COMPLETE")
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
        near = int((df["From 52W High %"] <= near_high).sum()) if matches and use_near_high else 0
        strong = int((df["RS Rating"] >= min_rs).sum()) if matches and use_min_rs else 0
        stale_count = stats.get("stale_data_count", 0)
        date_status = stats.get("data_date", "—") if stale_count == 0 else f"{stats.get('data_date', '—')} · {stale_count} stale"
        stats_slot.markdown(f"<div class='rstat'><div class='rstat-label'>Matches</div><div class='rstat-value'>{matches:,}</div></div><div class='rstat'><div class='rstat-label'>Universe</div><div class='rstat-value'>{stats.get('universe','—')}</div></div><div class='rstat'><div class='rstat-label'>Coverage</div><div class='rstat-value'>{stats.get('coverage',0):.1f}%</div></div><div class='rstat'><div class='rstat-label'>Data</div><div class='rstat-value'>{stats.get('downloaded',0):,} / {stats.get('universe',0):,}</div></div><div class='rstat'><div class='rstat-label'>RS {min_rs}+</div><div class='rstat-value score-strong'>{strong:,}</div></div><div class='rstat'><div class='rstat-label'>Within {near_high}% of 52W high</div><div class='rstat-value'>{near:,}</div></div><div class='rstat'><div class='rstat-label'>Data date</div><div class='rstat-value'>{date_status}</div></div><div class='rstat'><div class='rstat-label'>Stale data</div><div class='rstat-value'>{stale_count:,} stale</div></div><div class='rstat'><div class='rstat-label'>Snapshot</div><div class='rstat-value'>{stats.get('snapshot_mode','—').upper()} · {stats.get('downloaded_at','—').replace('T',' ')}</div></div>", unsafe_allow_html=True)

        distribution = stats.get("date_distribution", {})
        stale_symbols = stats.get("stale_data_symbols", [])
        missing_symbols = stats.get("missing", [])
        short_history = stats.get("short_history", [])
        with st.expander("Data diagnostics · stale / missing / history", expanded=False):
            st.caption("Diagnostic only — these checks do not change RS calculations or technical filters.")
            d1, d2, d3 = st.columns(3)
            d1.metric("Stale", f"{stale_count:,}")
            d2.metric("Missing", f"{len(missing_symbols):,}")
            d3.metric("Short history", f"{len(short_history):,}")
            if distribution:
                st.markdown("**Latest date distribution**")
                dist_rows = [{"Date": date, "Symbols": count} for date, count in list(distribution.items())[:15]]
                st.dataframe(pd.DataFrame(dist_rows), use_container_width=True, hide_index=True)
            if stale_symbols:
                st.markdown("**Stale symbols**")
                st.code(", ".join(stale_symbols), language=None)
            if missing_symbols:
                st.markdown("**Missing symbols**")
                st.code(", ".join(missing_symbols), language=None)
            if short_history:
                st.markdown("**Short / unusable history symbols**")
                st.code(", ".join(short_history), language=None)
            if stale_symbols:
                if st.button("Run source check", key="run_stale_source_check", use_container_width=True):
                    with st.spinner("Comparing Yahoo 2Y, Yahoo 10D and NSE…"):
                        st.session_state.source_check = source_check(stats.get("snapshot", {}), stale_symbols)
                source_df = st.session_state.get("source_check")
                if source_df is not None:
                    st.dataframe(source_df, use_container_width=True, hide_index=True, column_config={"Yahoo 2Y Close": st.column_config.NumberColumn(format="₹%.2f"), "Yahoo 10D Close": st.column_config.NumberColumn(format="₹%.2f"), "NSE Close": st.column_config.NumberColumn(format="₹%.2f")})
                    st.caption("Diagnostic only — this comparison does not change the scan, snapshot, RS ranking or technical filters.")
        st.markdown('<div class="section-title">Results</div>', unsafe_allow_html=True)
        search = st.text_input("Search stocks", placeholder="Search symbol, index or industry…", label_visibility="collapsed", key="stock_search")
        view = df.copy()
        if search:
            q = search.strip()
            view = view[view["Symbol"].str.contains(q, case=False, na=False) | view["Index"].str.contains(q, case=False, na=False) | view["Industry"].str.contains(q, case=False, na=False)]
        display_cols = ["Symbol", "Index", "Industry", "LTP", "RS Rating", "3M %", "6M %", "9M %", "12M %", "52W High", "From 52W High %", "TradingView"]
        shown = view[[c for c in display_cols if c in view.columns]].copy()
        shown.insert(0, "S.No", range(1, len(shown) + 1))
        all_columns = list(shown.columns)
        saved_columns = st.session_state.get("stock_columns", all_columns)
        saved_columns = [c for c in saved_columns if c in all_columns] or all_columns
        shown_for_table = shown[saved_columns]
        def stock_style(row):
            styles = [""] * len(row)
            if "RS Rating" in row.index and pd.notna(row["RS Rating"]):
                score = float(row["RS Rating"])
                fg = "#35d07f" if score >= 80 else ("#f3b94b" if score >= 50 else "#ff6673")
                styles[row.index.get_loc("RS Rating")] = f"color:{fg};font-weight:700;"
            return styles
        st.dataframe(shown_for_table.style.apply(stock_style, axis=1), use_container_width=True, hide_index=True, height=min(700, 95 + max(len(shown_for_table),1)*36), column_config={"S.No": st.column_config.NumberColumn("S.NO", format="%d", width="small"), "Symbol": st.column_config.TextColumn("SYMBOL", width="medium"), "Index": st.column_config.TextColumn("INDEX", width="large"), "Industry": st.column_config.TextColumn("INDUSTRY", width="medium"), "LTP": st.column_config.NumberColumn("LTP", format="₹%.2f"), "RS Rating": st.column_config.NumberColumn("RS", format="%d", width="small"), "3M %": st.column_config.NumberColumn("3M", format="%.1f%%"), "6M %": st.column_config.NumberColumn("6M", format="%.1f%%"), "9M %": st.column_config.NumberColumn("9M", format="%.1f%%"), "12M %": st.column_config.NumberColumn("12M", format="%.1f%%"), "52W High": st.column_config.NumberColumn("52W HIGH", format="₹%.2f"), "From 52W High %": st.column_config.NumberColumn("DISTANCE FROM 52W HIGH", format="%.1f%%"), "TradingView": st.column_config.LinkColumn("CHART", display_text="Open ↗", width="small")})
        eye_action, csv_action, action_spacer = st.columns([0.8, 1.8, 7.4])
        with eye_action:
            with st.popover(":material/visibility:", use_container_width=True):
                st.caption("Columns")
                st.multiselect("Show columns", all_columns, default=saved_columns, label_visibility="collapsed", key="stock_columns")
        with csv_action:
            st.download_button("Export CSV", shown_for_table.to_csv(index=False).encode("utf-8"), "nse_stock_rs_scan.csv", "text/csv", use_container_width=True, key="stock_csv", help="Download CSV")
        st.markdown(f'<div class="table-foot">Showing {len(shown_for_table):,} of {len(df):,} matches · sorted by RS</div>', unsafe_allow_html=True)
        st.markdown('<div class="legend"><span class="dot" style="background:#35d07f"></span>RS 80–99 <span class="dot" style="background:#f3b94b"></span>RS 50–79 <span class="dot" style="background:#ff6673"></span>RS 1–49</div>', unsafe_allow_html=True)
        st.markdown('<div class="footer">RS = weighted 3M / 6M / 9M / 12M relative performance. Technical filters are optional. Minervini MA trend checks price above 50 / 150 / 200 DMA; MA rising checks can be enabled separately. Index membership and Industry are informational metadata and are not used in scan calculations.</div>', unsafe_allow_html=True)