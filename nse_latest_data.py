from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

NSE_BHAVCOPY_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date}_F_0000.csv.zip"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/zip,application/octet-stream,*/*",
}


def _read_bhavcopy(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        csv_files = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not csv_files:
            raise ValueError("NSE bhavcopy ZIP contains no CSV")
        with archive.open(csv_files[0]) as handle:
            df = pd.read_csv(handle)
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    required = {"TckrSymb", "SctySrs", "ClsPric", "TradDt"}
    if not required.issubset(df.columns):
        raise ValueError(f"NSE bhavcopy missing columns: {sorted(required - set(df.columns))}")
    return df


def fetch_latest_nse_close(max_lookback_days: int = 7) -> tuple[str, dict[str, float]]:
    """Return the newest available NSE cash-market EQ close map."""
    today = datetime.now().date()
    last_error = None
    for offset in range(max_lookback_days + 1):
        day = today - timedelta(days=offset)
        date_str = day.strftime("%Y%m%d")
        try:
            response = requests.get(NSE_BHAVCOPY_URL.format(date=date_str), headers=HEADERS, timeout=20)
            response.raise_for_status()
            df = _read_bhavcopy(response.content)
            df["SctySrs"] = df["SctySrs"].astype(str).str.strip().str.upper()
            df = df[df["SctySrs"].eq("EQ")].copy()
            df["TckrSymb"] = df["TckrSymb"].astype(str).str.strip().str.upper()
            df["ClsPric"] = pd.to_numeric(df["ClsPric"], errors="coerce")
            df = df.dropna(subset=["TckrSymb", "ClsPric"])
            df = df[df["ClsPric"] > 0].drop_duplicates("TckrSymb", keep="last")
            if not df.empty:
                actual_date = pd.to_datetime(df["TradDt"].iloc[0], errors="coerce")
                if pd.notna(actual_date):
                    return actual_date.date().isoformat(), dict(zip(df["TckrSymb"], df["ClsPric"].astype(float)))
        except Exception as exc:
            last_error = exc
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
    """Overlay the official NSE close while preserving Yahoo adjusted-price scale."""
    data = snapshot.get("data", {})
    if not data:
        return snapshot
    if progress_callback:
        progress_callback(0, 1, "Loading latest NSE bhavcopy")
    nse_date, closes = fetch_latest_nse_close()
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
    snapshot["nse_source"] = "NSE UDiFF CM Bhavcopy"
    if progress_callback:
        progress_callback(1, 1, f"NSE latest close applied · {updated:,} symbols")
    return snapshot


def install_nse_latest_close(engine_module) -> None:
    """Patch the scanner download boundary without changing its RS/technical logic."""
    original_download_universe = engine_module._download_universe
    original_download_batch = engine_module._download_batch

    def wrapped_download_universe(*args, **kwargs):
        def guarded_download_batch(symbols, retries=3, threads=True, period="2y"):
            # Skip the old Yahoo-only stale recovery; NSE is now the authoritative
            # latest-close source. Normal 2-year downloads and missing-symbol recovery remain unchanged.
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
