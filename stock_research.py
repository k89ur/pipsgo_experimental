import math
from typing import Any

import pandas as pd
import yfinance as yf


def _number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception:
        return None


def _same_quarter_pair(row):
    if row is None:
        return None, None
    values = []
    for value in row.tolist():
        number = _number(value)
        if number is not None:
            values.append(number)
    return (values[0], values[4]) if len(values) >= 5 else (values[0], None) if values else (None, None)


def _growth(current, previous):
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1.0) * 100.0


def _safe_info(ticker):
    try:
        return ticker.info or {}
    except Exception:
        return {}


def _safe_frame(loader):
    try:
        frame = loader()
        return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _safe_value(frame, names):
    for name in names:
        if name in frame.index:
            return frame.loc[name]
    return None


def load_research(symbol):
    ticker = yf.Ticker(f"{symbol}.NS")
    info = _safe_info(ticker)
    quarterly = _safe_frame(lambda: ticker.quarterly_income_stmt)

    revenue_row = _safe_value(quarterly, ["Total Revenue", "Operating Revenue"])
    pretax_row = _safe_value(quarterly, ["Pretax Income"])
    eps_row = _safe_value(quarterly, ["Diluted EPS", "Basic EPS"])

    revenue_latest, revenue_yoy_base = _same_quarter_pair(revenue_row)
    eps_latest, eps_yoy_base = _same_quarter_pair(eps_row)
    pretax_latest, pretax_yoy_base = _same_quarter_pair(pretax_row)

    revenue_growth = _growth(revenue_latest, revenue_yoy_base)
    eps_growth = _growth(eps_latest, eps_yoy_base)

    margin_latest = None
    margin_yoy_base = None
    if revenue_latest not in (None, 0) and pretax_latest is not None:
        margin_latest = pretax_latest / revenue_latest * 100.0
    if revenue_yoy_base not in (None, 0) and pretax_yoy_base is not None:
        margin_yoy_base = pretax_yoy_base / revenue_yoy_base * 100.0
    margin_delta = None if margin_latest is None or margin_yoy_base is None else margin_latest - margin_yoy_base

    surprise = None
    earnings_history = _safe_frame(lambda: ticker.get_earnings_history())
    if not earnings_history.empty and "surprisePercent" in earnings_history.columns:
        surprise = _number(earnings_history.iloc[0]["surprisePercent"])

    institutional = _safe_frame(lambda: ticker.get_institutional_holders())
    institutional_count = len(institutional) if not institutional.empty else None

    float_shares = _number(info.get("floatShares"))
    shares_outstanding = _number(info.get("sharesOutstanding"))
    float_pct = None
    if float_shares is not None and shares_outstanding not in (None, 0):
        float_pct = float_shares / shares_outstanding * 100.0

    news = []
    try:
        for item in ticker.get_news(count=5) or []:
            content = item.get("content") or {}
            title = content.get("title") or item.get("title")
            if title:
                news.append(str(title))
    except Exception:
        pass

    roe = _number(info.get("returnOnEquity"))
    return {
        "info": info,
        "pe": _number(info.get("trailingPE")),
        "sector": info.get("sector") or "—",
        "industry": info.get("industry") or "—",
        "revenue_growth": revenue_growth,
        "eps_growth": eps_growth,
        "earnings_surprise": surprise,
        "pretax_margin": margin_latest,
        "margin_delta": margin_delta,
        "roe": roe * 100.0 if roe is not None else None,
        "institutional_count": institutional_count,
        "float_shares": float_shares,
        "shares_outstanding": shares_outstanding,
        "float_pct": float_pct,
        "news": news,
    }


def load_price_history(symbol):
    ticker = yf.Ticker(f"{symbol}.NS")
    history = ticker.history(period="2y", interval="1d", auto_adjust=False)
    if history.empty:
        return history
    history = history.dropna(subset=["Open", "High", "Low", "Close"])
    for window in (20, 50, 150, 200):
        history[f"DMA {window}"] = history["Close"].rolling(window).mean()
    return history
