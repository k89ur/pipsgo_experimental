from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from io import BytesIO
import json
import threading

import cloudscraper
import pandas as pd


NSE_BASE = "https://www.nseindia.com"
NSE_ARCHIVES_BASE = "https://nsearchives.nseindia.com"
NSE_REPORT_URL = f"{NSE_BASE}/report-detail/display-bulk-and-block-deals"
NSE_REPORTS_API = f"{NSE_BASE}/api/reports"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": NSE_REPORT_URL,
    "Origin": NSE_BASE,
    "X-Requested-With": "XMLHttpRequest",
    "Connection": "keep-alive",
}

REPORT_NAMES = {
    "bulk": "CM - Bulk Deals",
    "block": "CM - Block Deals",
    "short_selling": "CM - Short Selling",
}

_worker_state = threading.local()


def _session():
    session = cloudscraper.create_scraper(browser="chrome")
    session.headers.update(NSE_HEADERS)
    session.get(NSE_BASE, timeout=20)
    try:
        session.get("https://www.nseindia.com/all-reports", timeout=20)
    except Exception:
        pass
    try:
        session.get(NSE_REPORT_URL, timeout=20)
    except Exception:
        pass
    return session


def _worker_session():
    session = getattr(_worker_state, "session", None)
    if session is None:
        session = _session()
        _worker_state.session = session
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


def _column_key(column):
    return "".join(ch for ch in str(column).lower() if ch.isalnum())


def _normalise_columns(frame):
    if frame.empty:
        return frame

    result = frame.copy()
    result.columns = [str(c).strip() for c in result.columns]
    renamed = {}

    for column in result.columns:
        key = _column_key(column)
        if key in {"date", "tradedate", "ssdate", "bddate", "blkdate"} or key.endswith("date"):
            renamed[column] = "date"
        elif key in {"symbol", "sssymbol", "bdsymbol", "blksymbol"} or key.endswith("symbol"):
            renamed[column] = "symbol"
        elif key in {"securityname", "ssname", "bdname", "blkname", "scripname"}:
            renamed[column] = "securityName"
        elif key in {"clientname", "client", "ssclientname", "bdclientname", "blkclientname"}:
            renamed[column] = "clientName"
        elif key in {"buysell", "buyorsell", "buyorsellindicator", "transaction"}:
            renamed[column] = "buySell"
        elif key in {"quantity", "qty", "ssqty", "bdqty", "blkqty", "quantitytraded"}:
            renamed[column] = "qty"
        elif key in {"tradeprice", "tradepriceweightedaverageprice", "weightedaverageprice", "price", "watp"}:
            renamed[column] = "watp"
        elif key == "remarks":
            renamed[column] = "remarks"

    result = result.rename(columns=renamed)
    if result.columns.duplicated().any():
        result = result.loc[:, ~result.columns.duplicated(keep="first")]
    return result


def _request_historical(session, report, from_date, to_date):
    url = f"{NSE_BASE}/api/historical/{report}"
    response = session.get(
        url,
        params={"from": from_date, "to": to_date},
        headers={"Referer": NSE_REPORT_URL, "X-Requested-With": "XMLHttpRequest"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _historical(session, report, from_date, to_date):
    payload = _request_historical(session, report, from_date, to_date)
    return _normalise_columns(pd.DataFrame(_rows(payload)))


def _filter_symbol(frame, symbol):
    if frame.empty or "symbol" not in frame.columns:
        return frame
    wanted = str(symbol).strip().upper()
    return frame[
        frame["symbol"].astype(str).str.strip().str.upper() == wanted
    ].copy()


def _report_csv(session, report_key, trading_date):
    """Download one historical NSE report through the official reports endpoint."""
    archives = [{
        "name": REPORT_NAMES[report_key],
        "type": "daily-reports",
        "category": "capital-market",
        "section": "equities",
    }]
    params = {
        "archives": json.dumps(archives, separators=(",", ":")),
        "date": trading_date.strftime("%d-%b-%Y"),
        "type": "equities",
        "mode": "single",
    }
    response = session.get(
        NSE_REPORTS_API,
        params=params,
        headers={"Referer": "https://www.nseindia.com/all-reports"},
        timeout=20,
    )
    response.raise_for_status()
    content = response.content
    if not content or content.lstrip().startswith(b"<"):
        raise ValueError("NSE returned HTML instead of report data")
    return pd.read_csv(BytesIO(content))


def _archive_historical_symbol(report_key, symbol, start_date, end_date):
    """Fallback for NSE's official date-specific report download route."""
    dates = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)

    if not dates:
        return pd.DataFrame(), []

    frames = []
    failures = []

    def fetch_one(trading_date):
        session = _worker_session()
        try:
            frame = _report_csv(session, report_key, trading_date)
            return trading_date, _filter_symbol(_normalise_columns(frame), symbol), None
        except Exception as exc:
            return trading_date, pd.DataFrame(), str(exc)

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(fetch_one, trading_date) for trading_date in dates]
        for future in as_completed(futures):
            trading_date, frame, error = future.result()
            if not frame.empty:
                frames.append(frame)
            if error:
                failures.append(f"{report_key} {trading_date:%d-%m-%Y}: {error}")

    if not frames:
        return pd.DataFrame(), failures

    return pd.concat(frames, ignore_index=True), failures


def fetch_nse_historical_deals(symbol, days=365):
    """Fetch NSE historical bulk, block and short-selling records for one symbol."""
    end = date.today()
    # NSE documents a maximum one-year historical range. Use an inclusive
    # 365-calendar-day window rather than accidentally requesting 366 dates.
    start = end - timedelta(days=min(max(int(days), 1), 365) - 1)
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
        "failed_reports": [],
    }

    try:
        session = _session()
        frames = {}
        failed_reports = []
        successful_reports = []

        for key, endpoint in (
            ("bulk", "bulk-deals"),
            ("block", "block-deals"),
            ("short_selling", "short-selling"),
        ):
            try:
                frame = _historical(session, endpoint, from_date, to_date)
                frames[key] = _filter_symbol(frame, symbol)
                successful_reports.append(key)
            except Exception as exc:
                frames[key] = pd.DataFrame()
                failed_reports.append(f"{key}: {exc}")

        # If the historical JSON endpoint is blocked, switch to NSE's official
        # report-download route instead of returning a misleading empty result.
        if not successful_reports:
            for key in ("bulk", "block", "short_selling"):
                frame, fallback_failures = _archive_historical_symbol(
                    key, symbol, start, end
                )
                frames[key] = frame
                failed_reports.extend(fallback_failures)
                if not frame.empty:
                    successful_reports.append(key)

        result = {
            **empty,
            **frames,
            "available": bool(successful_reports),
            "failed_reports": failed_reports,
        }
        if not successful_reports:
            result["error"] = "NSE historical deal reports and official archive fallback both failed."
        elif failed_reports:
            result["warning"] = "Some NSE report requests failed; returned successful records are still shown."
        return result
    except Exception as exc:
        return {**empty, "error": str(exc)}
