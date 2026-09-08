import pandas as pd
import streamlit as st
import yfinance as yf

from watchlist_store import get_watchlist_records, remove_stock

st.markdown('<div class="page-brand"><span>PIPS</span>GOX</div>', unsafe_allow_html=True)
st.markdown('<div class="page-head"><div class="page-title">Watchlist Monitor</div><div class="page-sub">Compact market monitor for your 15-day shortlist</div></div>', unsafe_allow_html=True)

records = get_watchlist_records()
symbols = [record["symbol"] for record in records]

st.markdown(f'<div class="section-title watchlist-section-title">My Watchlist · {len(symbols):,}</div>', unsafe_allow_html=True)
st.markdown('<div style="height:.35rem"></div>', unsafe_allow_html=True)

if not symbols:
    st.markdown('<div class="empty-state"><div class="empty-title">No stocks yet</div><div class="empty-sub">Use the Watchlist action from Stock RS results to add a shortlisted stock.</div></div>', unsafe_allow_html=True)
    st.caption("Watchlist is stored in this browser and each stock expires automatically 15 days after it is added.")
    st.stop()

# Use the latest scan data already available in this Streamlit session when possible.
scan_frames = []
for key in ("stock_result", "fno_result"):
    frame = st.session_state.get(key)
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        scan_frames.append(frame)

if scan_frames:
    market = pd.concat(scan_frames, ignore_index=True)
    market["Symbol"] = market["Symbol"].astype(str).str.strip().str.upper()
    market = market.drop_duplicates("Symbol", keep="first").set_index("Symbol")
else:
    market = pd.DataFrame().set_index(pd.Index([], name="Symbol"))

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_classification(symbol):
    try:
        info = yf.Ticker(f"{symbol}.NS").info
        return info.get("sector") or "—", info.get("industry") or "—"
    except Exception:
        return "—", "—"

rows = []
for record in records:
    symbol = record["symbol"]
    row = market.loc[symbol].to_dict() if symbol in market.index else {}
    sector = row.get("Sector") or row.get("sector")
    industry = row.get("Industry") or row.get("industry")
    if not sector or not industry:
        fetched_sector, fetched_industry = fetch_classification(symbol)
        sector = sector or fetched_sector
        industry = industry or fetched_industry
    rows.append(
        {
            "Watch": True,
            "Symbol": symbol,
            "LTP": row.get("LTP"),
            "RS": row.get("RS Rating"),
            "Sector": sector or "—",
            "Industry": industry or "—",
        }
    )

monitor = pd.DataFrame(rows)

column_config = {
    "Watch": st.column_config.CheckboxColumn("☆", width="small", help="Remove this stock from Watchlist"),
    "Symbol": st.column_config.TextColumn("SYMBOL", width="small", pinned=True),
    "LTP": st.column_config.NumberColumn("LTP", format="₹%.2f", width="small"),
    "RS": st.column_config.NumberColumn("RS", format="%d", width="small"),
    "Sector": st.column_config.TextColumn("SECTOR", width="medium"),
    "Industry": st.column_config.TextColumn("INDUSTRY", width="medium"),
}

disabled = [column for column in monitor.columns if column != "Watch"]
edited = st.data_editor(
    monitor,
    use_container_width=True,
    hide_index=True,
    height=min(650, 72 + max(len(monitor), 1) * 34),
    row_height=32,
    column_config=column_config,
    disabled=disabled,
    key="watchlist_monitor_editor",
)

for symbol, after in zip(symbols, edited["Watch"].tolist()):
    if not bool(after):
        remove_stock(symbol)

st.caption("LTP and RS use the latest Stock RS data available in this session. Sector and Industry are read from Yahoo Finance when scan data does not include them.")
