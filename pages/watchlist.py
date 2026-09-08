import pandas as pd
import streamlit as st

from insights_data import fetch_nse, fetch_nse_deals, fetch_screener, search_screener


st.markdown('<div class="page-brand"><span>PIPS</span>GOX</div>', unsafe_allow_html=True)

st.markdown(
    '<div class="page-head"><div class="page-title">Insights</div>'
    '<div class="page-sub">Fundamental, ownership and market-position intelligence</div></div>',
    unsafe_allow_html=True,
)

with st.form("insights_search", clear_on_submit=False):
    query = st.text_input(
        "Search stock",
        value=str(st.query_params.get("symbol", "")).strip().upper(),
        placeholder="Search NSE symbol or company name…",
        label_visibility="collapsed",
    )
    submitted = st.form_submit_button("Search", type="primary", use_container_width=False)

if submitted:
    clean_query = query.strip().upper()
    if clean_query:
        try:
            matches = search_screener(clean_query)
        except Exception as exc:
            st.error(f"Unable to search Screener. ({exc})")
            st.stop()
        if not matches:
            st.warning(f"No company found for '{clean_query}'.")
            st.stop()
        selected = matches[0]
        symbol = str(selected.get("url", "")).split("/company/")[-1].strip("/").split("/")[0].upper()
        if not symbol:
            symbol = clean_query
        st.query_params["symbol"] = symbol
        st.session_state["insights_symbol"] = symbol
        st.rerun()

symbol = str(st.session_state.get("insights_symbol", st.query_params.get("symbol", ""))).strip().upper()

if not symbol:
    st.markdown(
        '<div class="empty-state"><div class="empty-title">Search a stock to open Insights</div>'
        '<div class="empty-sub">Data is fetched on demand from NSE and Screener.in. No scanner calculations are changed.</div></div>',
        unsafe_allow_html=True,
    )
    st.stop()

st.query_params["symbol"] = symbol

@st.cache_data(ttl=900, show_spinner=False)
def cached_screener(stock):
    return fetch_screener(stock)


@st.cache_data(ttl=300, show_spinner=False)
def cached_nse(stock):
    return fetch_nse(stock)


@st.cache_data(ttl=300, show_spinner=False)
def cached_deals(stock):
    return fetch_nse_deals(stock)


def _unique_columns(frame):
    """Make dataframe column labels unique for Streamlit/PyArrow."""
    if frame.empty:
        return frame
    result = frame.copy()
    seen = {}
    columns = []
    for column in result.columns:
        name = str(column)
        count = seen.get(name, 0)
        seen[name] = count + 1
        columns.append(name if count == 0 else f"{name}.{count}")
    result.columns = columns
    return result


try:
    with st.spinner(f"Loading {symbol} Insights…"):
        screener = cached_screener(symbol)
        nse = cached_nse(symbol)
        deals = cached_deals(symbol)
except Exception as exc:
    st.error(f"Unable to load Insights for {symbol}. ({exc})")
    st.stop()

company_name = screener.get("company_name") or symbol
sector = nse.get("sector") or screener.get("sector") or "—"
industry = nse.get("industry") or screener.get("industry") or "—"

st.markdown(
    f'<div class="page-head"><div class="page-title">{company_name}</div>'
    f'<div class="page-sub">{symbol} · {sector} · {industry}</div></div>',
    unsafe_allow_html=True,
)

st.markdown('<div class="section-title">Valuation & company snapshot</div>', unsafe_allow_html=True)
c1, c2, c3, c4, c5 = st.columns(5, gap="small")
with c1:
    st.metric("P/E", f"{screener.get('pe'):.2f}" if screener.get("pe") is not None else "—")
with c2:
    market_cap = nse.get("market_cap") or screener.get("market_cap")
    st.metric("Market Cap", f"₹{market_cap:,.0f} Cr" if market_cap is not None else "—")
with c3:
    st.metric("LTP", f"₹{nse.get('ltp'):,.2f}" if nse.get("ltp") is not None else "—")
with c4:
    st.metric("52W High", f"₹{nse.get('52w_high'):,.2f}" if nse.get("52w_high") is not None else "—")
with c5:
    st.metric("52W Low", f"₹{nse.get('52w_low'):,.2f}" if nse.get("52w_low") is not None else "—")

growth = screener.get("growth")
if isinstance(growth, pd.DataFrame) and not growth.empty:
    st.markdown('<div class="section-title">Growth & margin trend · quarterly YoY</div>', unsafe_allow_html=True)
    chart = growth.set_index("Quarter")[["Sales Growth", "Earning Growth", "Margin"]].copy()
    chart.columns = ["Sales Growth %", "Earning Growth %", "Margin %"]
    st.line_chart(chart, use_container_width=True, height=330)
    st.caption("Sales Growth and Earning Growth are YoY growth rates. Margin is OPM when available from Screener; otherwise it is derived from net profit / sales.")
else:
    st.info("Quarterly growth history is not available from Screener for this company.")

st.markdown('<div class="section-title">Institutional / large deals · NSE</div>', unsafe_allow_html=True)
bulk, block = st.columns(2, gap="large")
with bulk:
    st.markdown("**Bulk deals**")
    bulk_df = deals.get("bulk", pd.DataFrame())
    if bulk_df.empty:
        st.caption("No NSE bulk deal data available for this symbol right now.")
    else:
        cols = [c for c in ["date", "clientName", "buySell", "qty", "watp", "remarks"] if c in bulk_df.columns]
        st.dataframe(_unique_columns(bulk_df[cols]), use_container_width=True, hide_index=True, height=min(300, 70 + len(bulk_df) * 36))
with block:
    st.markdown("**Block deals**")
    block_df = deals.get("block", pd.DataFrame())
    if block_df.empty:
        st.caption("No NSE block deal data available for this symbol right now.")
    else:
        cols = [c for c in ["date", "clientName", "buySell", "qty", "watp", "remarks"] if c in block_df.columns]
        st.dataframe(_unique_columns(block_df[cols]), use_container_width=True, hide_index=True, height=min(300, 70 + len(block_df) * 36))

st.markdown('<div class="section-title">Shareholders</div>', unsafe_allow_html=True)
shareholders = screener.get("shareholders")
if isinstance(shareholders, pd.DataFrame) and not shareholders.empty:
    st.dataframe(_unique_columns(shareholders), use_container_width=True, hide_index=True, height=300)
else:
    st.info("Shareholding pattern is not available from the Screener company page.")

st.markdown('<div class="section-title">Market position</div>', unsafe_allow_html=True)
left, right = st.columns([1.15, 2.85], gap="large")
with left:
    st.markdown(f"**Sector**  \n{sector}")
    st.markdown(f"**Industry**  \n{industry}")
    market_share = screener.get("market_share")
    if market_share is None:
        st.markdown("**Market Share**  \n—")
        st.caption("NSE/Screener do not publish a standardized market-share field for every company.")
    else:
        st.markdown(f"**Market Share**  \n{market_share:.2f}%")
    indices = nse.get("indices") or []
    if indices:
        st.markdown("**NSE indices**")
        st.caption(", ".join(indices))

with right:
    peers = screener.get("peers")
    if isinstance(peers, pd.DataFrame) and not peers.empty:
        peer_display = _unique_columns(peers.copy())
        first_col = peer_display.columns[0]
        peer_display = peer_display.rename(columns={first_col: "Company"})
        st.dataframe(peer_display, use_container_width=True, hide_index=True, height=330)
    else:
        st.info("Peer comparison is not available from Screener for this company.")

st.markdown('<div class="section-title">Company website</div>', unsafe_allow_html=True)
website = screener.get("website")
if website:
    st.link_button("Open company website ↗", website)
else:
    st.caption("Company website was not available in the Screener listing.")

st.caption("Sources: NSE India for market classification, quote data and large deals; Screener.in for valuation, financial trends, shareholding, peers and company website. Data is fetched on demand and cached briefly.")
