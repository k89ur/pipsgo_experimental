import streamlit as st

st.set_page_config(
    page_title="PipsGo RS Scanner",
    page_icon="↗",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root{--bg:#090c11;--panel:#10151c;--panel2:#151b23;--line:#252d38;--text:#f3f5f7;--muted:#8993a2;--green:#35d07f;--amber:#f3b94b;--red:#ff6673;--blue:#6ca8ff;}
.stApp{background:var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif;}
.block-container{max-width:1500px;padding:1rem 1.25rem 3rem;}
[data-testid="stSidebar"]{background:#0d1117;border-right:1px solid var(--line);}
[data-testid="stSidebar"] > div:first-child{padding-top:1rem;}
[data-testid="stSidebar"] .stButton button{border:1px solid transparent;background:transparent;color:var(--muted);text-align:left;justify-content:flex-start;border-radius:8px;}
[data-testid="stSidebar"] .stButton button:hover{background:var(--panel2);color:var(--text);}
.sidebar-label{font-size:.65rem;color:#697384;text-transform:uppercase;letter-spacing:.12em;font-weight:700;margin:.3rem 0 .55rem;}
.logo{text-align:center;font-size:1.05rem;font-weight:800;letter-spacing:.22em;color:var(--text);margin:.15rem 0 1rem;}
.logo span{color:var(--green);}
.page-head{margin-bottom:.85rem;}.page-title{font-size:1.8rem;font-weight:700;letter-spacing:-.04em;line-height:1.05;}.page-sub{color:var(--muted);font-size:.76rem;margin-top:.35rem;}
.section-title{font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.11em;font-weight:700;margin:1rem 0 .55rem;}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:.9rem 1rem;}
.right-panel{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:.85rem .9rem;min-height:100%;}
.right-title{font-size:.66rem;color:var(--muted);text-transform:uppercase;letter-spacing:.11em;font-weight:700;margin-bottom:.7rem;}
.rstat{border-bottom:1px solid var(--line);padding:.55rem 0;}.rstat:last-child{border-bottom:0;}.rstat-label{color:#737e8f;font-size:.61rem;text-transform:uppercase;letter-spacing:.08em;}.rstat-value{font-size:1.05rem;font-weight:700;margin-top:.15rem;}
.hero-center{text-align:center;margin:.05rem 0 1rem;}.hero-center .brand{font-size:.72rem;color:var(--muted);letter-spacing:.18em;text-transform:uppercase;font-weight:700;}.hero-center .brand b{color:var(--green);}.hero-center .date{font-size:.66rem;color:#606a79;margin-top:.28rem;}
.settings{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:.9rem 1rem;}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:10px;overflow:hidden;}[data-testid="stDataFrame"] [role="columnheader"]{background:var(--panel2);}
[data-testid="stDownloadButton"] button{border-radius:8px;border:1px solid #2e9e68;background:#35d07f;color:#07110c;font-weight:700;min-height:2.2rem;padding:.25rem .8rem;box-shadow:0 5px 16px rgba(53,208,127,.08);}[data-testid="stDownloadButton"] button:hover{background:#4be28f;border-color:#4be28f;color:#07110c;}
.score-strong{color:var(--green)}.score-mid{color:var(--amber)}.score-weak{color:var(--red)}
.help{color:var(--muted);font-size:.68rem;line-height:1.4;}.footer{color:#5f6978;font-size:.68rem;border-top:1px solid var(--line);padding-top:.75rem;margin-top:1rem;}.legend{color:var(--muted);font-size:.68rem;margin:.45rem 0 1rem;}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin:0 .25rem 0 .65rem}.dot:first-child{margin-left:0}
@media(max-width:900px){.block-container{padding:1rem .75rem 2rem;}.page-title{font-size:1.55rem;}.hero-center{margin-bottom:.75rem;}}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="logo"><span>PIPS</span>GOX</div>', unsafe_allow_html=True)

index_page = st.Page("pages/index_rs.py", title="Index RS", icon=":material/leaderboard:", url_path="index-rs", default=True)
stock_page = st.Page("pages/stock_rs.py", title="Stock RS + Technical", icon=":material/query_stats:", url_path="stock-rs")

with st.sidebar:
    st.markdown('<div class="sidebar-label">Scanners</div>', unsafe_allow_html=True)
    st.caption("Choose a scanner")
    st.divider()
    st.markdown('<div class="help">PipsGoX market scanners</div>', unsafe_allow_html=True)

pg = st.navigation([index_page, stock_page], position="sidebar")
pg.run()
