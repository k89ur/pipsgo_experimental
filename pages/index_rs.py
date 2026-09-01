import streamlit as st
import pandas as pd
from index_rs_engine import run_index_scan

if "index_result" not in st.session_state:
    st.session_state.index_result = None

st.markdown('<div class="hero-center"><div class="brand"><b>PIPS</b>GOX · INDEX RS</div><div class="date">28 industries · benchmarked to NIFTY 50</div></div>', unsafe_allow_html=True)

main, side = st.columns([4.7, 1.35], gap="large")

with side:
    st.markdown('<div class="right-panel"><div class="right-title">Scanner status</div>', unsafe_allow_html=True)
    status_slot = st.empty()
    stats_slot = st.empty()
    st.markdown('</div>', unsafe_allow_html=True)

with main:
    h1, h2 = st.columns([3.8, 1])
    with h1:
        st.markdown('<div class="page-head"><div class="page-title">NIFTY Relative Strength</div><div class="page-sub">IBD-style relative strength · Pine-compatible daily calculation</div></div>', unsafe_allow_html=True)
    with h2:
        refresh = st.button("↻ Refresh", type="primary", use_container_width=True)

    if refresh or st.session_state.index_result is None:
        progress = status_slot.progress(0, text="Connecting…")
        try:
            def update(done, total, message):
                progress.progress(min(done / max(total, 1), 1.0), text=f"{message}\n{done}/{total}")
            df, stats = run_index_scan(update)
            st.session_state.index_result = df
            st.session_state.index_stats = stats
            progress.empty()
            status_slot.markdown('<div class="rstat"><div class="rstat-label">Status</div><div class="rstat-value score-strong">Ready</div></div>', unsafe_allow_html=True)
        except Exception as e:
            progress.empty()
            status_slot.error(f"Scan failed: {e}")
            st.stop()

    df = st.session_state.index_result
    stats = st.session_state.get("index_stats", {})
    asof = stats.get("as_of")
    asof_text = asof.strftime("%d %b %Y") if hasattr(asof, "strftime") else "—"
    valid = df[df["Raw RS"].notna()].copy()
    strong = int((valid["RS 1-99"] >= 80).sum())
    weak = int((valid["RS 1-99"] < 50).sum())

    stats_slot.markdown(f"""
    <div class="rstat"><div class="rstat-label">Latest data</div><div class="rstat-value">{asof_text}</div></div>
    <div class="rstat"><div class="rstat-label">Universe</div><div class="rstat-value">{stats.get('universe',28)}</div></div>
    <div class="rstat"><div class="rstat-label">Calculated</div><div class="rstat-value">{stats.get('available',0)}</div></div>
    <div class="rstat"><div class="rstat-label">Strong · 80+</div><div class="rstat-value score-strong">{strong}</div></div>
    <div class="rstat"><div class="rstat-label">Weak · &lt;50</div><div class="rstat-value score-weak">{weak}</div></div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Leaders</div>', unsafe_allow_html=True)
    top = valid.head(3)
    if len(top):
        cards = []
        for _, row in top.iterrows():
            score = int(row["RS 1-99"])
            cls = "score-strong" if score >= 80 else ("score-mid" if score >= 50 else "score-weak")
            cards.append(f"<div class='leader'><div class='leader-top'><span class='leader-rank'>#{int(row['Rank']):02d}</span><span class='leader-score {cls}'>{score}</span></div><div class='leader-name'>{row['INDEX']}</div><div style='color:#8d96a5;font-size:.68rem;margin-top:.2rem'>Raw RS {row['Raw RS']:.2f}</div></div>")
        st.markdown("<div class='leader-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-title">Results</div>', unsafe_allow_html=True)
    search_col, filter_col, export_col = st.columns([2.6, 1.6, 1.0])
    with search_col:
        search = st.text_input("Search", placeholder="Search index…", label_visibility="collapsed", key="index_search")
    with filter_col:
        filter_mode = st.selectbox("Filter", ["All", "Strong · 80+", "Middle · 50–79", "Weak · <50", "Unavailable"], label_visibility="collapsed", key="index_filter")
    with export_col:
        st.download_button("↓ Export CSV", df.to_csv(index=False).encode("utf-8"), "nifty_index_rs.csv", "text/csv", use_container_width=True, type="primary")

    view = df.copy()
    if search: view = view[view["INDEX"].str.contains(search, case=False, na=False)]
    if filter_mode == "Strong · 80+": view = view[view["RS 1-99"] >= 80]
    elif filter_mode == "Middle · 50–79": view = view[(view["RS 1-99"] >= 50) & (view["RS 1-99"] < 80)]
    elif filter_mode == "Weak · <50": view = view[(view["RS 1-99"] < 50) & view["RS 1-99"].notna()]
    elif filter_mode == "Unavailable": view = view[view["RS 1-99"].isna()]

    show = view[["Rank", "INDEX", "RS 1-99", "Raw RS", "3M %", "6M %", "9M %", "12M %", "LTP", "Status"]].copy()
    show["Rank"] = show["Rank"].astype(int)
    show.insert(2, "Strength", show["RS 1-99"].map(lambda s: "N/A" if pd.isna(s) else ("Strong" if s >= 80 else ("Middle" if s >= 50 else "Weak"))))

    def highlight_strength_cells(row):
        score = row["RS 1-99"]; styles = [""] * len(row)
        si, ri = row.index.get_loc("Strength"), row.index.get_loc("RS 1-99")
        if pd.isna(score): bg, fg = "#252a33", "#8d96a5"
        elif score >= 80: bg, fg = "#123b27", "#35d07f"
        elif score >= 50: bg, fg = "#3a3015", "#f3b94b"
        else: bg, fg = "#3b1a20", "#ff6673"
        style = f"background-color:{bg};color:{fg};font-weight:700;"; styles[si] = style; styles[ri] = style
        return styles

    show["TradingView"] = show["INDEX"].map(lambda x: f"https://www.tradingview.com/chart/?symbol=NSE%3A{x}")
    styled = show.style.apply(highlight_strength_cells, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True, height=min(720, 95 + max(len(show), 1) * 36), column_config={
        "Rank": st.column_config.NumberColumn("#", width="small"), "INDEX": st.column_config.TextColumn("INDEX", width="medium"),
        "Strength": st.column_config.TextColumn("STRENGTH", width="small"), "RS 1-99": st.column_config.NumberColumn("RS", format="%d", width="small"),
        "Raw RS": st.column_config.NumberColumn("RAW RS", format="%.2f", width="small"), "3M %": st.column_config.NumberColumn("3M", format="%.2f"),
        "6M %": st.column_config.NumberColumn("6M", format="%.2f"), "9M %": st.column_config.NumberColumn("9M", format="%.2f"),
        "12M %": st.column_config.NumberColumn("12M", format="%.2f"), "LTP": st.column_config.NumberColumn("LTP", format="%.2f"),
        "Status": st.column_config.TextColumn("STATUS", width="small"), "TradingView": st.column_config.LinkColumn("CHART", display_text="Open ↗", width="small"),
    })
    st.caption("3M / 6M / 9M / 12M = relative performance vs NIFTY 50")
    st.markdown('<div class="legend"><span class="dot" style="background:#35d07f"></span>Strong 80–99 <span class="dot" style="background:#f3b94b"></span>Middle 50–79 <span class="dot" style="background:#ff6673"></span>Weak 1–49 <span class="dot" style="background:#606a79"></span>Unavailable</div>', unsafe_allow_html=True)
    st.markdown('<div class="footer">TradingView daily bars · 63 / 126 / 189 / 252 trading bars · weighted 40% / 20% / 20% / 20% · Pine-compatible 1–99 ranking</div>', unsafe_allow_html=True)
