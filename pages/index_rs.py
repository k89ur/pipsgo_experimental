import streamlit as st
import pandas as pd
from index_rs_engine import run_index_scan

if "index_result" not in st.session_state:
    st.session_state.index_result = None

st.markdown('<div class="app-topline"><span>INDEX RELATIVE STRENGTH / DAILY</span><span class="live-state"><span class="live-dot"></span> LIVE DATA</span></div>', unsafe_allow_html=True)

main, side = st.columns([5.1, 1.05], gap="large")
with side:
    status_slot = st.empty()
    stats_slot = st.empty()

with main:
    st.markdown('<div class="page-head"><div><div class="page-title">Index Relative Strength</div><div class="page-sub">Daily relative-strength ranking across the supported NIFTY index universe</div></div></div>', unsafe_allow_html=True)
    st.markdown('<div class="control-bar">', unsafe_allow_html=True)
    st.markdown('<div class="control-label">Index scanner</div><div class="control-help">Refresh the current TradingView daily index data and ranking</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    run_index = st.button("▶  Refresh index data", type="primary", use_container_width=False, key="index_refresh")

    if run_index or st.session_state.index_result is None:
        progress = status_slot.progress(0, text="Connecting to TradingView…")
        try:
            def update(done, total, message):
                pct = min(done / max(total, 1), 1.0)
                progress.progress(pct, text=f"{message} · {done}/{total}")
                stats_slot.markdown(f"<div class='status-card'><div class='status-head'>Scanner status</div><div class='status-state'><span class='state-dot'></span>Scanning</div><div class='status-item'><div class='status-label'>Progress</div><div class='status-value'>{pct*100:.0f}%</div></div><div class='status-item'><div class='status-label'>Processed</div><div class='status-value'>{done}/{total}</div></div></div>", unsafe_allow_html=True)
            df, stats = run_index_scan(update)
            st.session_state.index_result = df
            st.session_state.index_stats = stats
            progress.progress(1.0, text="Scan complete")
        except Exception as e:
            progress.empty(); status_slot.error("Scan failed"); st.error(f"TradingView data refresh failed: {e}")

    df = st.session_state.index_result
    if df is None:
        status_slot.markdown('<div class="status-card"><div class="status-head">Scanner status</div><div class="status-state"><span class="state-dot"></span>Waiting for scan</div></div>', unsafe_allow_html=True)
        st.markdown('<div class="empty-state"><div class="empty-title">Ready to scan</div><div class="empty-sub">Refresh the index universe to calculate current relative strength.</div></div>', unsafe_allow_html=True)
    else:
        stats = st.session_state.get("index_stats", {})
        valid = df[df["Raw RS"].notna()].copy()
        strong = int((valid["RS 1-99"] >= 80).sum()); middle = int(((valid["RS 1-99"] >= 50) & (valid["RS 1-99"] < 80)).sum()); weak = int((valid["RS 1-99"] < 50).sum())
        asof = stats.get("benchmark_latest", stats.get("as_of")); asof_text = asof.strftime("%d %b %Y") if hasattr(asof, "strftime") else "—"
        unavailable = int(stats.get("unavailable_count", int(df["Latest Date"].isna().sum())))
        stale = int(stats.get("stale_count", 0)); insufficient = int((df["Latest Date"].notna() & df["Raw RS"].isna()).sum())
        status_slot.markdown(f"<div class='status-card'><div class='status-head'>Scanner status</div><div class='status-state'><span class='state-dot'></span>Scan complete</div><div class='status-item'><div class='status-label'>Latest</div><div class='status-value'>{asof_text}</div></div><div class='status-item'><div class='status-label'>Universe</div><div class='status-value'>{stats.get('universe',28)}</div></div><div class='status-item'><div class='status-label'>Calculated</div><div class='status-value strong'>{stats.get('available',0)}</div></div><div class='status-item'><div class='status-label'>Stale</div><div class='status-value'>{stale}</div></div><div class='status-item'><div class='status-label'>Insufficient</div><div class='status-value'>{insufficient}</div></div><div class='status-item'><div class='status-label'>Unavailable</div><div class='status-value'>{unavailable}</div></div><div class='status-item'><div class='status-label'>Strong 80+</div><div class='status-value strong'>{strong}</div></div></div>", unsafe_allow_html=True)

        top = valid.head(3)
        if len(top):
            cards=[]
            for i, (_, row) in enumerate(top.iterrows(),1):
                score=int(row["RS 1-99"]); cards.append(f"<div class='leader-item'><div class='leader-top'><span class='leader-rank'>0{i}</span><span class='leader-score'>{score}</span></div><div class='leader-name'>{row['INDEX']}</div><div class='leader-meta'>Raw RS {row['Raw RS']:.2f}</div></div>")
            st.markdown('<div class="leader-strip">'+''.join(cards)+'</div>',unsafe_allow_html=True)

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
