import time as perf_time
import streamlit as st
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo
import rs_engine
from nse_latest_data import install_nse_latest_close, source_check, eod_scan_market_open
from snapshot_cache import install as install_persistent_snapshot
from fno_stocks import filter_fno_results

install_persistent_snapshot(rs_engine)
install_nse_latest_close(rs_engine)
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
if "fno_result" not in st.session_state:
    st.session_state.fno_result = None
if "fno_full_table" not in st.session_state:
    st.session_state.fno_full_table = False
if "fno_error" not in st.session_state:
    st.session_state.fno_error = None

DISPLAY_COLS = ["Symbol", "Index", "Industry", "LTP", "RS Rating", "3M %", "6M %", "9M %", "12M %", "52W High", "From 52W High %", "TradingView", "GoCharting"]


def stock_style(row):
    styles = [""] * len(row)
    if "RS Rating" in row.index and pd.notna(row["RS Rating"]):
        score = float(row["RS Rating"])
        fg = "#35d07f" if score >= 80 else ("#f3b94b" if score >= 50 else "#ff6673")
        styles[row.index.get_loc("RS Rating")] = f"color:{fg};font-weight:700;"
    return styles


def stock_column_config():
    return {"S.No": st.column_config.NumberColumn("S.NO", format="%d", width="small"), "Symbol": st.column_config.TextColumn("SYMBOL"), "Index": st.column_config.TextColumn("INDEX"), "Industry": st.column_config.TextColumn("INDUSTRY"), "LTP": st.column_config.NumberColumn("LTP", format="₹%.2f"), "RS Rating": st.column_config.NumberColumn("RS", format="%d", width="small"), "3M %": st.column_config.NumberColumn("3M", format="%.1f%%"), "6M %": st.column_config.NumberColumn("6M", format="%.1f%%"), "9M %": st.column_config.NumberColumn("9M", format="%.1f%%"), "12M %": st.column_config.NumberColumn("12M", format="%.1f%%"), "52W High": st.column_config.NumberColumn("52W HIGH", format="₹%.2f"), "From 52W High %": st.column_config.NumberColumn("52WH < %", format="%.1f%%"), "TradingView": st.column_config.LinkColumn("TV", display_text="Open ↗", width="small"), "GoCharting": st.column_config.LinkColumn("GO", display_text="Open ↗", width="small")}


def style_stock_table(data):
    def color_52w_high(value):
        if pd.isna(value):
            return ""
        if float(value) > 0:
            return "color: #35d07f; font-weight: 600;"
        if float(value) < 0:
            return "color: #ff6673; font-weight: 600;"
        return ""

    if "From 52W High %" not in data.columns:
        return data.style
    return data.style.map(
        color_52w_high,
        subset=["From 52W High %"],
    )


def render_table(data, height, column_config, visible_columns=None):
    table = data.copy()
    if visible_columns:
        table = table[[c for c in visible_columns if c in table.columns]]
    st.dataframe(
        style_stock_table(table),
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config=column_config,
    )


@st.dialog("Reset scan")
def refresh_market_data_dialog():
    st.warning("Downloaded market data will be cleared and must be downloaded again.")
    st.write("Are you sure you want to clear the data?")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Confirm reset", type="primary", use_container_width=True, key="confirm_stock_refresh"):
            clear_stock_data_cache()
            st.session_state.stock_result = None
            st.session_state.fno_result = None
            st.session_state.fno_full_table = False
            st.session_state.fno_error = None
            st.session_state.pop("stock_stats", None)
            st.session_state.pop("source_check", None)
            st.session_state.pop("stock_columns", None)
            st.session_state.pop("fno_columns", None)
            st.session_state["stock_refresh_message"] = "Market data cleared."
            st.rerun()
    with c2:
        if st.button("Cancel", use_container_width=True, key="cancel_stock_refresh"):
            st.rerun()


@st.dialog("Table columns")
def stock_column_selector(all_columns, saved_columns):
    st.caption("Select the columns you want to display.")
    selected = []
    for col in all_columns:
        if st.checkbox(col, value=(col in saved_columns), key=f"stock_col_select_{col}"):
            selected.append(col)
    st.divider()
    if st.button("Apply", type="primary", use_container_width=True, key="apply_stock_columns"):
        st.session_state.stock_columns = selected or ["Symbol"]
        st.rerun()


@st.dialog("F&O table columns")
def fno_column_selector(all_columns, saved_columns):
    st.caption("Select the columns you want to display.")
    selected = []
    for col in all_columns:
        if st.checkbox(col, value=(col in saved_columns), key=f"fno_col_select_{col}"):
            selected.append(col)
    st.divider()
    if st.button("Apply", type="primary", use_container_width=True, key="apply_fno_columns"):
        st.session_state.fno_columns = selected or ["Symbol"]
        st.rerun()


def reset_stock_result_filters():
    st.session_state.stock_search = ""
    st.session_state.stock_result_index_filter = []
    st.session_state.stock_result_industry_filter = []


def reset_fno_result_filters():
    st.session_state.fno_search = ""
    st.session_state.fno_result_index_filter = []
    st.session_state.fno_result_industry_filter = []


def apply_result_filters(data, search, selected_indexes, selected_industries):
    view = data.copy()
    if search:
        q = search.strip()
        view = view[
            view["Symbol"].str.contains(q, case=False, na=False)
            | view["Index"].str.contains(q, case=False, na=False)
            | view["Industry"].str.contains(q, case=False, na=False)
        ]
    if selected_indexes:
        import re
        index_pattern = "|".join(re.escape(value) for value in selected_indexes)
        view = view[view["Index"].str.contains(index_pattern, case=False, na=False)]
    if selected_industries:
        view = view[view["Industry"].isin(selected_industries)]
    return view


def result_filter_controls(data, prefix="stock"):
    search_key = "stock_search" if prefix == "stock" else "fno_search"
    index_key = "stock_result_index_filter" if prefix == "stock" else "fno_result_index_filter"
    industry_key = "stock_result_industry_filter" if prefix == "stock" else "fno_result_industry_filter"
    reset_key = "stock_result_filter_reset" if prefix == "stock" else "fno_result_filter_reset"
    reset_callback = reset_stock_result_filters if prefix == "stock" else reset_fno_result_filters

    filter_search_col, filter_index_col, filter_industry_col, filter_reset_col = st.columns([2.8, 1.45, 1.45, 0.75], gap="small")
    with filter_search_col:
        search = st.text_input(
            "Search stocks",
            placeholder="Search symbol, index or industry…",
            label_visibility="collapsed",
            key=search_key,
        )
    index_options = sorted({value.strip() for value in data["Index"].dropna().astype(str) if value.strip()})
    industry_options = sorted({value.strip() for value in data["Industry"].dropna().astype(str) if value.strip()})
    with filter_index_col:
        selected_indexes = st.multiselect(
            "Index",
            index_options,
            placeholder="All indexes",
            label_visibility="collapsed",
            key=index_key,
        )
    with filter_industry_col:
        selected_industries = st.multiselect(
            "Industry",
            industry_options,
            placeholder="All industries",
            label_visibility="collapsed",
            key=industry_key,
        )
    with filter_reset_col:
        st.button(
            "Reset",
            use_container_width=True,
            key=reset_key,
            help="Clear search, Index and Industry filters",
            on_click=reset_callback,
        )
    return apply_result_filters(data, search, selected_indexes, selected_industries)


st.markdown('<div class="page-brand"><span>PIPS</span>GOX</div>', unsafe_allow_html=True)
st.markdown('<div class="page-head"><div class="page-title">Stock RS + Technical</div><div class="page-sub">IBD-style RS ranking with configurable scan filters</div></div>', unsafe_allow_html=True)

if st.session_state.stock_full_table:
    df = st.session_state.stock_result
    if df is None or df.empty:
        st.info("Run a Stock RS scan first to open the full table.")
        if st.button("", icon=":material/fullscreen_exit:", type="tertiary", width=30, key="stock_full_minimize_empty", help="Return to scanner"):
            st.session_state.stock_full_table = False
            st.rerun()
        st.stop()
    filtered_full = result_filter_controls(df, prefix="stock")
    full_table = filtered_full[[c for c in DISPLAY_COLS if c in filtered_full.columns]].copy()
    full_table.insert(0, "S.No", range(1, len(full_table) + 1))
    st.markdown(f'<div class="section-title">Stock RS Results · {len(filtered_full):,}</div>', unsafe_allow_html=True)
    top_spacer, minimize = st.columns([20, 1], gap="small")
    with minimize:
        if st.button("", icon=":material/fullscreen_exit:", type="tertiary", width=30, key="stock_full_minimize", help="Return to scanner"):
            st.session_state.stock_full_table = False
            st.rerun()
    render_table(full_table, min(900, 95 + max(len(full_table), 1) * 36), stock_column_config())
    st.stop()

if st.session_state.fno_full_table:
    fno_df = st.session_state.fno_result
    if fno_df is None:
        st.info("Run a Stock RS scan first to open the F&O table.")
        if st.button("", icon=":material/fullscreen_exit:", type="tertiary", width=30, key="fno_full_minimize_empty", help="Return to scanner"):
            st.session_state.fno_full_table = False
            st.rerun()
        st.stop()
    filtered_fno = result_filter_controls(fno_df, prefix="fno")
    fno_full = filtered_fno[[c for c in DISPLAY_COLS if c in filtered_fno.columns]].copy()
    fno_full.insert(0, "S.No", range(1, len(fno_full) + 1))
    st.markdown(f'<div class="section-title">F&O Results · {len(filtered_fno):,}</div>', unsafe_allow_html=True)
    top_spacer, minimize = st.columns([20, 1], gap="small")
    with minimize:
        if st.button("", icon=":material/fullscreen_exit:", type="tertiary", width=30, key="fno_full_minimize", help="Return to scanner"):
            st.session_state.fno_full_table = False
            st.rerun()
    if fno_full.empty:
        st.markdown('<div class="section-title">F&O Results · 0</div>', unsafe_allow_html=True)
        st.info("No F&O stocks from the current scan results.")
    else:
        render_table(fno_full, min(900, 95 + max(len(fno_full), 1) * 36), stock_column_config())
    st.stop()

main, side = st.columns([4.7, 1.35], gap="large")
with side:
    with st.container(border=True):
        st.markdown('<div class="right-title">Scanner status</div>', unsafe_allow_html=True)
        scan_mode_slot = st.empty()
        stage_slot = st.empty()
        progress_slot = st.empty()
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
            scan_live = st.button("▶ Live Market Scan", type="primary", use_container_width=True, key="stock_live_scan")
        with scan2:
            scan_eod = st.button("▶ After Market Scan", use_container_width=True, key="stock_eod_scan")
        with refresh:
            if st.button("↻ Reset Scan", use_container_width=True, key="stock_refresh"):
                refresh_market_data_dialog()
        status = st.empty()

if scan_live or scan_eod:
    mode = "intraday" if scan_live else "eod"
    if mode == "eod":
        try:
            if eod_scan_market_open():
                status.error("After Market Scan is unavailable while the NSE Capital Market session is running.")
                st.stop()
        except Exception as e:
            status.error(f"Unable to verify NSE Capital Market session status. After Market Scan is blocked for safety. ({e})")
            st.stop()
    stage_total = 5 if mode == "eod" else 3
    scan_name = "AFTER MARKET SCAN" if mode == "eod" else "LIVE MARKET SCAN"
    scan_subtitle = "EOD snapshot · NSE official close" if mode == "eod" else "Daily market snapshot"
    scan_mode_slot.markdown(
        f"<div style='font-size:.78rem;font-weight:800;letter-spacing:.04em;'>● {scan_name}</div>"
        f"<div style='font-size:.67rem;opacity:.68;margin-top:.08rem;'>{scan_subtitle}</div>",
        unsafe_allow_html=True,
    )
    stage_slot.markdown(
        f"<div style='font-size:.72rem;font-weight:700;margin-top:.45rem;'>Stage 1 of {stage_total}</div>"
        f"<div style='font-size:.68rem;opacity:.72;'>Preparing scanner…</div>",
        unsafe_allow_html=True,
    )
    progress_slot.progress(0, text=f"{scan_name} · Starting…")
    try:
        scan_wall_started = perf_time.perf_counter()

        def stock_update(done, total, label):
            text = str(label)
            lower = text.lower()
            if "calculating rs" in lower:
                stage = stage_total if mode == "eod" else 2
                base, span = (90, 8) if mode == "eod" else (72, 25)
                stage_name = "Calculating RS & technical filters"
            elif "applying nse eod closes" in lower:
                stage, base, span, stage_name = 4, 80, 10, "Applying NSE EOD closes"
            elif "recent reference data" in lower or "nse stage" in lower:
                stage, base, span, stage_name = 3, 65, 15, "Loading recent reference data"
            elif "nse bhavcopy" in lower:
                stage, base, span, stage_name = 2, 60, 5, "Loading latest NSE bhavcopy"
            elif "recovering" in lower:
                stage, base, span, stage_name = 1, 52, 8, "Recovering stale market data"
            elif "snapshot ready" in lower:
                stage, base, span, stage_name = 1, 60, 0, "Market data ready"
            else:
                stage, base, span, stage_name = 1, 0, 60, "Loading market data"
            if mode == "intraday" and stage == 3 and "calculating" not in lower:
                stage, base, span, stage_name = 2, 72, 0, "Preparing results"
            fraction = (done / total) if total else 0
            pct = min(99, int(base + span * fraction)) if span else base
            if "calculating rs" in lower and done >= total:
                pct = 98 if mode == "eod" else 97
            if "nse bhavcopy" in lower and done >= total:
                pct = 65
            stage_slot.markdown(
                f"<div style='font-size:.72rem;font-weight:700;margin-top:.45rem;'>Stage {stage} of {stage_total}</div>"
                f"<div style='font-size:.68rem;opacity:.72;'>{stage_name}</div>",
                unsafe_allow_html=True,
            )
            progress_slot.progress(pct, text=f"{scan_name} · {text}")
        with st.spinner("Running stock scan…"):
            scan_df, stats = run_scan(min_rs=min_rs, near_high_pct=near_high, min_price=min_price, use_minervini=use_minervini, use_ma_rising=use_ma_rising, rising_days=rising_days, batch_size=DEFAULT_BATCH_SIZE, snapshot_mode=mode, progress_callback=stock_update, use_min_rs=use_min_rs, use_near_high=use_near_high, use_min_price=use_min_price)
        total_matches = len(scan_df)
        stage_slot.markdown(
            f"<div style='font-size:.72rem;font-weight:700;margin-top:.45rem;'>Stage {stage_total} of {stage_total}</div>"
            f"<div style='font-size:.68rem;opacity:.72;'>Preparing final results…</div>",
            unsafe_allow_html=True,
        )
        progress_slot.progress(99, text=f"{scan_name} · Preparing final results…")
        performance_timings = dict(stats.get("performance_timings", {}))
        fno_started = perf_time.perf_counter()
        try:
            fno_df = filter_fno_results(scan_df)
            fno_symbols = set(fno_df["Symbol"].astype(str).str.strip().str.upper()) if fno_df is not None and not fno_df.empty else set()
            df = scan_df.loc[~scan_df["Symbol"].astype(str).str.strip().str.upper().isin(fno_symbols)].copy()
            st.session_state.fno_result = fno_df
            st.session_state.fno_error = None
        except Exception:
            df = scan_df.copy()
            st.session_state.fno_result = pd.DataFrame()
            st.session_state.fno_error = "F&O list is currently unavailable. Main Results are unaffected."
        performance_timings["F&O partition + result preparation"] = perf_time.perf_counter() - fno_started
        performance_timings["Stock RS scan wall time"] = perf_time.perf_counter() - scan_wall_started
        stats["performance_timings"] = performance_timings
        st.session_state.stock_result = df
        st.session_state.stock_stats = stats
        st.session_state.stock_stats["total_matches"] = total_matches
        st.session_state.fno_full_table = False
        st.session_state.pop("fno_columns", None)
        progress_slot.progress(100, text=f"{scan_name} · Scan complete")
        stage_slot.markdown(
            f"<div style='font-size:.72rem;font-weight:700;margin-top:.45rem;'>✓ {scan_name} COMPLETE</div>"
            f"<div style='font-size:.68rem;opacity:.72;'>Results are ready.</div>",
            unsafe_allow_html=True,
        )
    except Exception as e:
        progress_slot.empty()
        scan_mode_slot.markdown(
            f"<div style='font-size:.78rem;font-weight:800;letter-spacing:.04em;'>⚠ {scan_name}</div>"
            f"<div style='font-size:.67rem;opacity:.68;margin-top:.08rem;'>Scan failed</div>",
            unsafe_allow_html=True,
        )
        stage_slot.empty()
        message = str(e)
        if mode == "eod" and "Today's NSE EOD bhavcopy is not available yet" in message:
            status.warning("After Market Scan data is not available yet. NSE has not published today's EOD market data. Please try again after the EOD data is released.")
        else:
            status.error(f"Stock scan failed: {e}")
        st.stop()

with main:
    stats = st.session_state.get("stock_stats")
    df = st.session_state.stock_result
    if stats and df is not None:
        matches = stats.get("total_matches", len(df))
        coverage = stats.get("coverage", 0.0)
        near = int((df["From 52W High %"] <= near_high).sum()) if matches and use_near_high else 0
        fno_df = st.session_state.get("fno_result")
        fno_count = len(fno_df) if fno_df is not None else 0
        stale_count = stats.get("stale_data_count", 0)
        date_status = stats.get("data_date", "—") if stale_count == 0 else f"{stats.get('data_date', '—')} · {stale_count} stale"
        status_slot.markdown(f"<div class='rstat'><div class='rstat-label'>Matches</div><div class='rstat-value'>{matches:,}</div></div><div class='rstat'><div class='rstat-label'>Universe</div><div class='rstat-value'>{stats.get('universe','—')}</div></div><div class='rstat'><div class='rstat-label'>Coverage</div><div class='rstat-value'>{stats.get('coverage',0):.1f}%</div></div><div class='rstat'><div class='rstat-label'>Data</div><div class='rstat-value'>{stats.get('downloaded',0):,} / {stats.get('universe',0):,}</div></div><div class='rstat'><div class='rstat-label'>F&O Stocks</div><div class='rstat-value'>{fno_count:,}</div></div><div class='rstat'><div class='rstat-label'>Within {near_high}% of 52W high</div><div class='rstat-value'>{near:,}</div></div><div class='rstat'><div class='rstat-label'>Data date</div><div class='rstat-value'>{date_status}</div></div><div class='rstat'><div class='rstat-label'>Stale data</div><div class='rstat-value'>{stale_count:,} stale</div></div><div class='rstat'><div class='rstat-label'>Snapshot</div><div class='rstat-value'>{stats.get('snapshot_mode','—').upper()} · {stats.get('downloaded_at','—').replace('T',' ')}</div></div>", unsafe_allow_html=True)
        distribution = stats.get("date_distribution", {})
        stale_symbols = stats.get("stale_data_symbols", [])
        missing_symbols = stats.get("missing", [])
        short_history = stats.get("short_history", [])
        with st.expander("Data diagnostics · stale / missing / history", expanded=False):
            st.caption("Diagnostic only — these checks do not change RS calculations or technical filters.")
            performance_timings = stats.get("performance_timings", {})
            if st.button(
                "Test persistent Yahoo cache",
                key="stock_persistent_cache_test",
                use_container_width=True,
                help="Rebuild the market-data snapshot while bypassing only the in-memory snapshot cache. Persistent Yahoo batch cache is preserved.",
            ):
                test_mode = str(stats.get("snapshot_mode", "eod")).lower()
                with st.spinner("Testing persistent Yahoo cache…"):
                    try:
                        _, cache_test_stats = run_scan(
                            min_rs=min_rs,
                            near_high_pct=near_high,
                            min_price=min_price,
                            use_minervini=use_minervini,
                            use_ma_rising=use_ma_rising,
                            rising_days=rising_days,
                            batch_size=DEFAULT_BATCH_SIZE,
                            snapshot_mode=test_mode,
                            force_refresh=False,
                            bypass_memory_cache=True,
                            use_min_rs=use_min_rs,
                            use_near_high=use_near_high,
                            use_min_price=use_min_price,
                        )
                        st.session_state["stock_cache_test_stats"] = cache_test_stats
                    except Exception as exc:
                        st.session_state["stock_cache_test_error"] = str(exc)
                st.rerun()

            cache_test_stats = st.session_state.get("stock_cache_test_stats")
            cache_test_error = st.session_state.get("stock_cache_test_error")
            if cache_test_error:
                st.error(f"Persistent cache test failed: {cache_test_error}")
            if cache_test_stats:
                cache_test_timings = cache_test_stats.get("performance_timings", {})
                cache_rows = []
                for label in [
                    "Yahoo 2Y batches",
                    "Yahoo 2Y cache lookups",
                    "Yahoo 2Y cache hits",
                    "Yahoo 2Y cache misses",
                    "Yahoo cache lookups",
                    "Yahoo cache hits",
                    "Yahoo cache misses",
                    "Yahoo download calls",
                    "Yahoo 10D recovery batches",
                    "Yahoo 10D recovery symbols requested",
                    "Yahoo 10D recovery symbols received",
                ]:
                    value = cache_test_timings.get(label)
                    if value is not None:
                        cache_rows.append({"Metric": label, "Value": value})
                if cache_rows:
                    st.markdown("**Persistent cache test result**")
                    st.dataframe(pd.DataFrame(cache_rows), use_container_width=True, hide_index=True)
                    st.caption("Diagnostic only. The test bypasses the in-memory snapshot cache but preserves the persistent Yahoo batch cache and does not replace the displayed scan results.")

            if performance_timings:
                st.markdown("**Performance timing · Audit #12.2**")
                timing_rows = []
                timing_order = [
                    "NSE universe",
                    "Market data snapshot",
                    "Yahoo 2Y / snapshot download",
                    "Yahoo batch avg seconds",
                    "Yahoo batch min seconds",
                    "Yahoo batch max seconds",
                    "Yahoo request time",
                    "Adjusted reconstruction time",
                    "Stale-data recovery",
                    "Yahoo 10D recovery request time",
                    "Yahoo 10D recovery reconstruction time",
                    "NSE bhavcopy",
                    "Yahoo 10D reference",
                    "Apply NSE closes",
                    "Snapshot diagnostics refresh",
                    "RS & technical loop",
                    "RS scoring & filters",
                    "Index / Industry metadata",
                    "F&O partition + result preparation",
                    "Scan total (backend)",
                    "Stock RS scan wall time",
                ]
                for label in timing_order:
                    value = performance_timings.get(label)
                    if isinstance(value, (int, float)):
                        timing_rows.append({"Stage": label, "Time (s)": round(float(value), 3)})
                if timing_rows:
                    st.dataframe(pd.DataFrame(timing_rows), use_container_width=True, hide_index=True)
                extra_rows = []
                for label in ["Yahoo 2Y batches", "Yahoo 2Y cache lookups", "Yahoo 2Y cache hits", "Yahoo 2Y cache misses", "Yahoo 10D cache lookups", "Yahoo 10D cache hits", "Yahoo 10D cache misses", "Yahoo 10D recovery network calls", "Yahoo cache lookups", "Yahoo cache hits", "Yahoo cache misses", "Yahoo download calls", "Yahoo symbols processed", "Yahoo 10D recovery batches", "Yahoo 10D recovery symbols requested", "Yahoo 10D recovery symbols received", "Yahoo 10D reference batches", "Yahoo 10D symbols requested", "Yahoo 10D symbols received", "Stale symbols recovered", "Stale depth 1 session", "Stale depth 2 sessions", "Stale depth 3 sessions", "Stale depth 4 sessions", "Stale depth 5 sessions", "Stale depth 6+ sessions", "Stale depth max sessions", "Recovery shadow comparable", "Recovery shadow Raw RS changed", "Recovery shadow max Raw RS diff", "Recovery shadow RS Rating changed", "Recovery shadow max RS Rating diff", "Recovery shadow non-comparable current-only", "Recovery shadow non-comparable candidate-only", "Recovery shadow non-comparable both", "Recovery shadow non-comparable symbols", "Recovery shadow comparison", "NSE closes applied", "NSE adjustment factors"]:
                    value = performance_timings.get(label)
                    if value is not None:
                        extra_rows.append({"Metric": label, "Value": value})
                if extra_rows:
                    st.dataframe(pd.DataFrame(extra_rows), use_container_width=True, hide_index=True)
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
        view = result_filter_controls(df, prefix="stock")
        shown = view[[c for c in DISPLAY_COLS if c in view.columns]].copy()
        shown.insert(0, "S.No", range(1, len(shown) + 1))
        all_columns = list(shown.columns)
        saved_columns = st.session_state.get("stock_columns", all_columns)
        saved_columns = [c for c in saved_columns if c in all_columns] or all_columns
        # Migration: GoCharting was added after older saved column selections.
        if "GoCharting" in all_columns and "GoCharting" not in saved_columns:
            if "TradingView" in saved_columns:
                saved_columns.insert(saved_columns.index("TradingView") + 1, "GoCharting")
            else:
                saved_columns.append("GoCharting")
        shown_for_table = shown[saved_columns]
        full_table = df[[c for c in DISPLAY_COLS if c in df.columns]].copy()
        full_table.insert(0, "S.No", range(1, len(full_table) + 1))
        st.markdown('<div class="table-action-row">', unsafe_allow_html=True)
        action_spacer, view_action, download_action, full_action = st.columns([9.25, 0.42, 0.42, 0.42], gap="small")
        with view_action:
            if st.button("", icon=":material/view_column:", type="tertiary", width=28, key="stock_column_view", help="View columns"):
                stock_column_selector(all_columns, saved_columns)
        with download_action:
            st.download_button("", full_table.to_csv(index=False).encode("utf-8"), "nse_stock_rs_scan.csv", icon=":material/download:", type="tertiary", width=28, key="stock_download_csv", help="Download full table CSV")
        with full_action:
            if st.button("", icon=":material/fullscreen:", type="tertiary", width=28, key="stock_fullscreen_action", help="Full table view"):
                st.session_state.stock_full_table = True
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        render_table(shown, min(700, 95 + max(len(shown),1)*36), stock_column_config(), saved_columns)
        st.markdown(f'<div class="table-foot">Showing {len(shown):,} of {len(df):,} matches · sorted by RS</div>', unsafe_allow_html=True)

        fno_df = st.session_state.get("fno_result")
        st.markdown(f'<div class="section-title">F&O Results · {len(fno_df):,}</div>' if fno_df is not None else '<div class="section-title">F&O Results · —</div>', unsafe_allow_html=True)
        if st.session_state.get("fno_error"):
            st.warning(st.session_state.fno_error)
        elif fno_df is None:
            st.info("F&O Results will appear after the next scan.")
        elif fno_df.empty:
            st.info("No F&O stocks from the current scan results.")
        else:
            fno_display = fno_df[[c for c in DISPLAY_COLS if c in fno_df.columns]].copy()
            fno_display.insert(0, "S.No", range(1, len(fno_display) + 1))
            fno_all_columns = list(fno_display.columns)
            fno_saved_columns = st.session_state.get("fno_columns", fno_all_columns)
            fno_saved_columns = [c for c in fno_saved_columns if c in fno_all_columns] or fno_all_columns
            # Migration: GoCharting was added after older saved F&O column selections.
            if "GoCharting" in fno_all_columns and "GoCharting" not in fno_saved_columns:
                if "TradingView" in fno_saved_columns:
                    fno_saved_columns.insert(fno_saved_columns.index("TradingView") + 1, "GoCharting")
                else:
                    fno_saved_columns.append("GoCharting")
            fno_full_table = fno_df[[c for c in DISPLAY_COLS if c in fno_df.columns]].copy()
            fno_full_table.insert(0, "S.No", range(1, len(fno_full_table) + 1))
            st.markdown('<div class="table-action-row">', unsafe_allow_html=True)
            fno_spacer, fno_view_action, fno_download_action, fno_full_action = st.columns([9.25, 0.42, 0.42, 0.42], gap="small")
            with fno_view_action:
                if st.button("", icon=":material/view_column:", type="tertiary", width=28, key="fno_column_view", help="View F&O columns"):
                    fno_column_selector(fno_all_columns, fno_saved_columns)
            with fno_download_action:
                st.download_button("", fno_full_table.to_csv(index=False).encode("utf-8"), "nse_fno_stock_rs_scan.csv", icon=":material/download:", type="tertiary", width=28, key="fno_download_csv", help="Download full F&O table CSV")
            with fno_full_action:
                if st.button("", icon=":material/fullscreen:", type="tertiary", width=28, key="fno_fullscreen_action", help="Full F&O table view"):
                    st.session_state.fno_full_table = True
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            render_table(fno_display, min(700, 95 + max(len(fno_display),1)*36), stock_column_config(), fno_saved_columns)
            st.markdown(f'<div class="table-foot">Showing {len(fno_display):,} of {len(fno_df):,} F&O matches · same RS order as Main Results</div>', unsafe_allow_html=True)

        st.markdown('<div class="legend"><span class="dot" style="background:#35d07f"></span>RS 80–99 <span class="dot" style="background:#f3b94b"></span>RS 50–79 <span class="dot" style="background:#ff6673"></span>RS 1–49</div>', unsafe_allow_html=True)
        st.markdown('<div class="footer">RS = weighted 3M / 6M / 9M / 12M relative performance. Technical filters are optional. Minervini MA trend checks price above 50 / 150 / 200 DMA; MA rising checks can be enabled separately. Index membership and Industry are informational metadata and are not used in scan calculations.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="empty-state"><div class="empty-title">No scan results yet</div><div class="empty-sub">Run a Live Market Scan or After Market Scan to populate the stock ranking.</div></div>', unsafe_allow_html=True)