import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stock_research import load_price_history
from watchlist_store import get_watchlist

st.markdown('<div class="page-brand"><span>PIPS</span>GOX</div>', unsafe_allow_html=True)

watch_symbols = get_watchlist()
query_symbol = str(st.query_params.get("symbol", "")).strip().upper()

if watch_symbols:
    default_index = watch_symbols.index(query_symbol) if query_symbol in watch_symbols else 0
    symbol = st.selectbox("Stock", watch_symbols, index=default_index, key="research_symbol")
else:
    symbol = st.text_input("Stock symbol", value=query_symbol, placeholder="e.g. SYRMA").strip().upper()

if not symbol:
    st.markdown(
        '<div class="empty-state"><div class="empty-title">Select a stock</div>'
        '<div class="empty-sub">Add a stock to Watchlist from Stock RS, then select it here.</div></div>',
        unsafe_allow_html=True,
    )
    st.stop()

st.query_params["symbol"] = symbol

@st.cache_data(ttl=900, show_spinner=False)
def cached_history(stock):
    return load_price_history(stock)

try:
    with st.spinner("Loading price history…"):
        history = cached_history(symbol)
except Exception as exc:
    st.error(f"Unable to load price history for {symbol}. ({exc})")
    st.stop()

st.markdown(
    f'<div class="page-head"><div class="page-title">{symbol}</div>'
    '<div class="page-sub">Price & technical research</div></div>',
    unsafe_allow_html=True,
)

if history.empty:
    st.warning(f"Price history is unavailable for {symbol}.")
    st.stop()

# Build true OHLC bar marks: vertical high-low bar with open/close ticks.
x_values = history.index
high = history["High"].astype(float)
low = history["Low"].astype(float)
open_ = history["Open"].astype(float)
close = history["Close"].astype(float)

bar_x = []
bar_y = []
open_x = []
open_y = []
close_x = []
close_y = []

for x, o, h, l, c in zip(x_values, open_, high, low, close):
    bar_x.extend([x, x, None])
    bar_y.extend([l, h, None])
    open_x.extend([x, x, None])
    open_y.extend([o, o, None])
    close_x.extend([x, x, None])
    close_y.extend([c, c, None])

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=bar_x,
        y=bar_y,
        mode="lines",
        name="Price bar",
        line={"width": 1},
        hoverinfo="skip",
    )
)
fig.add_trace(
    go.Scatter(
        x=open_x,
        y=open_y,
        mode="lines",
        name="Open",
        line={"width": 1},
        hoverinfo="skip",
    )
)
fig.add_trace(
    go.Scatter(
        x=close_x,
        y=close_y,
        mode="lines",
        name="Close",
        line={"width": 1},
        hoverinfo="skip",
    )
)

for window in (20, 50, 150, 200):
    fig.add_trace(
        go.Scatter(
            x=history.index,
            y=history[f"DMA {window}"],
            name=f"{window} DMA",
            mode="lines",
            line={"width": 1},
        )
    )

fig.add_trace(
    go.Bar(
        x=history.index,
        y=history["Volume"],
        name="Volume",
        opacity=0.45,
        yaxis="y2",
        hovertemplate="Volume: %{y:,}<extra></extra>",
    )
)

fig.update_layout(
    height=680,
    margin={"l": 8, "r": 8, "t": 12, "b": 8},
    paper_bgcolor="#10151c",
    plot_bgcolor="#10151c",
    font={"color": "#cbd2dc", "family": "Inter, sans-serif", "size": 11},
    legend={"orientation": "h", "y": 1.02, "x": 0},
    hovermode="x unified",
    dragmode="pan",
    xaxis={"showgrid": False, "rangeslider": {"visible": False}},
    yaxis={"domain": [0.22, 1], "showgrid": True, "gridcolor": "#252d38"},
    yaxis2={"domain": [0, 0.17], "showgrid": False, "showticklabels": True},
    showlegend=True,
)

fig.update_traces(selector={"name": "Volume"}, marker_line_width=0)

st.plotly_chart(
    fig,
    use_container_width=True,
    config={
        "displaylogo": False,
        "scrollZoom": True,
        "displayModeBar": True,
        "modeBarButtonsToRemove": ["select2d", "lasso2d"],
    },
)

st.caption("OHLC bar chart · 20 / 50 / 150 / 200 DMA · volume. Fundamental research will be added later.")
