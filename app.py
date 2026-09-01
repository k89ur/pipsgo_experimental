import streamlit as st

st.set_page_config(
    page_title="PipsGo RS Scanner",
    page_icon="↗",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root{--bg:#0b0e13;--panel:#11151c;--panel2:#151a22;--line:#232a35;--text:#f3f5f7;--muted:#8d96a5;--green:#35d07f;--amber:#f3b94b;--red:#ff6673;}
.stApp{background:var(--bg);color:var(--text);}
.block-container{max-width:1180px;padding:1.25rem 1.1rem 3rem;}
.hero{display:flex;justify-content:space-between;align-items:center;gap:1rem;margin-bottom:.75rem;}
.hero-title{font-size:2rem;font-weight:700;letter-spacing:-.045em;line-height:1.05;margin:0;}
.hero-sub{color:var(--muted);font-size:.82rem;margin-top:.4rem;}
.asof{color:var(--muted);font-size:.7rem;text-align:right;text-transform:uppercase;letter-spacing:.07em;}.asof strong{color:var(--text);font-size:.86rem;display:block;margin-top:.18rem;letter-spacing:0;}
.section-title{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;font-weight:600;margin:1.35rem 0 .6rem;}
.statbar{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:.75rem 0 1.15rem;}.stat{background:var(--panel);padding:.85rem 1rem;}.stat-label{color:var(--muted);font-size:.66rem;text-transform:uppercase;letter-spacing:.08em;}.stat-value{font-size:1.18rem;font-weight:650;margin-top:.2rem;}
.leader-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:.7rem;}.leader{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:.8rem 1rem;}.leader-top{display:flex;justify-content:space-between;align-items:center;}.leader-rank{color:var(--muted);font-size:.7rem;font-weight:600;}.leader-name{font-size:.88rem;font-weight:600;margin-top:.3rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}.leader-score{font-size:1.45rem;font-weight:700;}
.score-strong{color:var(--green)}.score-mid{color:var(--amber)}.score-weak{color:var(--red)}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:11px;overflow:hidden;}[data-testid="stDataFrame"] [role="columnheader"]{background:var(--panel2);}
[data-testid="stDownloadButton"] button{border-radius:9px;border:1px solid #2e9e68;background:#35d07f;color:#07110c;font-weight:700;min-height:2.35rem;padding:.35rem .9rem;box-shadow:0 0 0 1px rgba(53,208,127,.08),0 5px 18px rgba(53,208,127,.08);}[data-testid="stDownloadButton"] button:hover{background:#4be28f;border-color:#4be28f;color:#07110c;}
.legend{color:var(--muted);font-size:.7rem;margin:.5rem 0 1rem;}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin:0 .25rem 0 .7rem;}.dot:first-child{margin-left:0;}.footer{color:#606a79;font-size:.7rem;border-top:1px solid var(--line);padding-top:.85rem;margin-top:1.2rem;}.help{color:var(--muted);font-size:.7rem;}
/* compact top navigation */
[data-testid="stHeader"]{background:var(--bg);}.stMainBlockContainer{padding-top:.65rem;}
@media(max-width:700px){.block-container{padding:1rem .65rem 2.25rem;}.hero-title{font-size:1.6rem;}.asof{display:none;}.statbar{grid-template-columns:repeat(2,1fr);}.leader-grid{grid-template-columns:1fr;}}
</style>
""", unsafe_allow_html=True)

index_page = st.Page("pages/index_rs.py", title="INDEX RS", icon=":material/leaderboard:", url_path="index-rs", default=True)
stock_page = st.Page("pages/stock_rs.py", title="STOCK RS + TECHNICAL", icon=":material/query_stats:", url_path="stock-rs")

pg = st.navigation([index_page, stock_page], position="top")
pg.run()
