from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta

import pandas as pd
import requests

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
    """Return the newest available NSE cash-market EQ bhavcopy close map."""
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


def patch_snapshot(snapshot: dict, progress_callback=None) -> dict:
    """Replace/append each Yahoo history's latest bar with the official NSE close."""
    data = snapshot.get("data", {})
    if not data:
        return snapshot
    if progress_callback:
        progress_callback(0, 1, "Loading latest NSE bhavcopy")
    nse_date, closes = fetch_latest_nse_close()
    target = pd.Timestamp(nse_date)
    updated = 0
    for symbol, frame in data.items():
        if symbol not in closes or frame is None or frame.empty:
            continue
        x = frame.copy()
        if target in x.index:
            x.loc[target, "Close"] = closes[symbol]
        else:
            row = {column: float("nan") for column in x.columns}
            row["Close"] = closes[symbol]
            x = pd.concat([x, pd.DataFrame([row], index=[target])])
        x.index = pd.to_datetime(x.index, errors="coerce").tz_localize(None)
        x = x[~x.index.isna()].sort_index()
        x = x[~x.index.duplicated(keep="last")]
        data[symbol] = x
        updated += 1
    snapshot["data"] = data
    snapshot["nse_data_date"] = nse_date
    snapshot["nse_close_symbols"] = updated
    snapshot["nse_source"] = "NSE UDiFF CM Bhavcopy"
    if progress_callback:
        progress_callback(1, 1, f"NSE latest close applied · {updated:,} symbols")
    return snapshot
