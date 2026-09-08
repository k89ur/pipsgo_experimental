from datetime import date, timedelta

import cloudscraper
import pandas as pd


NSE_BASE = "https://www.nseindia.com"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/136.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{NSE_BASE}/",
    "X-Requested-With": "XMLHttpRequest",
}


def _session():
    session = cloudscraper.create_scraper(browser="chrome")
    session.headers.update(NSE_HEADERS)
    session.get(NSE_BASE, timeout=20)
    return session


def _rows(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("data", "records", "rows", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _normalise_columns(frame):
    if frame.empty:
        return frame
    result = frame.copy()
    result.columns = [str(c).strip() for c in result.columns]
    aliases = {}
    for column in result.columns:
        key = "".join(ch for ch in column.lower() if ch.isalnum())
        aliases.update({
            "date": "date",
            "tradedate": "date",
            "ssdate": "date",
            "symbol": "symbol",
            "sssymbol": "symbol",
            "securityname": "securityName",
            "ssname": "securityName",
            "clientname": "clientName",
            "buysell": "buySell",
            "quantity": "qty",
            "qty": "qty",
            "ssqty": "qty",
            "tradeprice": "watp",
            "tradepriceweightedaverageprice": "watp",
            "watp": "watp",
            "remarks": "remarks",
        })
        if key in aliases:
            result = result.rename(columns={column: aliases[key]})
    return result


def _historical(session, report, from_date, to_date):
    url = f"{NSE_BASE}/api/historical/{report}"
    response = session.get(
        url,
        params={"from": from_date, "to": to_date},
        timeout=25,
    )
    response.raise_for_status()
    return _normalise_columns(pd.DataFrame(_rows(response.json())))


def fetch_nse_historical_deals(symbol, days=365):
    """Fetch NSE historical bulk, block and short-selling records for one symbol."""
    end = date.today()
    start = end - timedelta(days=min(max(int(days), 1), 365))
    from_date = start.strftime("%d-%m-%Y")
    to_date = end.strftime("%d-%m-%Y")

    empty = {
        "bulk": pd.DataFrame(),
        "block": pd.DataFrame(),
        "short_selling": pd.DataFrame(),
        "from_date": from_date,
        "to_date": to_date,
        "source": "NSE historical deal reports",
        "available": False,
    }

    try:
        session = _session()
        frames = {}
        for key, endpoint in (
            ("bulk", "bulk-deals"),
            ("block", "block-deals"),
            ("short_selling", "short-selling"),
        ):
            try:
                frame = _historical(session, endpoint, from_date, to_date)
                if "symbol" in frame.columns:
                    frame = frame[frame["symbol"].astype(str).str.strip().str.upper() == symbol.upper()].copy()
                frames[key] = frame
            except Exception:
                frames[key] = pd.DataFrame()

        result = {**empty, **frames, "available": True}
        return result
    except Exception as exc:
        return {**empty, "error": str(exc)}
