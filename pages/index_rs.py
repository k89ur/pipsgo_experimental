import streamlit as st
import pandas as pd
from index_rs_engine import run_index_scan

if "index_result" not in st.session_state:
    st.session_state.index_result = None

# UI ONLY: Index RS visual layer. Scanner engine and calculations are unchanged.
st.markdown("""
<style>
.index-ui-brand{display:flex;align-items:center;gap:8px;margin:0 0 18px;font-size:15px;font-weight:800;letter-spacing:.25em;color:#eef2f0}.index-ui-brand-mark{width:6px;height:6px;border-radius:50%;background:#48d39a;box-shadow:0 0 7px rgba(72,211,154,.5)}
.index-ui-kicker{font-size:9px;color:#626c69;letter-spacing:.18em;text-transform:uppercase;margin-bottom:7px}.index-ui-title{font-size:28px;font-weight:700;letter-spacing:-.04em;line-height:1.08;color:#eef2f0}.index-ui-subtitle{font-size:10px;color:#737d7a;margin-top:6px}
.index-ui-scan{margin-top:20px;border-top:1px solid #29302f;border-bottom:1px solid #29302f;padding:11px 0 10px}.index-ui-scan-title{font-size:11px;font-weight:650;color:#dfe5e2}.index-ui-scan-copy{font-size:9px;color:#68726f;margin-top:3px}.index-ui-scan-action{margin-top:9px}
.index-ui-status{border:1px solid #29302f;background:#0e1213;overflow:hidden}.index-ui-status-head{padding:10px 11px;border-bottom:1px solid #29302f;font-size:8px;color:#626c69;letter-spacing:.16em;text-transform:uppercase}.index-ui-status-state{padding:10px 11px;border-bottom:1px solid #29302f;font-size:10px;font-weight:650;color:#e1e6e4;display:flex;align-items:center;gap:6px}.index-ui-status-dot{width:6px;height:6px;border-radius:50%;background:#48d39a;box-shadow:0 0 7px rgba(72,211,154,.45)}.index-ui-stat{padding:8px 11px;border-bottom:1px solid #202625}.index-ui-stat:last-child{border-bottom:0}.index-ui-stat-label{font-size:7px;color:#596360;letter-spacing:.12em;text-transform:uppercase}.index-ui-stat-value{font-size:10px;color:#d5dbd8;font-weight:600;margin-top:3px}.index-ui-stat-value.green{color:#48d39a}
.index-ui-leader-label{font-size:8px;color:#626c69;letter-spacing:.16em;text-transform:uppercase;margin:18px 0 7px}.index-ui-leaders{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-top:1px solid #29302f;border-bottom:1px solid #29302f}.index-ui-leader{padding:10px 12px;border-right:1px solid #29302f;min-width:0}.index-ui-leader:last-child{border-right:0}.index-ui-leader-rank{font-size:8px;color:#596360}.index-ui-leader-main{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:5px}.index-ui-leader-name{font-size:10px;font-weight:650;color:#e0e5e3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.index-ui-leader-score{font-size:19px;line-height:1;font-weight:750;color:#48d39a}.index-ui-leader-raw{font-size:8px;color:#596360;margin-top:4px}
@media(max-width:900px){.index-ui-title{font-size:23px}.index-ui-leaders{grid-template-columns:1fr}.index-ui-leader{border-right:0;border-bottom:1px solid #29302f}.index-ui-leader:last-child{border-bottom:0}}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="index-ui-brand"><span class="index-ui-brand-mark"></span><span>PIPSGOX</span></div>', unsafe_allow_html=True)
st.markdown('<div class="index-ui-kicker">INDEX RELATIVE STRENGTH / DAILY</div>', unsafe_allow_html=True)
st.markdown('<div class="index-ui-title">Index Relative Strength</div>', unsafe_allow_html=True)
st.markdown('<div class="index-ui-subtitle">Daily relative-strength ranking across the supported NIFTY index universe</div>', unsafe_allow_html=True)

main, side = st.columns([5.1, 1.05], gap="large")
with side:
    st.markdown('<div class="index-ui-status"><div class="index-ui-status-head">Scanner status</div>', unsafe_allow_html=True)
    status_slot = st.empty(); stats_slot = st.empty()
    st.markdown('</div>', unsafe_allow_html=True)

with main:
    st.markdown('<div class="index-ui-scan"><div class="index-ui-scan-title">Index scanner</div><div class="index-ui-scan-copy">Refresh the current TradingView daily index data and ranking</div><div class="index-ui-scan-action">', unsafe_allow_html=True)
    run_index = st.button("▶  Refresh index data", type="primary", key="index_refresh")
    st.markdown('</div></div>', unsafe_allow_html=True)

    if run_index or st.session_state.index_result is None:
        progress = status_slot.progress(0, text="Connecting to TradingView…")
        try:
            def update(done, total, message):
                pct = min(done / max(total, 1), 1.0)
                progress.progress(pct, text=f"{message} · {done}/{total}")
                stats_slot.markdown(f"<div class='index-ui-status-state'><span class='index-ui-status-dot'></span>Scanning</div><div class='index-ui-stat'><div class='index-ui-stat-label'>Progress</div><div class='index-ui-stat-value'>{pct*100:.0f}%</div></div><div class='index-ui-stat'><div class='index-ui-stat-label'>Processed</div><div class='index-ui-stat-value'>{done}/{total}</div></div>", unsafe_allow_html=True)
            df, stats = run_index_scan(update)
            st.session_state.index_result = df; st.session_state.index_stats = stats
            progress.progress(1.0, text="Scan complete")
        except Exception as e:
            progress.empty(); status_slot.error("Scan failed"); st.error(f"TradingView data refresh failed: {e}")

    df = st.session_state.index_result
    if df is None:
        status_slot.markdown('<div class="index-ui-status-state"><span class="index-ui-status-dot"></span>Waiting for scan</div>', unsafe_allow_html=True)
        stats_slot.markdown('<div class="index-ui-stat"><div class="index-ui-stat-label">Status</div><div class="index-ui-stat-value">Ready</div></div>', unsafe_allow_html=True)
    else:
        stats = st.session_state.get("index_stats", {}); valid = df[df["Raw RS"].notna()].copy()
        strong = int((valid["RS 1-99"] >= 80).sum()); middle = int(((valid["RS 1-99"] >= 50) & (valid["RS 1-99"] < 80)).sum()); weak = int((valid["RS 1-99"] < 50).sum())
        asof = stats.get("benchmark_latest", stats.get("as_of")); asof_text = asof.strftime("%d %b %Y") if hasattr(asof, "strftime") else "—"
        unavailable = int(stats.get("unavailable_count", int(df["Latest Date"].isna().sum())))
        stale = int(stats.get("stale_count", 0)); insufficient = int((df["Latest Date"].notna() & df["Raw RS"].isna()).sum())
        status_slot.markdown(f"<div class='index-ui-status-state'><span class='index-ui-status-dot'></span>Scan complete</div><div class='index-ui-stat'><div class='index-ui-stat-label'>Latest</div><div class='index-ui-stat-value'>{asof_text}</div></div><div class='index-ui-stat'><div class='index-ui-stat-label'>Universe</div><div class='index-ui-stat-value'>{stats.get('universe',28)}</div></div><div class='index-ui-stat'><div class='index-ui-stat-label'>Calculated</div><div class='index-ui-stat-value green'>{stats.get('available',0)}</div></div><div class='index-ui-stat'><div class='index-ui-stat-label'>Stale</div><div class='index-ui-stat-value'>{stale}</div></div><div class='index-ui-stat'><div class='index-ui-stat-label'>Insufficient</div><div class='index-ui-stat-value'>{insufficient}</div></div><div class='index-ui-stat'><div class='index-ui-stat-label'>Unavailable</div><div class='index-ui-stat-value'>{unavailable}</div></div><div class='index-ui-stat'><div class='index-ui-stat-label'>Strong 80+</div><div class='index-ui-stat-value green'>{strong}</div></div></div>", unsafe_allow_html=True)

        top = valid.head(3)
        if len(top):
            cards=[]
            for i, (_, row) in enumerate(top.iterrows(),1):
                score=int(row["RS 1-99"]); cards.append(f"<div class='index-ui-leader'><div class='index-ui-leader-rank'>0{i}</div><div class='index-ui-leader-main'><div class='index-ui-leader-name'>{row['INDEX']}</div><div class='index-ui-leader-score'>{score}</div></div><div class='index-ui-leader-raw'>Raw RS {row['Raw RS']:.2f}</div></div>")
            st.markdown('<div class="index-ui-leader-label">Top relative strength</div><div class="index-ui-leaders">'+''.join(cards)+'</div>',unsafe_allow_html=True)

        st.markdown(f'<div class="results-head"><div class="results-title">Results <span class="results-count">{len(valid):,}</span></div></div>',unsafe_allow_html=True)
        search_col, filter_col = st.columns([2.8,1.7])
        with search_col: search=st.text_input("Search",placeholder="Search index…",label_visibility="collapsed",key="index_search")
        with filter_col: filter_mode=st.selectbox("Filter",["All","Strong · 80+","Middle · 50–79","Weak · <50","Unavailable"],label_visibility="collapsed",key="index_filter")
        view=df.copy()
        if search: view=view[view["INDEX"].str.contains(search,case=False,na=False)]
        if filter_mode=="Strong · 80+": view=view[view["RS 1-99"]>=80]
        elif filter_mode=="Middle · 50–79": view=view[(view["RS 1-99"]>=50)&(view["RS 1-99"]<80)]
        elif filter_mode=="Weak · <50": view=view[(view["RS 1-99"]<50)&view["RS 1-99"].notna()]
        elif filter_mode=="Unavailable": view=view[view["RS 1-99"].isna()]
        show=view[["Rank","INDEX","RS 1-99","Raw RS","3M %","6M %","9M %","12M %","LTP","Bars","First Date","Latest Date","Status"]].copy(); show["Rank"]=show["Rank"].astype(int)
        show.insert(2,"Strength",show["RS 1-99"].map(lambda s:"N/A" if pd.isna(s) else ("Strong" if s>=80 else ("Middle" if s>=50 else "Weak"))))
        def style(row):
            styles=[""]*len(row); score=row["RS 1-99"]; fg="#7d8796" if pd.isna(score) else ("#48d39a" if score>=80 else ("#e8b84f" if score>=50 else "#ed7180")); s=f"color:{fg};font-weight:700;"; styles[row.index.get_loc("Strength")]=s; styles[row.index.get_loc("RS 1-99")]=s; return styles
        show["TradingView"]=show["INDEX"].map(lambda x:f"https://www.tradingview.com/chart/?symbol=NSE%3A{x}")
        all_columns=list(show.columns); saved_columns=st.session_state.get("index_columns",all_columns); saved_columns=[c for c in saved_columns if c in all_columns] or all_columns; shown_for_table=show[saved_columns]
        st.dataframe(shown_for_table.style.apply(style,axis=1),use_container_width=True,hide_index=True,height=min(700,95+max(len(shown_for_table),1)*36),column_config={"Rank":st.column_config.NumberColumn("#",width="small"),"INDEX":st.column_config.TextColumn("INDEX",width="medium"),"Strength":st.column_config.TextColumn("STRENGTH",width="small"),"RS 1-99":st.column_config.NumberColumn("RS",format="%d",width="small"),"Raw RS":st.column_config.NumberColumn("RAW RS",format="%.2f",width="small"),"3M %":st.column_config.NumberColumn("3M",format="%.2f"),"6M %":st.column_config.NumberColumn("6M",format="%.2f"),"9M %":st.column_config.NumberColumn("9M",format="%.2f"),"12M %":st.column_config.NumberColumn("12M",format="%.2f"),"LTP":st.column_config.NumberColumn("LTP",format="%.2f"),"Bars":st.column_config.NumberColumn("BARS",format="%d",width="small"),"First Date":st.column_config.DateColumn("FIRST DATE",format="DD MMM YYYY",width="medium"),"Latest Date":st.column_config.DateColumn("LATEST DATE",format="DD MMM YYYY",width="medium"),"Status":st.column_config.TextColumn("STATUS",width="small"),"TradingView":st.column_config.LinkColumn("CHART",display_text="Open ↗",width="small")})
        eye_action,csv_action,_=st.columns([.8,1.8,7.4])
        with eye_action:
            with st.popover(":material/visibility:",use_container_width=True):
                st.caption("Columns"); st.multiselect("Show columns",all_columns,default=saved_columns,label_visibility="collapsed",key="index_columns")
        with csv_action:
            st.download_button("Export CSV",show.to_csv(index=False).encode("utf-8"),"nifty_index_rs.csv","text/csv",use_container_width=True,key="index_csv")
        st.markdown(f'<div class="table-foot">Showing {len(shown_for_table):,} of {len(df):,} indices · sorted by RS</div>',unsafe_allow_html=True)
        st.markdown('<div class="legend"><span class="dot" style="background:#48d39a"></span>Strong 80–99 <span class="dot" style="background:#e8b84f"></span>Middle 50–79 <span class="dot" style="background:#ed7180"></span>Weak 1–49</div>',unsafe_allow_html=True)
