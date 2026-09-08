import streamlit as st
from nse_latest_data import eod_scan_market_open
from snapshot_cache import install as install_persistent_snapshot
import vcp_engine

install_persistent_snapshot(vcp_engine.rs_engine)
clear_market_data_cache = vcp_engine.rs_engine.clear_stock_data_cache

if "vcp_result" not in st.session_state:
    st.session_state.vcp_result = None
if "vcp_stats" not in st.session_state:
    st.session_state.vcp_stats = None
if "vcp_full_table" not in st.session_state:
    st.session_state.vcp_full_table = False
if "vcp_columns" not in st.session_state:
    st.session_state.vcp_columns = None

COLUMNS = [
    "Symbol", "Index", "Industry", "LTP", "VCP Score", "VCP Stage", "Contractions",
    "C1 %", "C2 %", "C3 %", "C4 %", "Final Contraction %", "Final Contraction Age",
    "Pivot", "From Pivot %", "52W High", "From 52W High %", "Avg Volume 50D",
    "Volume Contracting", "Trend OK", "Breakout", "Breakout Status", "Breakout Contractions",
    "TradingView",
]


def column_config():
    return {
        "S.No": st.column_config.NumberColumn("S.NO", format="%d", width="small"),
        "Symbol": st.column_config.TextColumn("SYMBOL"),
        "Index": st.column_config.TextColumn("INDEX"),
        "Industry": st.column_config.TextColumn("INDUSTRY"),
        "LTP": st.column_config.NumberColumn("LTP", format="₹%.2f"),
        "VCP Score": st.column_config.NumberColumn("SCORE", format="%d"),
        "VCP Stage": st.column_config.TextColumn("STAGE"),
        "Contractions": st.column_config.NumberColumn("C", format="%d"),
        "C1 %": st.column_config.NumberColumn("C1", format="%.1f%%"),
        "C2 %": st.column_config.NumberColumn("C2", format="%.1f%%"),
        "C3 %": st.column_config.NumberColumn("C3", format="%.1f%%"),
        "C4 %": st.column_config.NumberColumn("C4", format="%.1f%%"),
        "Final Contraction %": st.column_config.NumberColumn("FINAL", format="%.1f%%"),
        "Final Contraction Age": st.column_config.NumberColumn("FINAL AGE", format="%d"),
        "Pivot": st.column_config.NumberColumn("PIVOT", format="₹%.2f"),
        "From Pivot %": st.column_config.NumberColumn("PIVOT < %", format="%.1f%%"),
        "52W High": st.column_config.NumberColumn("52WH", format="₹%.2f"),
        "From 52W High %": st.column_config.NumberColumn("52WH", format="%.1f%%"),
        "Avg Volume 50D": st.column_config.NumberColumn("AVG VOL", format="%.0f"),
        "Volume Contracting": st.column_config.CheckboxColumn("VOL ↓"),
        "Trend OK": st.column_config.CheckboxColumn("TREND"),
        "Breakout": st.column_config.CheckboxColumn("BREAKOUT"),
        "Breakout Status": st.column_config.TextColumn("BREAKOUT STATUS"),
        "Breakout Contractions": st.column_config.NumberColumn("BO C", format="%d"),
        "TradingView": st.column_config.LinkColumn("CHART", display_text="Open ↗", width="small"),
    }


def visible_vcp_columns():
    saved = st.session_state.get("vcp_columns")
    return saved if saved else COLUMNS.copy()


def render_table(data, height, visible_columns=None):
    table = data[[c for c in (visible_columns or COLUMNS) if c in data.columns]].copy()
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config=column_config(),
    )


@st.dialog("Reset Market Data")
def reset_market_data_dialog():
    st.warning("Downloaded market data will be cleared and must be downloaded again.")
    st.write("Are you sure you want to reset the VCP market-data cache?")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Confirm reset", type="primary", use_container_width=True, key="confirm_vcp_reset"):
            clear_market_data_cache()
            st.session_state.vcp_result = None
            st.session_state.vcp_stats = None
            st.session_state.vcp_full_table = False
            st.session_state.vcp_columns = None
            st.session_state["vcp_reset_message"] = "Market data cleared."
            st.rerun()
    with c2:
        if st.button("Cancel", use_container_width=True, key="cancel_vcp_reset"):
            st.rerun()


@st.dialog("VCP Table Columns")
def vcp_column_selector(all_columns, saved_columns):
    st.caption("Select the columns you want to display in the VCP results table.")
    selected = []
    for col in all_columns:
        if st.checkbox(col, value=(col in saved_columns), key=f"vcp_col_select_{col}"):
            selected.append(col)
    st.divider()
    if st.button("Apply", type="primary", use_container_width=True, key="apply_vcp_columns"):
        st.session_state.vcp_columns = selected or ["Symbol"]
        st.rerun()


st.markdown('<div class="page-brand"><span>PIPS</span>GOX</div>', unsafe_allow_html=True)
st.markdown('<div class="page-head"><div class="page-title">VCP Scan</div><div class="page-sub">Volatility Contraction Pattern · swing-high / swing-low contraction analysis with volume confirmation</div></div>', unsafe_allow_html=True)

if st.session_state.vcp_full_table:
    df = st.session_state.vcp_result
    if df is None or df.empty:
        st.info("Run a VCP scan first to open the full table.")
    else:
        full = df[[c for c in visible_vcp_columns() if c in df.columns]].copy()
        full.insert(0, "S.No", range(1, len(full) + 1))
        top, close = st.columns([20, 1], gap="small")
        with close:
            if st.button("", icon=":material/fullscreen_exit:", type="tertiary", width=30, key="vcp_minimize", help="Return to scanner"):
                st.session_state.vcp_full_table = False
                st.rerun()
        st.dataframe(
            full,
            use_container_width=True,
            hide_index=True,
            height=min(900, 95 + max(len(full), 1) * 36),
            column_config=column_config(),
        )
    st.stop()

main, side = st.columns([4.7, 1.35], gap="large")
with side:
    with st.container(border=True):
        st.markdown('<div class="right-title">Scanner status</div>', unsafe_allow_html=True)
        progress_slot = st.empty()
        status_slot = st.empty()

with main:
    with st.container(border=True):
        st.markdown('<div class="section-title" style="margin-top:.05rem">VCP settings</div>', unsafe_allow_html=True)
        a, b, c, d = st.columns(4, gap="small")
        with a:
            min_c = st.slider("Minimum contractions", 2, 4, 2, key="vcp_min_c")
            max_c = st.slider("Maximum contractions", min_c, 4, 4, key="vcp_max_c")
        with b:
            first_max = st.slider("Maximum first contraction %", 5.0, 40.0, 25.0, step=1.0, key="vcp_first_max")
            final_max = st.slider("Maximum final contraction %", 1.0, 10.0, 5.0, step=.5, key="vcp_final_max")
        with c:
            final_min = st.slider("Final contraction minimum %", 0.0, 5.0, 0.0, step=.5, key="vcp_final_min")
            quality = st.selectbox("VCP quality", ["Strict", "Standard", "Loose"], index=1, key="vcp_quality")
        with d:
            volume_required = st.checkbox("Volume contraction required", True, key="vcp_volume")
            trend_filter = st.checkbox("Trend filter", True, key="vcp_trend")
            breakout = st.checkbox("Breakout already occurred", False, key="vcp_breakout")
        st.markdown('<div style="height:.15rem"></div>', unsafe_allow_html=True)
        e, f, g, h = st.columns(4, gap="small")
        with e:
            near_high = st.slider("Within 52W high %", 1.0, 15.0, 7.0, step=.5, key="vcp_near_high")
        with f:
            min_price = st.number_input("Minimum price ₹", min_value=1.0, value=100.0, step=10.0, key="vcp_min_price")
        with g:
            min_avg_volume = st.number_input("Minimum average volume", min_value=0.0, value=0.0, step=10000.0, key="vcp_min_avg_volume")
        with h:
            near_pivot = st.slider("Near pivot %", 1.0, 15.0, 5.0, step=.5, key="vcp_near_pivot")
        st.markdown('<div style="height:.15rem"></div>', unsafe_allow_html=True)
        k, l = st.columns(2, gap="small")
        with k:
            final_age_max = st.slider("Final contraction started within (trading days)", 5, 60, 20, step=1, key="vcp_final_age")
        with l:
            st.caption("Active VCP filter: the latest qualifying contraction must have started within this many trading bars.")
        st.markdown('<div style="height:.15rem"></div>', unsafe_allow_html=True)
        i, j, reset = st.columns([1.45, 1.45, 1.55], gap="small")
        with i:
            live = st.button("▶ Live Market Scan", type="primary", use_container_width=True, key="vcp_live")
        with j:
            eod = st.button("▶ After Market Scan", use_container_width=True, key="vcp_eod")
        with reset:
            if st.button("↻ Reset Market Data", use_container_width=True, key="vcp_reset"):
                reset_market_data_dialog()
        status = st.empty()

if live or eod:
    mode = "intraday" if live else "eod"
    if mode == "eod":
        try:
            if eod_scan_market_open():
                status.error("After Market Scan is unavailable while the NSE Capital Market session is running.")
                st.stop()
        except Exception as exc:
            status.error(f"Unable to verify NSE Capital Market session status. ({exc})")
            st.stop()
    progress_slot.progress(0, text="Starting VCP scan…")
    try:
        def update(done, total, label):
            progress_slot.progress(int(done / total * 100) if total else 0, text=f"{label} · {done:,}/{total:,}")

        with st.spinner("Running VCP scan…"):
            result, stats = vcp_engine.run_scan(
                min_contractions=min_c,
                max_contractions=max_c,
                first_max=first_max,
                final_max=final_max,
                final_min_tightness=final_min,
                volume_required=volume_required,
                near_high_pct=near_high,
                min_price=min_price,
                min_avg_volume=min_avg_volume,
                trend_filter=trend_filter,
                near_pivot_pct=near_pivot,
                breakout_already_occurred=breakout,
                quality=quality,
                final_contraction_max_age=final_age_max,
                batch_size=vcp_engine.DEFAULT_BATCH_SIZE,
                snapshot_mode=mode,
                progress_callback=update,
            )
        st.session_state.vcp_result = result
        st.session_state.vcp_stats = stats
        progress_slot.empty()
        status.success(f"VCP scan complete · {len(result):,} matches")
    except Exception as exc:
        progress_slot.empty()
        status.error(f"VCP scan failed: {exc}")

with main:
    df = st.session_state.vcp_result
    stats = st.session_state.vcp_stats
    if stats:
        status_slot.markdown(
            f"<div class='rstat'><div class='rstat-label'>Matches</div><div class='rstat-value'>{stats.get('matches',0):,}</div></div>"
            f"<div class='rstat'><div class='rstat-label'>Universe</div><div class='rstat-value'>{stats.get('universe',0):,}</div></div>"
            f"<div class='rstat'><div class='rstat-label'>Usable</div><div class='rstat-value'>{stats.get('usable',0):,}</div></div>"
            f"<div class='rstat'><div class='rstat-label'>Coverage</div><div class='rstat-value'>{stats.get('coverage',0):.1f}%</div></div>"
            f"<div class='rstat'><div class='rstat-label'>Data</div><div class='rstat-value'>{stats.get('data_date','—')}</div></div>"
            f"<div class='rstat'><div class='rstat-label'>Snapshot</div><div class='rstat-value'>{str(stats.get('snapshot_mode','—')).upper()}</div></div>",
            unsafe_allow_html=True,
        )
    if df is not None:
        st.markdown(f'<div class="section-title">VCP Results · {len(df):,}</div>', unsafe_allow_html=True)
        if df.empty:
            st.info("No stocks matched the current VCP settings.")
        else:
            selected_columns = visible_vcp_columns()
            tool1, tool2, tool3, spacer = st.columns([0.45, 0.45, 0.45, 18], gap="small")
            with tool1:
                if st.button("", icon=":material/view_column:", type="tertiary", width=30, key="vcp_columns", help="Select columns"):
                    vcp_column_selector(COLUMNS, selected_columns)
            with tool2:
                csv_data = df[[c for c in selected_columns if c in df.columns]].to_csv(index=False).encode("utf-8")
                st.download_button("", data=csv_data, file_name="vcp_results.csv", mime="text/csv", icon=":material/download:", type="tertiary", width=30, key="vcp_download", help="Download CSV")
            with tool3:
                if st.button("", icon=":material/fullscreen:", type="tertiary", width=30, key="vcp_full", help="Full screen view"):
                    st.session_state.vcp_full_table = True
                    st.rerun()
            view = df[[c for c in selected_columns if c in df.columns]].copy()
            st.dataframe(
                view.head(50),
                use_container_width=True,
                hide_index=True,
                height=min(650, 95 + min(len(view), 15) * 36),
                column_config=column_config(),
            )
            if len(df) > 50:
                st.caption(f"Showing top 50 of {len(df):,} matches. Use Full screen view for the complete table.")
