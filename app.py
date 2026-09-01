import streamlit as st
import pandas as pd
from index_rs_engine import run_index_scan

st.set_page_config(page_title="NIFTY RS", page_icon="↗", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.block-container{max-width:1150px;padding:1.6rem 1rem 3rem}
h1{letter-spacing:-1px;margin-bottom:.2rem}
[data-testid="stMetricValue"]{font-size:1.35rem}
.small{color:#777;font-size:.82rem}
</style>
""", unsafe_allow_html=True)

st.title("NIFTY Relative Strength")
st.caption("28 NIFTY indices · IBD-style RS · NIFTY 50 benchmark")

if "index_result" not in st.session_state:
    st.session_state.index_result = None

refresh = st.button("↻  Refresh RS", type="primary")

# Automatically calculate on first page load. Refresh explicitly recalculates.
if refresh or st.session_state.index_result is None:
    progress = st.progress(0, text="Connecting to NSE…")
    try:
        def update(done, total, message):
            progress.progress(min(done / max(total, 1), 1.0), text=f"{message} · {done}/{total}")
        df, stats = run_index_scan(update)
        st.session_state.index_result = df
        st.session_state.index_stats = stats
        progress.empty()
    except Exception as e:
        progress.empty()
        st.error(f"NSE data refresh failed: {e}")
        st.stop()

df = st.session_state.index_result
stats = st.session_state.get("index_stats", {})

if df is not None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Indices", stats.get("universe", 28))
    c2.metric("Calculated", stats.get("available", 0))
    asof = stats.get("as_of")
    c3.metric("Latest data", asof.strftime("%d %b %Y") if hasattr(asof, "strftime") else "—")
    c4.metric("Source", "NSE")

    st.divider()
    search = st.text_input("Search index", placeholder="BANKNIFTY, AUTO, METAL…", label_visibility="collapsed")
    view = df[df["INDEX"].str.contains(search, case=False, na=False)].copy() if search else df.copy()

    display_cols = ["Rank", "INDEX", "LTP", "RS 1-99", "Raw RS", "3M %", "6M %", "9M %", "12M %", "Status"]
    st.dataframe(
        view[display_cols],
        use_container_width=True,
        hide_index=True,
        height=min(760, 80 + len(view) * 35),
        column_config={
            "Rank": st.column_config.NumberColumn("#", width="small"),
            "LTP": st.column_config.NumberColumn("LTP", format="%.2f"),
            "RS 1-99": st.column_config.NumberColumn("RS", format="%d"),
            "Raw RS": st.column_config.NumberColumn("Raw RS", format="%.2f"),
            "3M %": st.column_config.NumberColumn("3M Rel %", format="%.2f"),
            "6M %": st.column_config.NumberColumn("6M Rel %", format="%.2f"),
            "9M %": st.column_config.NumberColumn("9M Rel %", format="%.2f"),
            "12M %": st.column_config.NumberColumn("12M Rel %", format="%.2f"),
        },
    )

    st.download_button("Export CSV", df.to_csv(index=False).encode("utf-8"), "nifty_index_rs.csv", "text/csv")
    st.caption("Formula: relative performance vs NIFTY 50, weighted 40% / 20% / 20% / 20%, then converted to 1–99 using the supplied Pine ranking logic.")
else:
    st.info("Loading NSE index data…")
