import streamlit as st
import pandas as pd
from rs_engine import run_scan

st.markdown("""
<div class="hero"><div>
  <div class="hero-title">Stock RS + Technical</div>
  <div class="hero-sub">NSE equities · IBD-style RS · 52-week high · Minervini trend filters</div>
</div></div>
""", unsafe_allow_html=True)

if "stock_result" not in st.session_state:
    st.session_state.stock_result = None

with st.container(border=True):
    st.markdown("<div class='section-title' style='margin-top:.2rem'>Scan settings</div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: min_rs = st.slider("Minimum RS", 50, 99, 80, key="stock_min_rs")
    with c2: near_high = st.slider("Within 52W high (%)", 1, 25, 5, key="stock_near_high")
    with c3: min_price = st.number_input("Minimum price (₹)", min_value=1.0, value=100.0, step=10.0, key="stock_min_price")
    with c4: rising_days = st.slider("MA rising days", 5, 40, 20, key="stock_rising_days")
    c5, c6 = st.columns([1, 3])
    with c5: use_minervini = st.checkbox("Minervini MA trend", value=True, key="stock_minervini")
    with c6: st.markdown("<div class='help'>Price above 50 / 150 / 200 DMA and all three rising when enabled.</div>", unsafe_allow_html=True)
    run_stock = st.button("▶  Run Stock Scan", type="primary")

if run_stock:
    progress = st.progress(0, text="Starting stock scan…")
    try:
        def stock_update(done, total, message):
            progress.progress(min(done / max(total, 1), 1.0), text=f"{message} · {done}/{total}")
        result, stats = run_scan(
            min_rs=min_rs, near_high_pct=near_high, min_price=min_price,
            rising_days=rising_days, use_minervini=use_minervini,
            batch_size=50, progress_callback=stock_update,
        )
        st.session_state.stock_result = result
        st.session_state.stock_stats = stats
        progress.empty()
    except Exception as e:
        progress.empty()
        st.error(f"Stock scan failed: {e}")


df = st.session_state.stock_result
if df is None:
    st.markdown('<div class="footer">Run the scan to download the NSE stock universe and apply the selected RS + technical filters.</div>', unsafe_allow_html=True)
else:
    stats = st.session_state.get("stock_stats", {})
    matches = len(df)
    near = int((df["From 52W High %"] <= 2).sum()) if matches else 0

    st.markdown(f"""
    <div class="statbar">
      <div class="stat"><div class="stat-label">Matches</div><div class="stat-value">{matches}</div></div>
      <div class="stat"><div class="stat-label">Universe</div><div class="stat-value">{stats.get('universe','—')}</div></div>
      <div class="stat"><div class="stat-label">Coverage</div><div class="stat-value">{stats.get('coverage',0):.0f}%</div></div>
      <div class="stat"><div class="stat-label">RS 80+ & within 2%</div><div class="stat-value score-strong">{near}</div></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Results</div>', unsafe_allow_html=True)
    search = st.text_input("Search stocks", placeholder="Search symbol…", label_visibility="collapsed", key="stock_search")
    view = df.copy()
    if search:
        view = view[view["Symbol"].str.contains(search, case=False, na=False)]

    display_cols = ["Symbol", "LTP", "RS Rating", "3M %", "6M %", "9M %", "12M %", "52W High", "From 52W High %", "50 DMA", "150 DMA", "200 DMA", "TradingView"]
    available = [c for c in display_cols if c in view.columns]
    shown = view[available].copy()

    def stock_style(row):
        styles = [""] * len(row)
        if "RS Rating" in row.index and pd.notna(row["RS Rating"]):
            score = float(row["RS Rating"])
            if score >= 80: bg, fg = "#123b27", "#35d07f"
            elif score >= 50: bg, fg = "#3a3015", "#f3b94b"
            else: bg, fg = "#3b1a20", "#ff6673"
            styles[row.index.get_loc("RS Rating")] = f"background-color:{bg};color:{fg};font-weight:700;"
        return styles

    styled = shown.style.apply(stock_style, axis=1)
    left, right = st.columns([4.2, 1])
    with left:
        st.markdown(f'<div style="color:#606a79;font-size:.7rem;margin-top:.25rem">{len(view)} stocks shown · sorted by RS · scan uses Yahoo Finance daily data</div>', unsafe_allow_html=True)
    with right:
        st.download_button("↓  Export CSV", df.to_csv(index=False).encode("utf-8"), "nse_stock_rs_scan.csv", "text/csv", use_container_width=True, type="primary")

    st.dataframe(styled, use_container_width=True, hide_index=True, height=min(700, 95 + max(len(shown),1)*36), column_config={
        "Symbol": st.column_config.TextColumn("SYMBOL", width="medium"),
        "LTP": st.column_config.NumberColumn("LTP", format="₹%.2f"),
        "RS Rating": st.column_config.NumberColumn("RS", format="%d", width="small"),
        "3M %": st.column_config.NumberColumn("3M", format="%.1f%%"),
        "6M %": st.column_config.NumberColumn("6M", format="%.1f%%"),
        "9M %": st.column_config.NumberColumn("9M", format="%.1f%%"),
        "12M %": st.column_config.NumberColumn("12M", format="%.1f%%"),
        "52W High": st.column_config.NumberColumn("52W HIGH", format="₹%.2f"),
        "From 52W High %": st.column_config.NumberColumn("FROM HIGH", format="%.1f%%"),
        "50 DMA": st.column_config.NumberColumn("50 DMA", format="₹%.2f"),
        "150 DMA": st.column_config.NumberColumn("150 DMA", format="₹%.2f"),
        "200 DMA": st.column_config.NumberColumn("200 DMA", format="₹%.2f"),
        "TradingView": st.column_config.LinkColumn("CHART", display_text="↗", width="small"),
    })

    st.markdown('<div class="legend"><span class="dot" style="background:#35d07f"></span>RS 80–99 <span class="dot" style="background:#f3b94b"></span>RS 50–79 <span class="dot" style="background:#ff6673"></span>RS 1–49</div>', unsafe_allow_html=True)
    st.markdown('<div class="footer">RS = weighted 3M / 6M / 9M / 12M relative performance. Technical filter = price above 50 / 150 / 200 DMA with configurable rising-period checks.</div>', unsafe_allow_html=True)
