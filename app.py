import streamlit as st
import pandas as pd

from index_rs_engine import run_index_scan

st.set_page_config(
    page_title="NIFTY RS",
    page_icon="↗",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
    --bg: #0b0e13;
    --panel: #11151c;
    --panel2: #151a22;
    --line: #232a35;
    --text: #f3f5f7;
    --muted: #8d96a5;
    --green: #35d07f;
    --amber: #f3b94b;
    --red: #ff6673;
}

.stApp { background: var(--bg); color: var(--text); }
.block-container { max-width: 1180px; padding: 1.5rem 1.1rem 3rem; }
header[data-testid="stHeader"] { background: transparent; }

.hero { display:flex; justify-content:space-between; align-items:center; gap:1rem; margin-bottom:1rem; }
.hero-title { font-size:2rem; font-weight:700; letter-spacing:-.045em; line-height:1.05; margin:0; }
.hero-sub { color:var(--muted); font-size:.82rem; margin-top:.4rem; }
.asof { color:var(--muted); font-size:.7rem; text-align:right; text-transform:uppercase; letter-spacing:.07em; }
.asof strong { color:var(--text); font-size:.86rem; display:block; margin-top:.18rem; letter-spacing:0; }

[data-testid="stButton"] button { border-radius:9px; font-weight:600; border:1px solid #303846; }
[data-testid="stButton"] button[kind="primary"] { background:#f4f6f8; color:#0b0e13; border:0; }

.statbar { display:grid; grid-template-columns:repeat(4,1fr); gap:1px; background:var(--line); border:1px solid var(--line); border-radius:12px; overflow:hidden; margin:.9rem 0 1.35rem; }
.stat { background:var(--panel); padding:.9rem 1.05rem; }
.stat-label { color:var(--muted); font-size:.68rem; text-transform:uppercase; letter-spacing:.08em; }
.stat-value { font-size:1.2rem; font-weight:650; margin-top:.22rem; }

.section-title { font-size:.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:.1em; font-weight:600; margin:1.55rem 0 .6rem; }
.section-head { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin:1.55rem 0 .6rem; }
.section-head .section-title { margin:0; }

.leader-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:.7rem; }
.leader { background:var(--panel); border:1px solid var(--line); border-radius:11px; padding:.8rem 1rem; }
.leader-top { display:flex; justify-content:space-between; align-items:center; }
.leader-rank { color:var(--muted); font-size:.7rem; font-weight:600; }
.leader-name { font-size:.9rem; font-weight:600; margin-top:.32rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.leader-score { font-size:1.45rem; font-weight:700; }
.score-strong { color:var(--green); }
.score-mid { color:var(--amber); }
.score-weak { color:var(--red); }

.toolbar { display:flex; gap:.65rem; align-items:center; margin:.7rem 0 .75rem; }

[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:11px; overflow:hidden; }
[data-testid="stDataFrame"] [role="columnheader"] { background:var(--panel2); }

/* Eye-catching but restrained CSV action. */
[data-testid="stDownloadButton"] button {
    border-radius:9px;
    border:1px solid #2e9e68;
    background:#35d07f;
    color:#07110c;
    font-weight:700;
    min-height:2.35rem;
    padding:.35rem .9rem;
    box-shadow:0 0 0 1px rgba(53,208,127,.08), 0 5px 18px rgba(53,208,127,.08);
}
[data-testid="stDownloadButton"] button:hover { background:#4be28f; border-color:#4be28f; color:#07110c; }

.legend { color:var(--muted); font-size:.7rem; margin:.5rem 0 1.1rem; }
.dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin:0 .25rem 0 .7rem; }
.dot:first-child { margin-left:0; }
.footer { color:#606a79; font-size:.7rem; border-top:1px solid var(--line); padding-top:.85rem; margin-top:1.25rem; }

@media (max-width:700px) {
    .block-container { padding:1.15rem .65rem 2.25rem; }
    .hero { align-items:flex-start; }
    .hero-title { font-size:1.6rem; }
    .asof { display:none; }
    .statbar { grid-template-columns:repeat(2,1fr); }
    .leader-grid { grid-template-columns:1fr; }
}
</style>
""", unsafe_allow_html=True)

if "index_result" not in st.session_state:
    st.session_state.index_result = None

refresh = st.button("↻  Refresh", type="primary")

if refresh or st.session_state.index_result is None:
    progress = st.progress(0, text="Connecting to TradingView…")
    try:
        def update(done, total, message):
            progress.progress(min(done / max(total, 1), 1.0), text=f"{message} · {done}/{total}")
        df, stats = run_index_scan(update)
        st.session_state.index_result = df
        st.session_state.index_stats = stats
        progress.empty()
    except Exception as e:
        progress.empty()
        st.error(f"TradingView data refresh failed: {e}")
        st.stop()

df = st.session_state.index_result
stats = st.session_state.get("index_stats", {})
asof = stats.get("as_of")
asof_text = asof.strftime("%d %b %Y") if hasattr(asof, "strftime") else "—"

# Header is rendered only after data is available, avoiding the duplicate date block.
h1, h2 = st.columns([5, 1.15])
with h1:
    st.markdown("""
    <div class="hero">
      <div>
        <div class="hero-title">NIFTY Relative Strength</div>
        <div class="hero-sub">28 industries · IBD-style RS · benchmarked to NIFTY 50</div>
      </div>
    </div>
    """, unsafe_allow_html=True)
with h2:
    st.markdown(f"<div class='asof'>Latest data<strong>{asof_text}</strong></div>", unsafe_allow_html=True)

valid = df[df["Raw RS"].notna()].copy()
strong = int((valid["RS 1-99"] >= 80).sum())
weak = int((valid["RS 1-99"] < 50).sum())

st.markdown(f"""
<div class="statbar">
  <div class="stat"><div class="stat-label">Universe</div><div class="stat-value">{stats.get('universe', 28)}</div></div>
  <div class="stat"><div class="stat-label">Calculated</div><div class="stat-value">{stats.get('available', 0)}</div></div>
  <div class="stat"><div class="stat-label">Strong · RS 80+</div><div class="stat-value score-strong">{strong}</div></div>
  <div class="stat"><div class="stat-label">Weak · RS &lt;50</div><div class="stat-value score-weak">{weak}</div></div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="section-title">Leaders</div>', unsafe_allow_html=True)
top = valid.head(3)
if len(top):
    cards = []
    for _, row in top.iterrows():
        score = int(row["RS 1-99"])
        cls = "score-strong" if score >= 80 else ("score-mid" if score >= 50 else "score-weak")
        cards.append(
            f"<div class='leader'><div class='leader-top'><span class='leader-rank'>#{int(row['Rank']):02d}</span><span class='leader-score {cls}'>{score}</span></div><div class='leader-name'>{row['INDEX']}</div><div style='color:#8d96a5;font-size:.7rem;margin-top:.22rem'>Raw RS&nbsp; {row['Raw RS']:.2f}</div></div>"
        )
    st.markdown("<div class='leader-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)

# Controls
st.markdown('<div class="section-title">All industries</div>', unsafe_allow_html=True)
f1, f2 = st.columns([2.4, 1.6])
with f1:
    search = st.text_input("Search", placeholder="Search index…", label_visibility="collapsed")
with f2:
    filter_mode = st.selectbox("Filter", ["All", "Strong · 80+", "Middle · 50–79", "Weak · <50", "Unavailable"], label_visibility="collapsed")

view = df.copy()
if search:
    view = view[view["INDEX"].str.contains(search, case=False, na=False)]
if filter_mode == "Strong · 80+":
    view = view[view["RS 1-99"] >= 80]
elif filter_mode == "Middle · 50–79":
    view = view[(view["RS 1-99"] >= 50) & (view["RS 1-99"] < 80)]
elif filter_mode == "Weak · <50":
    view = view[(view["RS 1-99"] < 50) & view["RS 1-99"].notna()]
elif filter_mode == "Unavailable":
    view = view[view["RS 1-99"].isna()]

show = view[["Rank", "INDEX", "RS 1-99", "Raw RS", "3M %", "6M %", "9M %", "12M %", "LTP", "Status"]].copy()
show["Rank"] = show["Rank"].astype(int)

# Human-readable strength label derived directly from the existing RS rank.
def strength_label(score):
    if pd.isna(score):
        return "N/A"
    if score >= 80:
        return "Strong"
    if score >= 50:
        return "Middle"
    return "Weak"

show.insert(2, "Strength", show["RS 1-99"].map(strength_label))

# Highlight ONLY the Strength and RS cells; all other cells keep the neutral table background.
def highlight_strength_cells(row):
    score = row["RS 1-99"]
    styles = [""] * len(row)
    strength_i = row.index.get_loc("Strength")
    rs_i = row.index.get_loc("RS 1-99")

    if pd.isna(score):
        bg, fg = "#252a33", "#8d96a5"
    elif score >= 80:
        bg, fg = "#123b27", "#35d07f"
    elif score >= 50:
        bg, fg = "#3a3015", "#f3b94b"
    else:
        bg, fg = "#3b1a20", "#ff6673"

    style = f"background-color:{bg};color:{fg};font-weight:700;"
    styles[strength_i] = style
    styles[rs_i] = style
    return styles

# Add the TradingView URL as the final column and show it as a compact external-link icon.
show["TradingView"] = show["INDEX"].map(
    lambda x: f"https://www.tradingview.com/chart/?symbol=NSE%3A{x}"
)

styled = show.style.apply(highlight_strength_cells, axis=1)

# Export is intentionally placed beside the table section so it is easy to find.
head_left, head_right = st.columns([4.2, 1])
with head_left:
    st.markdown('<div style="color:#606a79;font-size:.7rem;margin-top:.25rem">Ranked by Pine-compatible RS · click ↗ to open the index chart</div>', unsafe_allow_html=True)
with head_right:
    st.download_button(
        "↓  Export CSV",
        df.to_csv(index=False).encode("utf-8"),
        "nifty_index_rs.csv",
        "text/csv",
        use_container_width=True,
        type="primary",
    )

st.dataframe(
    styled,
    use_container_width=True,
    hide_index=True,
    height=min(760, 95 + max(len(show), 1) * 36),
    column_config={
        "Rank": st.column_config.NumberColumn("#", width="small"),
        "INDEX": st.column_config.TextColumn("INDEX", width="medium"),
        "Strength": st.column_config.TextColumn("STRENGTH", width="small"),
        "RS 1-99": st.column_config.NumberColumn("RS", format="%d", width="small"),
        "Raw RS": st.column_config.NumberColumn("RAW RS", format="%.2f", width="small"),
        "3M %": st.column_config.NumberColumn("3M", format="%.2f"),
        "6M %": st.column_config.NumberColumn("6M", format="%.2f"),
        "9M %": st.column_config.NumberColumn("9M", format="%.2f"),
        "12M %": st.column_config.NumberColumn("12M", format="%.2f"),
        "LTP": st.column_config.NumberColumn("LTP", format="%.2f"),
        "Status": st.column_config.TextColumn("STATUS", width="small"),
        "TradingView": st.column_config.LinkColumn("CHART", display_text="↗", width="small"),
    },
)

st.caption("3M / 6M / 9M / 12M = relative performance vs NIFTY 50")
st.markdown('<div class="legend"><span class="dot" style="background:#35d07f"></span>Strong 80–99 <span class="dot" style="background:#f3b94b"></span>Middle 50–79 <span class="dot" style="background:#ff6673"></span>Weak 1–49 <span class="dot" style="background:#606a79"></span>Unavailable</div>', unsafe_allow_html=True)
st.markdown('<div class="footer">TradingView daily bars · 63 / 126 / 189 / 252 trading bars · weighted 40% / 20% / 20% / 20% · Pine-compatible 1–99 ranking</div>', unsafe_allow_html=True)
