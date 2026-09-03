import streamlit as st
import pandas as pd
from rs_engine import run_scan, DEFAULT_BATCH_SIZE, clear_stock_data_cache

if "stock_result" not in st.session_state:
    st.session_state.stock_result = None

st.markdown('<div class="page-brand"><span>PIPS</span>GOX</div>', unsafe_allow_html=True)
st.markdown('<div class="page-head"><div class="page-title">Stock RS + Technical</div><div class="page-sub">IBD-style RS ranking with configurable scan filters</div></div>', unsafe_allow_html=True)

main, side = st.columns([4.7, 1.35], gap="large")
with side:
    with st.container(border=True):
        st.markdown('<div class="right-title">Scanner status</div>', unsafe_allow_html=True)
        status_slot = st.empty(); stats_slot = st.empty()

with main:
    with st.container(border=True):
        st.markdown('<div class="section-title" style="margin-top:.05rem">Scan settings</div>', unsafe_allow_html=True)
        st.markdown('<div class="help" style="margin:.05rem 0 .55rem 0">Turn a filter on to include it. Off = not applied.</div>', unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3, gap="medium")
        with c1:
            use_min_rs = st.checkbox("Minimum RS", value=True, key="stock_use_min_rs")
            min_rs = st.slider("RS threshold", 50, 99, 80, key="stock_min_rs")
            st.markdown(f'<div class="filter-state {"active" if use_min_rs else "inactive"}">{"ON" if use_min_rs else "OFF"} · RS ≥ {min_rs}</div>', unsafe_allow_html=True)
        with c2:
            use_near_high = st.checkbox("Near 52W high", value=True, key="stock_use_near_high")
            near_high = st.slider("Maximum distance (%)", 1, 25, 5, key="stock_near_high")
            st.markdown(f'<div class="filter-state {"active" if use_near_high else "inactive"}">{"ON" if use_near_high else "OFF"} · ≤ {near_high}% from 52W high</div>', unsafe_allow_html=True)
        with c3:
            use_min_price = st.checkbox("Minimum price", value=True, key="stock_use_min_price")
            min_price = st.number_input("Minimum LTP (₹)", min_value=1.0, value=100.0, step=10.0, key="stock_min_price")
            st.markdown(f'<div class="filter-state {"active" if use_min_price else "inactive"}">{"ON" if use_min_price else "OFF"} · ₹{min_price:,.0f}+</div>', unsafe_allow_html=True)

        st.markdown('<div class="trend-row">', unsafe_allow_html=True)
        t1, t2 = st.columns(2, gap="medium")
        with t1:
            use_minervini = st.checkbox("Minervini MA trend", value=True, key="stock_minervini")
            st.markdown(f'<div class="filter-state {"active" if use_minervini else "inactive"}">{"ON" if use_minervini else "OFF"} · Price &gt; 50 / 150 / 200 DMA</div>', unsafe_allow_html=True)
        with t2:
            use_ma_rising = st.checkbox("MA rising", value=False, key="stock_use_ma_rising")
            rising_days = st.slider("Rising days", 5, 40, 20, key="stock_rising_days")
            st.markdown(f'<div class="filter-state {"active" if use_ma_rising else "inactive"}>{"ON" if use_ma_rising else "OFF"} · all 3 DMAs rising for {rising_days} days</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        active_parts = []
        if use_min_rs: active_parts.append(f"RS ≥ {min_rs}")
        if use_near_high: active_parts.append(f"≤ {near_high}% from 52W high")
        if use_min_price: active_parts.append(f"₹{min_price:,.0f}+")
        if use_minervini: active_parts.append("Minervini MA")
        if use_ma_rising: active_parts.append(f"MA rising {rising_days}d")
        active_summary = "  •  ".join(active_parts) if active_parts else "No filters — full universe"
        st.markdown(f'<div class="active-summary"><span>ACTIVE FILTERS</span><strong>{active_summary}</strong></div>', unsafe_allow_html=True)
        st.markdown('<div class="settings-foot">2 years daily OHLCV · batch 100 · 52W High = highest Close in latest 252 trading rows</div>', unsafe_allow_html=True)

        st.markdown('<div class="scan-actions-title">RUN SCAN</div>', unsafe_allow_html=True)
        scan1, scan2, refresh = st.columns([1.45, 1.45, 1.55], gap="small")
        with scan1:
            run_intraday = st.button("▶  14:00 Scan", type="primary", use_container_width=True, help="Run using the day's intraday market-data snapshot.")
        with scan2:
            run_eod = st.button("▶  21:00 EOD Scan", use_container_width=True, help="Run using the completed EOD market-data snapshot.")
        with refresh:
            with st.popover("↻  Refresh Data", use_container_width=True, help="Confirm before clearing the current market-data snapshots."):
                st.markdown("**Refresh market data?**")
                st.caption("Current snapshots will be discarded. Your displayed results stay unchanged until you confirm.")
                confirm_refresh = st.button("Confirm Refresh", type="primary", use_container_width=True, key="confirm_stock_refresh")
                st.button("Cancel", use_container_width=True, key="cancel_stock_refresh")

    if confirm_refresh:
        clear_stock_data_cache()
        st.session_state.stock_result = None
        st.session_state.pop("stock_stats", None)
        st.session_state["stock_refresh_message"] = "Market-data snapshots cleared. The next scan will download fresh data."

    scan_mode = "intraday" if run_intraday else ("eod" if run_eod else None)
    if scan_mode:
        progress = status_slot.progress(0, text=f"Starting {scan_mode.upper()} scan…")
        try:
            def stock_update(done, total, message):
                pct = min(done / max(total, 1), 1.0)
                progress.progress(pct, text=f"{message} · {done:,}/{total:,}")
                stats_slot.markdown(f"<div class='rstat'><div class='rstat-label'>Progress</div><div class='rstat-value'>{pct*100:.0f}%</div></div><div class='rstat'><div class='rstat-label'>Processed</div><div class='rstat-value'>{done:,} / {total:,}</div></div>", unsafe_allow_html=True)
            result, stats = run_scan(
                min_rs=min_rs, near_high_pct=near_high, min_price=min_price, rising_days=rising_days,
                use_min_rs=use_min_rs, use_near_high=use_near_high, use_min_price=use_min_price,
                use_ma_rising=use_ma_rising, use_minervini=use_minervini, batch_size=DEFAULT_BATCH_SIZE,
                snapshot_mode=scan_mode, progress_callback=stock_update,
            )
            st.session_state.stock_result = result; st.session_state.stock_stats = stats
            progress.progress(1.0, text=f"{scan_mode.upper()} scan complete")
            stats_slot.markdown(f"<div class='rstat'><div class='rstat-label'>Status</div><div class='rstat-value score-strong'>Complete</div></div><div class='rstat'><div class='rstat-label'>Mode</div><div class='rstat-value'>{stats.get('snapshot_mode','—').upper()}</div></div><div class='rstat'><div class='rstat-label'>Matches</div><div class='rstat-value'>{len(result):,}</div></div><div class='rstat'><div class='rstat-label'>Universe</div><div class='rstat-value'>{stats.get('universe',0):,}</div></div><div class='rstat'><div class='rstat-label'>Coverage</div><div class='rstat-value'>{stats.get('coverage',0):.1f}%</div></div><div class='rstat'><div class='rstat-label'>Data</div><div class='rstat-value'>{stats.get('downloaded',0):,} / {stats.get('universe',0):,}</div></div><div class='rstat'><div class='rstat-label'>Data date</div><div class='rstat-value'>{stats.get('data_date','—')}</div></div><div class='rstat'><div class='rstat-label'>Snapshot</div><div class='rstat-value'>{stats.get('downloaded_at','—').replace('T',' ')}</div></div>", unsafe_allow_html=True)
        except Exception as e:
            progress.empty(); status_slot.error("Scan failed"); st.error(f"Stock scan failed: {e}")

    if st.session_state.get("stock_refresh_message"):
        st.info(st.session_state.pop("stock_refresh_message"))

    df = st.session_state.stock_result
    if df is None:
        stats_slot.markdown('<div class="rstat"><div class="rstat-label">Status</div><div class="rstat-value">Waiting</div></div><div class="help">Choose 14:00 Scan for the intraday snapshot or 21:00 EOD Scan for the completed daily snapshot.</div>', unsafe_allow_html=True)
        st.markdown('<div class="empty-state"><div class="empty-title">Ready to scan</div><div class="empty-sub">The scanner will evaluate the NSE universe using your selected filters.</div></div>', unsafe_allow_html=True)
    else:
        stats = st.session_state.get("stock_stats", {})
        matches = len(df); near = int((df["From 52W High %"] <= near_high).sum()) if matches and use_near_high else 0; strong = int((df["RS Rating"] >= min_rs).sum()) if matches and use_min_rs else 0
        stats_slot.markdown(f"<div class='rstat'><div class='rstat-label'>Matches</div><div class='rstat-value'>{matches:,}</div></div><div class='rstat'><div class='rstat-label'>Universe</div><div class='rstat-value'>{stats.get('universe','—')}</div></div><div class='rstat'><div class='rstat-label'>Coverage</div><div class='rstat-value'>{stats.get('coverage',0):.1f}%</div></div><div class='rstat'><div class='rstat-label'>Data</div><div class='rstat-value'>{stats.get('downloaded',0):,} / {stats.get('universe',0):,}</div></div><div class='rstat'><div class='rstat-label'>RS {min_rs}+</div><div class='rstat-value score-strong'>{strong:,}</div></div><div class='rstat'><div class='rstat-label'>Within {near_high}% of 52W high</div><div class='rstat-value'>{near:,}</div></div><div class='rstat'><div class='rstat-label'>Snapshot</div><div class='rstat-value'>{stats.get('snapshot_mode','—').upper()} · {stats.get('data_date','—')}</div></div>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">Results</div>', unsafe_allow_html=True)
        search = st.text_input("Search stocks", placeholder="Search symbol, index or industry…", label_visibility="collapsed", key="stock_search")
        view = df.copy()
        if search:
            q = search.strip(); view = view[view["Symbol"].str.contains(q, case=False, na=False) | view["Index"].str.contains(q, case=False, na=False) | view["Industry"].str.contains(q, case=False, na=False)]
        display_cols = ["Symbol", "Index", "Industry", "LTP", "RS Rating", "3M %", "6M %", "9M %", "12M %", "52W High", "From 52W High %", "TradingView"]
        shown = view[[c for c in display_cols if c in view.columns]].copy(); shown.insert(0, "S.No", range(1, len(shown) + 1))
        all_columns = list(shown.columns); saved_columns = st.session_state.get("stock_columns", all_columns); saved_columns = [c for c in saved_columns if c in all_columns] or all_columns
        shown_for_table = shown[saved_columns]
        def stock_style(row):
            styles = [""] * len(row)
            if "RS Rating" in row.index and pd.notna(row["RS Rating"]):
                score = float(row["RS Rating"]); fg = "#35d07f" if score >= 80 else ("#f3b94b" if score >= 50 else "#ff6673"); styles[row.index.get_loc("RS Rating")] = f"color:{fg};font-weight:700;"
            return styles
        st.dataframe(shown_for_table.style.apply(stock_style, axis=1), use_container_width=True, hide_index=True, height=min(700, 95 + max(len(shown_for_table),1)*36), column_config={
            "S.No": st.column_config.NumberColumn("S.NO", format="%d", width="small"), "Symbol": st.column_config.TextColumn("SYMBOL", width="medium"), "Index": st.column_config.TextColumn("INDEX", width="large"), "Industry": st.column_config.TextColumn("INDUSTRY", width="medium"), "LTP": st.column_config.NumberColumn("LTP", format="₹%.2f"), "RS Rating": st.column_config.NumberColumn("RS", format="%d", width="small"),
            "3M %": st.column_config.NumberColumn("3M", format="%.1f%%"), "6M %": st.column_config.NumberColumn("6M", format="%.1f%%"), "9M %": st.column_config.NumberColumn("9M", format="%.1f%%"), "12M %": st.column_config.NumberColumn("12M", format="%.1f%%"), "52W High": st.column_config.NumberColumn("52W HIGH", format="₹%.2f"), "From 52W High %": st.column_config.NumberColumn("DISTANCE FROM 52W HIGH", format="%.1f%%"), "TradingView": st.column_config.LinkColumn("CHART", display_text="Open ↗", width="small"),
        })
        eye_action, csv_action, action_spacer = st.columns([0.8, 1.8, 7.4])
        with eye_action:
            with st.popover(":material/visibility:", use_container_width=True):
                st.caption("Columns"); st.multiselect("Show columns", all_columns, default=saved_columns, label_visibility="collapsed", key="stock_columns")
        with csv_action:
            st.download_button("Export CSV", shown_for_table.to_csv(index=False).encode("utf-8"), "nse_stock_rs_scan.csv", "text/csv", use_container_width=True, key="stock_csv", help="Download CSV")
        st.markdown(f'<div class="table-foot">Showing {len(shown_for_table):,} of {len(df):,} matches · sorted by RS</div>', unsafe_allow_html=True)
        st.markdown('<div class="legend"><span class="dot" style="background:#35d07f"></span>RS 80–99 <span class="dot" style="background:#f3b94b"></span>RS 50–79 <span class="dot" style="background:#ff6673"></span>RS 1–49</div>',unsafe_allow_html=True)
        st.markdown('<div class="footer">RS = weighted 3M / 6M / 9M / 12M relative performance. Technical filters are optional. Minervini MA trend checks price above 50 / 150 / 200 DMA; MA rising checks can be enabled separately. Index membership and Industry are informational metadata and are not used in scan calculations.</div>', unsafe_allow_html=True)
