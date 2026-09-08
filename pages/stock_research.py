import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

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

# Lightweight Charts expects seconds since Unix epoch for daily time values.
chart_rows = []
for timestamp, row in history.iterrows():
    chart_rows.append(
        {
            "time": int(pd.Timestamp(timestamp).timestamp()),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row["Volume"]) if pd.notna(row["Volume"]) else 0,
            "dma20": float(row["DMA 20"]) if pd.notna(row["DMA 20"]) else None,
            "dma50": float(row["DMA 50"]) if pd.notna(row["DMA 50"]) else None,
            "dma150": float(row["DMA 150"]) if pd.notna(row["DMA 150"]) else None,
            "dma200": float(row["DMA 200"]) if pd.notna(row["DMA 200"]) else None,
        }
    )

payload = json.dumps({"symbol": symbol, "rows": chart_rows}, separators=(",", ":"))

chart_html = f"""
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<script src="https://unpkg.com/lightweight-charts@5.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
html,body{{margin:0;padding:0;background:#10151c;color:#cbd2dc;font-family:Inter,system-ui,sans-serif;overflow:hidden}}
#shell{{width:100%;background:#10151c}}
#toolbar{{height:34px;display:flex;align-items:center;gap:5px;padding:0 8px;box-sizing:border-box;border-bottom:1px solid #252d38;white-space:nowrap;overflow-x:auto}}
button{{border:1px solid #252d38;background:#151b23;color:#8993a2;border-radius:5px;height:25px;padding:0 9px;font-size:11px;cursor:pointer}}
button:hover,button.active{{background:#252d38;color:#f3f5f7;border-color:#3b4655}}
#status{{margin-left:auto;color:#8993a2;font-size:10px;padding-left:8px}}
#chart{{width:100%;height:650px}}
@media(max-width:700px){{#toolbar{{height:36px;padding:0 6px;gap:4px}}button{{height:27px;padding:0 8px;font-size:11px}}#chart{{height:560px}}#status{{display:none}}}}
</style>
</head>
<body>
<div id="shell">
  <div id="toolbar">
    <button data-range="3m">3M</button>
    <button data-range="6m">6M</button>
    <button data-range="1y">1Y</button>
    <button data-range="2y">2Y</button>
    <button data-range="all">ALL</button>
    <button id="fit">FIT</button>
    <span id="status"></span>
  </div>
  <div id="chart"></div>
</div>
<script>
const payload = {payload};
const rows = payload.rows;
const chartHost = document.getElementById('chart');
const toolbar = document.getElementById('toolbar');
const status = document.getElementById('status');

const chart = LightweightCharts.createChart(chartHost, {{
  autoSize: true,
  layout: {{
    background: {{ type: 'solid', color: '#10151c' }},
    textColor: '#aab3bf',
    fontFamily: 'Inter, system-ui, sans-serif',
    fontSize: 11,
  }},
  grid: {{
    vertLines: {{ color: '#1c232d' }},
    horzLines: {{ color: '#252d38' }},
  }},
  rightPriceScale: {{
    borderColor: '#252d38',
    scaleMargins: {{ top: 0.08, bottom: 0.24 }},
  }},
  timeScale: {{
    borderColor: '#252d38',
    timeVisible: false,
    rightOffset: 5,
    barSpacing: 6,
    minBarSpacing: 2,
  }},
  crosshair: {{
    mode: LightweightCharts.CrosshairMode.Normal,
    vertLine: {{ color: '#8993a2', width: 1, style: LightweightCharts.LineStyle.Dashed, labelBackgroundColor: '#252d38' }},
    horzLine: {{ color: '#8993a2', width: 1, style: LightweightCharts.LineStyle.Dashed, labelBackgroundColor: '#252d38' }},
  }},
  handleScroll: {{
    mouseWheel: true,
    pressedMouseMove: true,
    horzTouchDrag: true,
    vertTouchDrag: false,
  }},
  handleScale: {{
    mouseWheel: true,
    pinch: true,
    axisPressedMouseMove: true,
    axisDoubleClickReset: true,
  }},
  kineticScroll: {{ mouse: true, touch: true }},
}});

const barSeries = chart.addSeries(LightweightCharts.BarSeries, {{
  upColor: '#35d07f',
  downColor: '#ff6673',
  openVisible: true,
  thinBars: true,
  priceLineVisible: false,
  lastValueVisible: true,
}});

const dma20 = chart.addSeries(LightweightCharts.LineSeries, {{ color: '#3b82f6', lineWidth: 1, priceLineVisible: false, lastValueVisible: false }});
const dma50 = chart.addSeries(LightweightCharts.LineSeries, {{ color: '#d9a6a6', lineWidth: 1, priceLineVisible: false, lastValueVisible: false }});
const dma150 = chart.addSeries(LightweightCharts.LineSeries, {{ color: '#ef4444', lineWidth: 1, priceLineVisible: false, lastValueVisible: false }});
const dma200 = chart.addSeries(LightweightCharts.LineSeries, {{ color: '#63c48b', lineWidth: 1, priceLineVisible: false, lastValueVisible: false }});

const volumeSeries = chart.addSeries(LightweightCharts.HistogramSeries, {{
  priceFormat: {{ type: 'volume' }},
  priceScaleId: '',
  color: '#3a8f7a',
  priceLineVisible: false,
  lastValueVisible: false,
}});
volumeSeries.priceScale().applyOptions({{ scaleMargins: {{ top: 0.82, bottom: 0.02 }} }});

barSeries.setData(rows.map(r => ({{ time:r.time, open:r.open, high:r.high, low:r.low, close:r.close }})));
dma20.setData(rows.filter(r => r.dma20 !== null).map(r => ({{ time:r.time, value:r.dma20 }})));
dma50.setData(rows.filter(r => r.dma50 !== null).map(r => ({{ time:r.time, value:r.dma50 }})));
dma150.setData(rows.filter(r => r.dma150 !== null).map(r => ({{ time:r.time, value:r.dma150 }})));
dma200.setData(rows.filter(r => r.dma200 !== null).map(r => ({{ time:r.time, value:r.dma200 }})));
volumeSeries.setData(rows.map(r => ({{ time:r.time, value:r.volume, color:r.close >= r.open ? 'rgba(53,208,127,.42)' : 'rgba(255,102,115,.42)' }})));

chart.subscribeCrosshairMove(param => {{
  if (!param.time || !param.seriesData) {{ status.textContent = ''; return; }}
  const bar = param.seriesData.get(barSeries);
  if (bar) {{
    const date = new Date(Number(bar.time) * 1000).toLocaleDateString(undefined, {{ day:'2-digit', month:'short', year:'numeric' }});
    status.textContent = `${{date}}  O ${{bar.open.toFixed(2)}}  H ${{bar.high.toFixed(2)}}  L ${{bar.low.toFixed(2)}}  C ${{bar.close.toFixed(2)}}`;
  }}
}});

function setRange(range) {{
  if (!rows.length) return;
  let start = 0;
  if (range !== 'all') {{
    const days = range === '3m' ? 92 : range === '6m' ? 183 : range === '1y' ? 365 : 730;
    const cutoff = rows[rows.length - 1].time - days * 86400;
    start = rows.findIndex(r => r.time >= cutoff);
    if (start < 0) start = 0;
  }}
  chart.timeScale().setVisibleRange({{ from: rows[start].time, to: rows[rows.length - 1].time }});
  document.querySelectorAll('[data-range]').forEach(b => b.classList.toggle('active', b.dataset.range === range));
}}

toolbar.addEventListener('click', event => {{
  const button = event.target.closest('button');
  if (!button) return;
  if (button.dataset.range) setRange(button.dataset.range);
  if (button.id === 'fit') chart.timeScale().fitContent();
}});

setRange('1y');
</script>
</body>
</html>
"""

components.html(chart_html, height=700, scrolling=False)

st.caption("TradingView Lightweight Charts · OHLC bars · 20 / 50 / 150 / 200 DMA · volume · pinch zoom · drag/pan · crosshair.")
