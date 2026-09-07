import io
import pandas as pd
import requests

FNO_CSV_URL = "https://drive.google.com/uc?export=download&id=1urIdJJ8L3DJGuuNvt49azQ62O0pDKj9e"


def load_fno_symbols(timeout=15):
    """Fetch the external F&O CSV and return a normalized symbol set."""
    response = requests.get(FNO_CSV_URL, timeout=timeout)
    response.raise_for_status()
    df = pd.read_csv(io.BytesIO(response.content))
    if "SYMBOL" not in df.columns:
        raise ValueError("F&O CSV must contain a SYMBOL column.")
    symbols = (
        df["SYMBOL"]
        .astype(str)
        .str.strip()
        .str.upper()
    )
    symbols = symbols[symbols.ne("") & symbols.ne("NAN")]
    return set(symbols.tolist())


def filter_fno_results(df, timeout=15):
    """Return only rows from an existing scan result that are in the F&O list."""
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    symbols = load_fno_symbols(timeout=timeout)
    result = df.copy()
    normalized = result["Symbol"].astype(str).str.strip().str.upper()
    return result.loc[normalized.isin(symbols)].copy()
