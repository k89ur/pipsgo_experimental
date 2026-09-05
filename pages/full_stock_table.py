import streamlit as st
import pandas as pd

st.set_page_config(page_title="Stock RS Table", page_icon=":material/table_view:", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
[data-testid="stSidebar"]{display:none!important}
.block-container{max-width:none;padding:1.2rem .8rem 1rem}
[data-testid="stDataFrame"]{border:1px solid #252d38;border-radius:8px;overflow:hidden}
[data-testid="stDataFrame"] [role="columnheader"]{background:#151b23}
</style>
""", unsafe_allow_html=True)

df = st.session_state.get("stock_result")
if df is None or df.empty:
    st.info("Run a Stock RS scan first to open the full table.")
    st.stop()

display_cols = ["Symbol", "Index", "Industry", "LTP", "RS Rating", "3M %", "6M %", "9M %", "12M %", "52W High", "From 52W High %", "TradingView"]
full_table = df[[c for c in display_cols if c in df.columns]].copy()
full_table.insert(0, "S.No", range(1, len(full_table) + 1))

def stock_style(row):
    styles = [""] * len(row)
    if "RS Rating" in row.index and pd.notna(row["RS Rating"]):
        score = float(row["RS Rating"])
        fg = "#35d07f" if score >= 80 else ("#f3b94b" if score >= 50 else "#ff6673")
        styles[row.index.get_loc("RS Rating")] = f"color:{fg};font-weight:700;"
    return styles

st.dataframe(
    full_table.style.apply(stock_style, axis=1),
    use_container_width=True,
    hide_index=True,
    height=min(900, 95 + max(len(full_table), 1) * 36),
    column_config={
        "S.No": st.column_config.NumberColumn("S.NO", format="%d", width="small"),
        "Symbol": st.column_config.TextColumn("SYMBOL"),
        "Index": st.column_config.TextColumn("INDEX"),
        "Industry": st.column_config.TextColumn("INDUSTRY"),
        "LTP": st.column_config.NumberColumn("LTP", format="₹%.2f"),
        "RS Rating": st.column_config.NumberColumn("RS", format="%d", width="small"),
        "3M %": st.column_config.NumberColumn("3M", format="%.1f%%"),
        "6M %": st.column_config.NumberColumn("6M", format="%.1f%%"),
        "9M %": st.column_config.NumberColumn("9M", format="%.1f%%"),
        "12M %": st.column_config.NumberColumn("12M", format="%.1f%%"),
        "52W High": st.column_config.NumberColumn("52W HIGH", format="₹%.2f"),
        "From 52W High %": st.column_config.NumberColumn("52WH < %", format="%.1f%%"),
        "TradingView": st.column_config.LinkColumn("CHART", display_text="Open ↗", width="small"),
    },
)
