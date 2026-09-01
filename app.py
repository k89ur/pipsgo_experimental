import streamlit as st

st.set_page_config(page_title="PipsGo RS Scanner", page_icon="↗", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{--bg:#090c11;--panel:#10151c;--panel2:#151b23;--line:#252d38;--text:#f3f5f7;--muted:#8993a2;--green:#35d07f;--amber:#f3b94b;--red:#ff6673;}
.stApp{background:var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif}.block-container{max-width:1500px;padding:3.15rem 1.25rem 3rem}
[data-testid="stSidebar"]{background:#0d1117;border-right:1px solid var(--line)}[data-testid="stSidebar"]>div:first-child{padding-top:1rem}
.sidebar-label{font-size:.65rem;color:#697384;text-transform:uppercase;letter-spacing:.12em;font-weight:700;margin:.3rem 0 .55rem}
.page-brand{display:flex;justify-content:flex-start;align-items:center;height:34px;margin:.05rem 0 .85rem;font-size:1.15rem;font-weight:800;letter-spacing:.24em;line-height:1;color:var(--text);user-select:none}.page-brand span{color:var(--green)}
.page-head{margin-bottom:.85rem}.page-title{font-size:1.8rem;font-weight:700;letter-spacing:-.04em;line-height:1.05}.page-sub{color:var(--muted);font-size:.76rem;margin-top:.35rem}.section-title{font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.11em;font-weight:700;margin:1rem 0 .55rem}
.right-panel{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:.85rem .9rem}.right-title{font-size:.66rem;color:var(--muted);text-transform:uppercase;letter-spacing:.11em;font-weight:700;margin-bottom:.7rem}.rstat{border-bottom:1px solid var(--line);padding:.55rem 0}.rstat:last-child{border-bottom:0}.rstat-label{color:#737e8f;font-size:.61rem;text-transform:uppercase;letter-spacing:.08em}.rstat-value{font-size:1.05rem;font-weight:700;margin-top:.15rem}
.settings{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:.9rem 1rem}.leader-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:.65rem}.leader{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:.7rem .85rem}.leader-top{display:flex;justify-content:space-between;align-items:center}.leader-rank{color:var(--muted);font-size:.66rem}.leader-score{font-size:1.3rem;font-weight:700}.leader-name{font-size:.8rem;font-weight:600;margin-top:.25rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.score-strong{color:var(--green)}.score-mid{color:var(--amber)}.score-weak{color:var(--red)}
.empty-state{background:var(--panel);border:1px dashed var(--line);border-radius:11px;padding:1.5rem;margin-top:.8rem}.empty-title{font-weight:650}.empty-sub,.help{color:var(--muted);font-size:.68rem;line-height:1.45;margin-top:.25rem}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:10px;overflow:hidden}[data-testid="stDataFrame"] [role="columnheader"]{background:var(--panel2)}
.table-tools{display:flex;justify-content:flex-end;align-items:center;gap:.4rem;margin:0 0 .3rem}.table-tools [data-testid="stButton"] button,.table-tools [data-testid="stDownloadButton"] button{min-height:2rem;height:2rem;padding:.2rem .55rem;border:1px solid var(--line);background:var(--panel);color:#a7b0bd;border-radius:7px;font-size:.72rem}.table-tools [data-testid="stButton"] button:hover,.table-tools [data-testid="stDownloadButton"] button:hover{color:var(--text);border-color:#3b4655;background:var(--panel2)}
[data-testid="stDownloadButton"] button{border-radius:7px;border:1px solid #2e9e68;background:#35d07f;color:#07110c;font-weight:700;min-height:2rem;height:2rem;padding:.15rem .6rem;box-shadow:none;white-space:nowrap;display:flex;align-items:center;justify-content:space-between;gap:.7rem}[data-testid="stDownloadButton"] button:hover{background:#4be28f;border-color:#4be28f;color:#07110c}
[data-testid="stDownloadButton"] button svg{order:2;margin-left:auto;width:.85rem;height:.85rem}
.legend{color:var(--muted);font-size:.68rem;margin:.45rem 0 1rem}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin:0 .25rem 0 .65rem}.dot:first-child{margin-left:0}.table-foot{color:#697384;font-size:.68rem;margin-top:.4rem}.footer{color:#5f6978;font-size:.68rem;border-top:1px solid var(--line);padding-top:.75rem;margin-top:1rem}
@media(max-width:900px){.block-container{padding:2.7rem .7rem 2rem}.leader-grid{grid-template-columns:1fr}.page-title{font-size:1.55rem}.page-brand{height:30px;font-size:1.02rem}}
</style>
""", unsafe_allow_html=True)

index_page = st.Page("pages/index_rs.py", title="Index RS", icon=":material/leaderboard:", url_path="index-rs", default=True)
stock_page = st.Page("pages/stock_rs.py", title="Stock RS + Technical", icon=":material/query_stats:", url_path="stock-rs")

with st.sidebar:
    st.markdown('<div class="sidebar-label">Scanners</div>', unsafe_allow_html=True)
    st.caption("Choose a scanner")
    st.divider()
    st.markdown('<div class="help">PipsGoX market scanners</div>', unsafe_allow_html=True)

pg = st.navigation([index_page, stock_page], position="sidebar")
pg.run()
