import streamlit as st
import pandas as pd
from rs_engine import run_scan

st.set_page_config(page_title="NSE RS Scanner", page_icon="↗", layout="wide")

st.markdown("""
<style>
.block-container {max-width: 1200px; padding-top: 2rem;}
h1 {letter-spacing:-1px;}
[data-testid="stMetricValue"] {font-size: 1.35rem;}
.small {color:#777; font-size:.85rem;}
</style>
""", unsafe_allow_html=True)

st.title("NSE Relative Strength")
st.caption("IBD-style relative strength ranking • NSE equities • simple momentum scan")

with st.sidebar:
    st.header("Scan")
    min_rs = st.slider("Minimum RS Rating", 50, 99, 80)
    near_high = st.slider("Within 52W high (%)", 1, 25, 5)
    min_price = st.number_input("Minimum price (₹)", min_value=1.0, value=100.0, step=10.0)
    rising_days = st.slider("MA rising days", 5, 40, 20)
    batch_size = st.slider("Download batch size", 20, 100, 50)
    st.divider()
    use_minervini = st.checkbox("Use MA trend filters", value=True)
    st.caption("Price must be above 50/150/200 DMA and all three must be rising.")
    st.divider()
    run = st.button("Run scan", type="primary", use_container_width=True)

if "result" not in st.session_state:
    st.session_state.result = None

if run:
    progress = st.progress(0, text="Starting…")
    status = st.empty()

    def update(done, total, message):
        pct = int(done / total * 100) if total else 0
        progress.progress(min(pct, 100), text=f"{message}  {done}/{total}")

    try:
        result, stats = run_scan(
            min_rs=min_rs,
            near_high_pct=near_high,
            min_price=min_price,
            rising_days=rising_days,
            use_minervini=use_minervini,
            batch_size=batch_size,
            progress_callback=update,
        )
        st.session_state.result = result
        st.session_state.stats = stats
        progress.progress(100, text="Scan complete")
        status.success(f"Found {len(result)} stocks.")
    except Exception as e:
        progress.empty()
        st.error(f"Scan failed: {e}")

df = st.session_state.result

if df is not None:
    stats = st.session_state.get("stats", {})
    c1, c2, c3 = st.columns(3)
    c1.metric("Matches", len(df))
    c2.metric("Universe", stats.get("universe", "—"))
    c3.metric("Data coverage", f"{stats.get('coverage', 0):.0f}%")

    st.subheader("Results")

    display_cols = [
        "Symbol", "LTP", "RS Rating", "3M %", "6M %",
        "9M %", "12M %", "52W High", "From 52W High %"
    ]
    available = [c for c in display_cols if c in df.columns]
    st.dataframe(
        df[available],
        use_container_width=True,
        hide_index=True,
        column_config={
            "LTP": st.column_config.NumberColumn(format="₹%.2f"),
            "52W High": st.column_config.NumberColumn(format="₹%.2f"),
            "RS Rating": st.column_config.NumberColumn(format="%d"),
            "3M %": st.column_config.NumberColumn(format="%.1f%%"),
            "6M %": st.column_config.NumberColumn(format="%.1f%%"),
            "9M %": st.column_config.NumberColumn(format="%.1f%%"),
            "12M %": st.column_config.NumberColumn(format="%.1f%%"),
            "From 52W High %": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

    out = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV",
        data=out,
        file_name="nse_rs_results.csv",
        mime="text/csv",
    )

    st.caption("RS Rating is an IBD-style approximation, not IBD's proprietary rating. Data source: Yahoo Finance; NSE universe list: NSE.")
else:
    st.info("Set your filters in the sidebar and press **Run scan**.")
    st.markdown("""
    **Default scan**

    - RS Rating ≥ 80
    - Within 5% of 52-week high
    - Price ≥ ₹100
    - At least 365 calendar days of data
    - Price above 50 / 150 / 200 DMA
    - 50 / 150 / 200 DMA rising
    """)
