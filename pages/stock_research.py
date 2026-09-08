import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

afrom = None
from stock_research import load_price_history, load_research
from watchlist_store import get_watchlist

st.markdown('<div class="page-brand"><span>PIPS</span>GOX</div>', unsafe_allow_html=True)

watch_symbols = get_watchlist()
query_symbol = st.query_params.get("symbol", "")
query_symbol = str(query_symbol).strip().upper()

if watch_symbols:
    default_index = watch_symbols.index(query_symbol) if query_symbol in watch_symbols else 0
    symbol = st.selectbox("Stock", watch_symbols, index=default_index, key="research_symbol")
else:
    symbol = st.text_input("Stock symbol", value=query_symbol, placeholder="e.g. SYRMA").strip().upper()

if not symbol:
    st.markdown('<div class="empty-state"><div class="empty-title">Select a stock</div><div class="empty-sub">Add a stock to Watchlist from Stock RS, then select it here for deeper research.</div></div>', unsafe_allow_html=True)
    st.stop()

st.query_params["symbol"] = symbol

@st.cache_data(ttl=900, show_spinner=False)
def cached_research(stock):
    return load_research(stock)

@st.cache_data(ttl=900, show_spinner=False)
def cached_history(stock):
    return load_price_history(stock)

try:
    with st.spinner("Loading stock research…"):
        research = cached_research(symbol)
        history = cached_history(symbol)
except Exception as exc:
    st.error(f"Unable to load research data for {symbol}. ({exc})")
    st.stop()

info = research["info"]
company = info.get("longName") or info.get("shortName") or symbol

st.markdown(
    f'<div class="page-head"><div class="page-title">{symbol}</div>'
    f'<div class="page-sub">{company} · {research["sector"]} · {research["industry"]}</div></div>',
    unsafe_allow_html=True,
)

if history.empty:
    st.warning(f"Price history is unavailable for {symbol}.")
else:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.78, 0.22],
    )
    fig.add_trace(
        go.Ohlc(
            x=history.index,
            open=history["Open"],
            high=history["High"],
            low=history["Low"],
            close=history["Close"],
            name="OHLC",
            increasing_line_color="#35d07f",
            decreasing_line_color="#ff6673",
        ),
        row=1,
        col=1,
    )
    for window in (20, 50, 150, 200):
        fig.add_trace(
            go.Scatter(
                x=history.index,
                y=history[f"DMA {window}"],
                name=f"{window} DMA",
                mode="lines",
                line={"width": 1},
            ),
            row=1,
            col=1,
        )
    fig.add_trace(
        go.Bar(x=history.index, y=history["Volume"], name="Volume", opacity=0.55),
        row=2,
        col=1,
    )
    fig.update_layout(
        height=610,
        margin={"l": 8, "r": 8, "t": 10, "b": 8},
        paper_bgcolor="#10151c",
        plot_bgcolor="#10151c",
        font={"color": "#cbd2dc", "family": "Inter, sans-serif", "size": 11},
        legend={"orientation": "h", "y": 1.02, "x": 0},
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        dragmode="pan",
    )
    fig.update_xaxes(showgrid=False, rangeslider_visible=False)
    fig.update_yaxes(showgrid=True, gridcolor="#252d38", row=1, col=1)
    fig.update_yaxes(showgrid=False, row=2, col=1)
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "scrollZoom": True})

st.markdown('<div class="section-title">Fundamental & Growth Checklist</div>', unsafe_allow_html=True)

pe = research["pe"]
rev = research["revenue_growth"]
eps = research["eps_growth"]
surprise = research["earnings_surprise"]
margin_delta = research["margin_delta"]
roe = research["roe"]
float_pct = research["float_pct"]
inst_count = research["institutional_count"]

cards = [
    ("P/E", "—" if pe is None else f"{pe:.1f}x"),
    ("Sales growth", "—" if rev is None else f"{rev:+.1f}% YoY"),
    ("Earnings growth", "—" if eps is None else f"{eps:+.1f}% YoY"),
    ("Earnings surprise", "—" if surprise is None else f"{surprise:+.1f}%"),
]
card_cols = st.columns(4)
for col, (label, value) in zip(card_cols, cards):
    with col:
        st.markdown(
            f'<div class="leader"><div class="leader-rank">{label}</div><div class="leader-score">{value}</div></div>',
            unsafe_allow_html=True,
        )

checklist = pd.DataFrame(
    [
        ["Revenue growth accompanying earnings", f"Revenue {_fmt(rev)} · EPS {_fmt(eps)}"],
        ["Earnings surprise", "—" if surprise is None else f"Latest surprise {surprise:+.1f}%"],
        ["Margin expansion", "—" if margin_delta is None else f"Pretax margin Δ {margin_delta:+.1f} pts YoY"],
        ["ROE", "—" if roe is None else f"{roe:.1f}%"],
        ["Institutional sponsorship", "—" if inst_count is None else f"{inst_count} listed institutional holders"],
        ["Industry group strength", "Not scored yet — use stock/industry RS before promotion"],
        ["New product / catalyst", research["news"][0] if research["news"] else "No recent headline available"],
        ["Float / supply-demand", "—" if float_pct is None else f"Float ≈ {float_pct:.1f}% of shares outstanding"],
        ["Avoid melt-ups pre-base", "Manual chart check — parabolic/climactic run-ups increase failure risk"],
    ],
    columns=["Criterion", "Current evidence"],
)

st.dataframe(
    checklist,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Criterion": st.column_config.TextColumn("CRITERION", width="medium"),
        "Current evidence": st.column_config.TextColumn("CURRENT EVIDENCE", width="large"),
    },
)

st.caption("Growth and earnings fields are derived from Yahoo Finance data. Industry strength, catalyst quality, and pre-base melt-up risk are deliberately not presented as automated facts until a dedicated scoring source is added.")


def _fmt(value):
    if value is None:
        return "—"
    try:
        value = float(value)
        if not math.isfinite(value):
            return "—"
        return f"{value:+.1f}%"
    except Exception:
        return "—"
