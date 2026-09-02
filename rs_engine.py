from __future__ import annotations

import io
from functools import lru_cache
from typing import Callable, Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf

NSE_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
SECTOR_INDUSTRY_URL = "https://drive.google.com/uc?export=download&id=1Auelz4iprUIV578TPc_C5i_EEol43i9c"
STOCK_INDEX_URL = "https://drive.google.com/uc?export=download&id=19auf-ZldcujlMEiznNUMYTFBiokST2ro"


def get_nse_symbols() -> list[str]:
    """Get the current NSE equity universe. Falls back to bundled symbols.csv."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"}
    try:
        r = requests.get(NSE_URL, headers=headers, timeout=20)
        r.raise_for_status()
        df = pd.read_csv(io.BytesIO(r.content))
        col = next((c for c in ["SYMBOL", "Symbol", "symbol"] if c in df.columns), None)
        if not col:
            raise ValueError("NSE CSV has no SYMBOL column")
        symbols = df[col].astype(str).str.strip().replace("nan", np.nan).dropna().unique().tolist()
        symbols = [s for s in symbols if s and s not in {"SYMBOL"}]
        if len(symbols) >= 100:
            return sorted(symbols)
    except Exception:
        pass
    try:
        fallback = pd.read_csv("symbols.csv")
        col = "Symbol" if "Symbol" in fallback.columns else fallback.columns[0]
        return sorted(fallback[col].dropna().astype(str).str.strip().unique())
    except Exception as e:
        raise RuntimeError("Could not load NSE symbols. Keep an updated symbols.csv beside app.py.") from e


def _download_batch(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Download one batch from Yahoo Finance."""
    tickers = [f"{s}.NS" for s in symbols]
    raw = yf.download(
        tickers=tickers,
        period="2y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    result: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return result
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = set(raw.columns.get_level_values(0)); level1 = set(raw.columns.get_level_values(1))
        for s in symbols:
            t = f"{s}.NS"
            try:
                if t in level0:
                    x = raw[t].copy()
                elif t in level1:
                    x = raw.xs(t, axis=1, level=1).copy()
                else:
                    continue
                if "Close" in x.columns and not x["Close"].dropna().empty:
                    result[s] = x.dropna(subset=["Close"])
            except Exception:
                continue
    else:
        s = symbols[0]
        if "Close" in raw.columns:
            result[s] = raw.dropna(subset=["Close"])
    return result


def _return_at_days(close: pd.Series, days: int) -> float:
    if len(close) <= days:
        return np.nan
    now = float(close.iloc[-1]); old = float(close.iloc[-days - 1])
    return (now / old - 1.0) * 100.0 if old else np.nan


def _metrics(symbol: str, x: pd.DataFrame, rising_days: int) -> dict:
    close = x["Close"].dropna().astype(float)
    if len(close) < 200:
        return {}
    ltp = float(close.iloc[-1])
    d50 = close.rolling(50).mean(); d150 = close.rolling(150).mean(); d200 = close.rolling(200).mean()
    if len(d200.dropna()) <= rising_days:
        return {}
    high_52w = float(close.tail(252).max())
    from_high = (high_52w - ltp) / high_52w * 100.0 if high_52w else np.nan
    return {
        "Symbol": symbol, "LTP": ltp,
        "3M %": _return_at_days(close, 63), "6M %": _return_at_days(close, 126),
        "9M %": _return_at_days(close, 189), "12M %": _return_at_days(close, 252),
        "50 DMA": float(d50.iloc[-1]), "150 DMA": float(d150.iloc[-1]), "200 DMA": float(d200.iloc[-1]),
        "50 DMA Rising": float(d50.iloc[-1]) > float(d50.iloc[-1-rising_days]),
        "150 DMA Rising": float(d150.iloc[-1]) > float(d150.iloc[-1-rising_days]),
        "200 DMA Rising": float(d200.iloc[-1]) > float(d200.iloc[-1-rising_days]),
        "52W High": high_52w, "From 52W High %": from_high, "History Days": len(close),
    }


def _percentile_rating(scores: pd.Series) -> pd.Series:
    pct = scores.rank(method="average", pct=True) * 99
    return pct.round().clip(1, 99).astype(int)


@lru_cache(maxsize=1)
def _load_sector_industry() -> dict[str, tuple[str, str]]:
    """Load the external Symbol -> (Sector, Industry) metadata database once per process."""
    try:
        r = requests.get(
            SECTOR_INDUSTRY_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"},
            timeout=30,
        )
        r.raise_for_status()
        metadata = pd.read_csv(io.BytesIO(r.content))
        required = {"Symbol", "Sector", "Industry"}
        if not required.issubset(metadata.columns):
            raise ValueError("Sector/industry CSV is missing required columns")

        metadata = metadata[["Symbol", "Sector", "Industry"]].copy()
        metadata["Symbol"] = metadata["Symbol"].astype(str).str.strip().str.upper()
        for col in ["Sector", "Industry"]:
            metadata[col] = metadata[col].fillna("").astype(str).str.strip()
            metadata[col] = metadata[col].replace("", "Not Available")
        metadata = metadata[
            ~metadata["Symbol"].isin(["", "NAN", "NONE"])
        ].drop_duplicates("Symbol")

        return {
            row.Symbol: (row.Sector, row.Industry)
            for row in metadata.itertuples(index=False)
        }
    except Exception:
        # Metadata is optional. A failed metadata request must never stop the stock scan.
        return {}


def _sector_industry_results(symbols: list[str]) -> dict[str, tuple[str, str]]:
    """Resolve Sector and Industry locally; unknown symbols remain Not Available."""
    metadata = _load_sector_industry()
    return {
        symbol: metadata.get(symbol, ("Not Available", "Not Available"))
        for symbol in symbols
    }


def _load_stock_indices() -> dict[str, tuple[str, str, str, str, str]]:
    """Load external stock -> index 1-5 memberships from the public Drive CSV."""
    urls = [
        STOCK_INDEX_URL,
        "https://drive.google.com/uc?export=download&confirm=t&id=19auf-ZldcujlMEiznNUMYTFBiokST2ro",
        "https://drive.usercontent.google.com/download?id=19auf-ZldcujlMEiznNUMYTFBiokST2ro&export=download&confirm=t",
    ]
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,application/octet-stream,*/*"}

    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            r.raise_for_status()
            content = r.content
            if not content:
                continue
            metadata = pd.read_csv(io.BytesIO(content))

            normalized = {str(c).replace("\ufeff", "").strip().upper(): c for c in metadata.columns}
            symbol_col = normalized.get("SYMBOL")
            index_cols = [normalized.get(f"INDEX {i}") for i in range(1, 6)]
            if not symbol_col or any(c is None for c in index_cols):
                continue

            metadata = metadata[[symbol_col, *index_cols]].copy()
            metadata.columns = ["Symbol", "Index 1", "Index 2", "Index 3", "Index 4", "Index 5"]
            metadata["Symbol"] = metadata["Symbol"].astype(str).str.replace("\ufeff", "", regex=False).str.strip().str.upper()
            metadata = metadata[~metadata["Symbol"].isin(["", "NAN", "NONE"])].drop_duplicates("Symbol")

            for col in ["Index 1", "Index 2", "Index 3", "Index 4", "Index 5"]:
                metadata[col] = metadata[col].fillna("").astype(str).str.strip()
                metadata[col] = metadata[col].replace("", "Not Available")

            return {
                row[0]: (row[1], row[2], row[3], row[4], row[5])
                for row in metadata.itertuples(index=False, name=None)
            }
        except Exception:
            continue

    return {}


def _stock_index_results(symbols: list[str]) -> dict[str, tuple[str, str, str, str, str]]:
    """Resolve five index membership fields; unknown symbols remain Not Available."""
    metadata = _load_stock_indices()
    missing = ("Not Available",) * 5
    return {symbol: metadata.get(symbol, missing) for symbol in symbols}


def run_scan(min_rs: int = 80, near_high_pct: float = 5, min_price: float = 100, rising_days: int = 20,
             use_minervini: bool = True, batch_size: int = 50,
             progress_callback: Optional[Callable[[int, int, str], None]] = None):
    """Run the stock scan with original calculations and filters."""
    symbols = get_nse_symbols(); total = len(symbols); rows = []; successful = 0
    batches = [symbols[start:start + batch_size] for start in range(0, total, batch_size)]

    # Use only yfinance's internal threading. Avoid an outer ThreadPoolExecutor
    # because Streamlit deployments can hit process/thread limits.
    completed = 0
    for batch in batches:
        try:
            data = _download_batch(batch)
        except Exception:
            data = {}
        successful += len(data)
        for symbol, x in data.items():
            try:
                m = _metrics(symbol, x, rising_days)
                if m:
                    rows.append(m)
            except Exception:
                continue
        completed += len(batch)
        if progress_callback:
            progress_callback(min(completed, total), total, "Downloading & calculating")

    if not rows:
        raise RuntimeError("No usable stock data was returned.")
    df = pd.DataFrame(rows)
    ret_cols = ["3M %", "6M %", "9M %", "12M %"]
    df = df.dropna(subset=ret_cols).copy()
    df["Raw RS Score"] = df["3M %"] * 0.40 + df["6M %"] * 0.20 + df["9M %"] * 0.20 + df["12M %"] * 0.20
    df["RS Rating"] = _percentile_rating(df["Raw RS Score"])
    df = df[(df["LTP"] >= min_price) & (df["History Days"] >= 252) & (df["RS Rating"] >= min_rs) & (df["From 52W High %"] <= near_high_pct)].copy()
    if use_minervini:
        df = df[(df["LTP"] > df["50 DMA"]) & (df["LTP"] > df["150 DMA"]) & (df["LTP"] > df["200 DMA"]) & df["50 DMA Rising"] & df["150 DMA Rising"] & df["200 DMA Rising"]].copy()
    df = df.sort_values(["RS Rating", "Raw RS Score"], ascending=False).reset_index(drop=True)

    # Metadata is informational only and is never used in scan calculations or filters.
    if not df.empty:
        industry_metadata = _sector_industry_results(df["Symbol"].astype(str).tolist())
        index_metadata = _stock_index_results(df["Symbol"].astype(str).tolist())
        df["Industry"] = [industry_metadata.get(s, ("Not Available", "Not Available"))[1] for s in df["Symbol"].astype(str)]
        index_values = [index_metadata.get(s, ("Not Available",) * 5) for s in df["Symbol"].astype(str)]
        for i, col in enumerate(["Index 1", "Index 2", "Index 3", "Index 4", "Index 5"]):
            df[col] = [values[i] for values in index_values]
        df["Index"] = df[["Index 1", "Index 2", "Index 3", "Index 4", "Index 5"]].apply(
            lambda row: " • ".join(value for value in row if value != "Not Available") or "Not Available",
            axis=1,
        )
        df = df.drop(columns=["Index 1", "Index 2", "Index 3", "Index 4", "Index 5"])
    else:
        df["Industry"] = pd.Series(dtype=str)
        df["Index"] = pd.Series(dtype=str)

    df["TradingView"] = "https://www.tradingview.com/chart/?symbol=NSE%3A" + df["Symbol"].astype(str)
    columns = ["Symbol", "Index", "Industry", "LTP", "RS Rating", "Raw RS Score", "3M %", "6M %", "9M %", "12M %",
               "50 DMA", "150 DMA", "200 DMA", "52W High", "From 52W High %", "History Days", "TradingView"]
    df = df[columns]
    stats = {"universe": total, "coverage": (successful / total * 100) if total else 0}
    return df, stats
