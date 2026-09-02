import streamlit as st
import pandas as pd
from rs_engine import run_scan

if "stock_result" not in st.session_state:
    st.session_state.stock_result = None

st.markdown('<div class="page-brand"><span>PIPS</span>GOX</div>', unsafe_allow_html=True)
st.markdown('<div class="page-head"><div class="page-title">Stock RS + Technical</div><div class="page-sub">IBD-style RS ranking with configurable 52-week and Minervini filters</div></div>', unsafe_allow_html=True)

main, side = st.columns([4.7, 1.35], gap="large")
with side:
    with st.container(border=True):
        st.markdown('<div class="right-title">Scanner status</div>', unsafe_allow_html=True)
        status_slot = st.empty(); stats_slot = st.empty()

with main:
    with st.container(border=True):
        st.markdown('<div class="section-title" style="margin-top:.05rem">Scan settings</div>', unsafe_allow_html=True)
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: min_rs = st.slider("Minimum RS", 50, 99, 80, key="stock_min_rs")
        with c2: near_high = st.slider("Within 52W high (%)", 1, 25, 5, key="stock_near_high")
        with c3: min_price = st.number_input("Minimum price (₹)", min_value=1.0, value=100.0, step=10.0, key="stock_min_price")
        with c4: rising_days = st.slider("MA rising days", 5, 40, 20, key="stock_rising_days")
        with c5: batch_size = st.selectbox("Batch size", [10, 25, 50, 75, 100], index=2, key="stock_batch_size", help="Larger batches can be faster but may be less reliable with Yahoo Finance.")
        b1, b2 = st.columns([1, 3])
        with b1: use_minervini = st.checkbox("Minervini MA trend", value=True, key="stock_minervini")
        with b2: st.markdown('<div class="help" style="padding-top:.4rem">Price above 50 / 150 / 200 DMA and all three rising when enabled.</div>', unsafe_allow_html=True)
        run_stock = st.button("▶  Run Stock Scan", type="primary")

    if run_stock:
        progress = status_slot.progress(0, text="Starting…")
        try:
            def stock_update(done, total, message):
                pct = min(done / max(total, 1), 1.0)
                progress.progress(pct, text=f"{message} · {done:,}/{total:,}")
                stats_slot.markdown(f"<div class='rstat'><div class='rstat-label'>Progress</div><div class='rstat-value'>{pct*100:.0f}%</div></div><div class='rstat'><div class='rstat-label'>Processed</div><div class='rstat-value'>{done:,} / {total:,}</div></div>", unsafe_allow_html=True)
            result, stats = run_scan(min_rs=min_rs, near_high_pct=near_high, min_price=min_price, rising_days=rising_days, use_minervini=use_minervini, batch_size=int(batch_size), progress_callback=stock_update)
            st.session_state.stock_result = result; st.session_state.stock_stats = stats
            progress.progress(1.0, text="Scan complete")
            stats_slot.markdown(f"<div class='rstat'><div class='rstat-label'>Status</div><div class='rstat-value score-strong'>Complete</div></div><div class='rstat'><div class='rstat-label'>Matches</div><div class='rstat-value'>{len(result):,}</div></div><div class='rstat'><div class='rstat-label'>Universe</div><div class='rstat-value'>{stats.get('universe',0):,}</div></div><div class='rstat'><div class='rstat-label'>Coverage</div><div class='rstat-value'>{stats.get('coverage',0):.0f}%</div></div><div class='rstat'><div class='rstat-label'>Batch size</div><div class='rstat-value'>{int(batch_size)}</div></div>", unsafe_allow_html=True)
        except Exception as e:
            progress.empty(); status_slot.error("Scan failed"); st.error(f"Stock scan failed: {e}")

    df = st.session_state.stock_result
    if df is None:
        stats_slot.markdown('<div class="rstat"><div class="rstat-label">Status</div><div class="rstat-value">Waiting</div></div><div class="help">Configure the scan and press Run. Results will appear below.</div>', unsafe_allow_html=True)
        st.markdown('<div class="empty-state"><div class="empty-title">Ready to scan</div><div class="empty-sub">The scanner will evaluate the NSE universe using your selected RS, 52-week and trend filters.</div></div>', unsafe_allow_html=True)
    else:
        stats = st.session_state.get("stock_stats", {})
        matches = len(df); near = int((df["From 52W High %"] <= 2).sum()) if matches else 0; strong = int((df["RS Rating"] >= 80).sum()) if matches else 0
        stats_slot.markdown(f"<div class='rstat'><div class='rstat-label'>Matches</div><div class='rstat-value'>{matches:,}</div></div><div class='rstat'><div class='rstat-label'>Universe</div><div class='rstat-value'>{stats.get('universe','—')}</div></div><div class='rstat'><div class='rstat-label'>Coverage</div><div class='rstat-value'>{stats.get('coverage',0):.0f}%</div></div><div class='rstat'><div class='rstat-label'>RS 80+</div><div class='rstat-value score-strong'>{strong:,}</div></div><div class='rstat'><div class='rstat-label'>Within 2% of high</div><div class='rstat-value'>{near:,}</div></div><div class='rstat'><div class='rstat-label'>Batch size</div><div class='rstat-value'>{int(st.session_state.get('stock_batch_size',50))}</div></div>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">Results</div>', unsafe_allow_html=True)
        search = st.text_input("Search stocks", placeholder="Search symbol, index or industry…", label_visibility="collapsed", key="stock_search")
        view = df.copy()
        if search:
            q = search.strip(); view = view[view["Symbol"].str.contains(q, case=False, na=False) | view["Index"].str.contains(q, case=False, na=False) | view["Industry"].str.contains(q, case=False, na=False)]
        display_cols = ["Symbol", "Index", "Industry", "LTP", "RS Rating", "3M %", "6M %", "9M %", "12M %", "52W High", "From 52W High %", "50 DMA", "150 DMA", "200 DMA", "TradingView"]
        shown = view[[c for c in display_cols if c in view.columns]].copy()
        all_columns = list(shown.columns); saved_columns = st.session_state.get("stock_columns", all_columns); saved_columns = [c for c in saved_columns if c in all_columns] or all_columns
        shown_for_table = shown[saved_columns]

        def stock_style(row):
            styles = [""] * len(row)
            if "RS Rating" in row.index and pd.notna(row["RS Rating"]):
                score = float(row["RS Rating"]); fg = "#35d07f" if score >= 80 else ("#f3b94b" if score >= 50 else "#ff6673"); styles[row.index.get_loc("RS Rating")] = f"color:{fg};font-weight:700;"
            return styles

        st.dataframe(shown_for_table.style.apply(stock_style, axis=1), use_container_width=True, hide_index=True, height=min(700, 95 + max(len(shown_for_table),1)*36), column_config={"Symbol": st.column_config.TextColumn("SYMBOL", width="medium"), "Index": st.column_config.TextColumn("INDEX", width="large"), "Industry": st.column_config.TextColumn("INDUSTRY", width="medium"), "LTP": st.column_config.NumberColumn("LTP", format="₹%.2f"), "RS Rating": st.column_config.NumberColumn("RS", format="%d", width="small"), "3M %": st.column_config.NumberColumn("3M", format="%.1f%%"), "6M %": st.column_config.NumberColumn("6M", format="%.1f%%"), "9M %": st.column_config.NumberColumn("9M", format="%.1f%%"), "12M %": st.column_config.NumberColumn("12M", format="%.1f%%"), "52W High": st.column_config.NumberColumn("52W HIGH", format="₹%.2f"), "From 52W High %": st.column_config.NumberColumn("FROM HIGH", format="%.1f%%"), "50 DMA": st.column_config.NumberColumn("50 DMA", format="₹%.2f"), "150 DMA": st.column_config.NumberColumn("150 DMA", format="₹%.2f"), "200 DMA": st.column_config.NumberColumn("200 DMA", format="₹%.2f"), "TradingView": st.column_config.LinkColumn("CHART", display_text="Open ↗", width="small")})

        eye_action, csv_action, action_spacer = st.columns([0.8, 1.8, 7.4])
        with eye_action:
            with st.popover(":material/visibility:", use_container_width=True, help="Select columns"):
                st.caption("Columns"); st.multiselect("Show columns", all_columns, default=saved_columns, label_visibility="collapsed", key="stock_columns")
        with csv_action:
            st.download_button("Export CSV", shown_for_table.to_csv(index=False).encode("utf-8"), "nse_stock_rs_scan.csv", "text/csv", use_container_width=True, key="stock_csv", help="Download CSV")

        st.markdown(f'<div class="table-foot">Showing {len(shown_for_table):,} of {len(df):,} matches · sorted by RS</div>', unsafe_allow_html=True)
        st.markdown('<div class="legend"><span class="dot" style="background:#35d07f"></span>RS 80–99 <span class="dot" style="background:#f3b94b"></span>RS 50–79 <span class="dot" style="background:#ff6673"></span>RS 1–49</div>', unsafe_allow_html=True)
        index_status = stats.get("index_status")
        if index_status:
            st.caption(f"Index metadata diagnostic: {index_status} · Matched displayed stocks: {stats.get('index_matched', 0):,} · Parsed rows: {stats.get('index_rows', 0):,}")
        st.markdown('<div class="footer">RS = weighted 3M / 6M / 9M / 12M relative performance. Technical filter = price above 50 / 150 / 200 DMA with configurable rising-period checks. Index membership and Industry are informational metadata and are not used in scan calculations or filters.</div>', unsafe_allow_html=True)
