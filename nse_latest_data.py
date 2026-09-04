from __future__ import annotations

import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

NSE_BHAVCOPY_URLS = (
    "https://archives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv",
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv",
)
NSE_HOME = "https://www.nseindia.com/"
IST = ZoneInfo("Asia/Kolkata")
EQUITY_CLOSE_TIME = (15, 30)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0 Safari/537.36",
    "Accept": "text/csv,application/octet-stream,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_HOME,
    "Connection": "keep-alive",
}


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(NSE_HOME, timeout=8)
    except Exception:
        pass
    return session


def _read_bhavcopy(content: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(content))
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    required = {"SYMBOL", "SERIES", "DATE1", "CLOSE_PRICE"}
    if not required.issubset(df.columns):
        raise ValueError(f"NSE bhavcopy missing columns: {sorted(required - set(df.columns))}")
    return df


def fetch_latest_nse_close(max_lookback_days: int = 5, require_today: bool = False) -> tuple[str, dict[str, float]]:
    """Return the newest available NSE cash-market EQ close map."""
    now = datetime.now(IST)
    today = now.date()
    if require_today and (now.hour, now.minute) < EQUITY_CLOSE_TIME:
        raise RuntimeError("Today's NSE EOD data is not available before 15:30 IST.")

    session = _make_session()
    last_error = None
    end_offset = 0 if require_today else max_lookback_days
    for offset in range(0, end_offset + 1):
        day = today - timedelta(days=offset)
        date_str = day.strftime("%d%m%Y")
        for template in NSE_BHAVCOPY_URLS:
            url = template.format(date=date_str)
            try:
                response = session.get(url, timeout=12)
                response.raise_for_status()
                if not response.content or response.content.lstrip().startswith(b"<"):
                    raise ValueError("NSE returned non-CSV content")
                df = _read_bhavcopy(response.content)
                df["SERIES"] = df["SERIES"].astype(str).str.strip().str.upper()
                df = df[df["SERIES"].eq("EQ")].copy()
                df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip().str.upper()
                df["CLOSE_PRICE"] = pd.to_numeric(df["CLOSE_PRICE"], errors="coerce")
                df = df.dropna(subset=["SYMBOL", "CLOSE_PRICE"])
                df = df[df["CLOSE_PRICE"] > 0].drop_duplicates("SYMBOL", keep="last")
                if not df.empty:
                    actual_date = pd.to_datetime(df["DATE1"].iloc[0], errors="coerce")
                    if pd.notna(actual_date):
                        actual_day = actual_date.date()
                        if require_today and actual_day != today:
                            raise ValueError(f"NSE returned bhavcopy dated {actual_day}, expected {today}")
                        return actual_day.isoformat(), dict(zip(df["SYMBOL"], df["CLOSE_PRICE"].astype(float)))
            except Exception as exc:
                last_error = exc
    if require_today:
        raise RuntimeError(f"Today's NSE EOD bhavcopy is not available yet: {last_error}")
    raise RuntimeError(f"Unable to retrieve a recent NSE bhavcopy: {last_error}")


def _download_raw_recent(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Download short unadjusted histories used only to derive adjustment factors."""
    result: dict[str, pd.DataFrame] = {}
    for start in range(0, len(symbols), 100):
        group = symbols[start:start + 100]
        try:
            raw = yf.download(
                tickers=[f"{s}.NS" for s in group],
                period="10d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                group_by="ticker",
                threads=True,
            )
            if raw is None or raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                level0 = set(raw.columns.get_level_values(0))
                level1 = set(raw.columns.get_level_values(1))
                for symbol in group:
                    ticker = f"{symbol}.NS"
                    try:
                        if ticker in level0:
                            x = raw[ticker].copy()
                        elif ticker in level1:
                            x = raw.xs(ticker, axis=1, level=1).copy()
                        else:
                            continue
                        if "Close" not in x.columns:
                            continue
                        x.index = pd.to_datetime(x.index, errors="coerce").tz_localize(None)
                        x = x[~x.index.isna()].sort_index()
                        x["Close"] = pd.to_numeric(x["Close"], errors="coerce")
                        x = x.dropna(subset=["Close"])
                        if not x.empty:
                            result[symbol] = x
                    except Exception:
                        continue
        except Exception:
            continue
    return result


def patch_snapshot(snapshot: dict, progress_callback=None) -> dict:
    """Overlay the official NSE close for EOD scans while preserving Yahoo adjusted-price scale."""
    data = snapshot.get("data", {})
    if not data or str(snapshot.get("mode", "eod")).lower() != "eod":
        return snapshot
    if progress_callback:
        progress_callback(0, 1, "Loading latest NSE bhavcopy")
    nse_date, closes = fetch_latest_nse_close(require_today=True)
    raw_recent = _download_raw_recent(list(data.keys()))
    target = pd.Timestamp(nse_date)
    updated = 0
    factor_count = 0
    for symbol, frame in data.items():
        nse_close = closes.get(symbol)
        if nse_close is None or frame is None or frame.empty:
            continue
        raw = raw_recent.get(symbol)
        adjusted_factor = None
        if raw is not None and not raw.empty:
            common = frame.index.intersection(raw.index)
            common = common[common <= target]
            if len(common):
                ref_date = common[-1]
                adjusted_close = pd.to_numeric(frame.loc[ref_date, "Close"], errors="coerce")
                raw_close = pd.to_numeric(raw.loc[ref_date, "Close"], errors="coerce")
                if pd.notna(adjusted_close) and pd.notna(raw_close) and float(raw_close) > 0:
                    adjusted_factor = float(adjusted_close) / float(raw_close)
                    factor_count += 1
        scaled_close = float(nse_close) * adjusted_factor if adjusted_factor is not None else float(nse_close)
        x = frame.copy()
        if target in x.index:
            x.loc[target, "Close"] = scaled_close
        else:
            row = {column: float("nan") for column in x.columns}
            row["Close"] = scaled_close
            x = pd.concat([x, pd.DataFrame([row], index=[target])])
        x.index = pd.to_datetime(x.index, errors="coerce").tz_localize(None)
        x = x[~x.index.isna()].sort_index()
        x = x[~x.index.duplicated(keep="last")]
        data[symbol] = x
        updated += 1
    snapshot["data"] = data
    snapshot["nse_data_date"] = nse_date
    snapshot["nse_close_symbols"] = updated
    snapshot["nse_adjustment_factors"] = factor_count
    snapshot["nse_source"] = "NSE official CM bhavcopy"
    if progress_callback:
        progress_callback(1, 1, f"NSE latest close applied · {updated:,} symbols")
    return snapshot


def install_nse_latest_close(engine_module) -> None:
    """Patch the scanner download boundary without changing its RS/technical logic."""
    if getattr(engine_module, "_nse_latest_close_installed", False):
        return

    original_download_universe = engine_module._download_universe
    original_download_batch = engine_module._download_batch

    def wrapped_download_universe(*args, **kwargs):
        def guarded_download_batch(symbols, retries=3, threads=True, period="2y"):
            if period != "2y":
                return {}
            return original_download_batch(symbols, retries=retries, threads=threads, period=period)

        engine_module._download_batch = guarded_download_batch
        try:
            snapshot = original_download_universe(*args, **kwargs)
        finally:
            engine_module._download_batch = original_download_batch
        return patch_snapshot(snapshot, kwargs.get("progress_callback"))

    engine_module._download_universe = wrapped_download_universe
    engine_module._nse_latest_close_installed = True
