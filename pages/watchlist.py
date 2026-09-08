import streamlit as st

from watchlist_store import get_watchlist, remove_stock

st.markdown('<div class="page-brand"><span>PIPS</span>GOX</div>', unsafe_allow_html=True)
st.markdown('<div class="page-head"><div class="page-title">Watchlist</div><div class="page-sub">Manually shortlisted stocks for research and monitoring</div></div>', unsafe_allow_html=True)

symbols = get_watchlist()

st.markdown(f'<div class="section-title">My Watchlist · {len(symbols):,}</div>', unsafe_allow_html=True)

if not symbols:
    st.markdown('<div class="empty-state"><div class="empty-title">No stocks yet</div><div class="empty-sub">Use the Watchlist action from Stock RS results to add a shortlisted stock. The detailed research workspace will be added in the next phases.</div></div>', unsafe_allow_html=True)
else:
    for symbol in symbols:
        left, right = st.columns([8, 1], gap="small")
        with left:
            st.markdown(f'<div style="padding:.55rem .7rem;border:1px solid var(--line);border-radius:8px;background:var(--panel);font-weight:650">{symbol}</div>', unsafe_allow_html=True)
        with right:
            if st.button("", icon=":material/star:", type="tertiary", width=30, key=f"watch_remove_{symbol}", help=f"Remove {symbol} from Watchlist"):
                remove_stock(symbol)
                st.rerun()

st.caption("Watchlist storage is currently session-based. Persistent storage will be added before production use.")
