import io
import requests
import pandas as pd

FNO_CSV_URL = "https://drive.google.com/uc?export=download&id=1urIdJJ8L3DJGuuNvt49azQ62O0pDKj9e"


def load_fno_symbols(timeout=15):
    """Fetch the external F&O CSV and return a normalized symbol set."""
    response = requests.get(FNO_CSV_URL, timeout=timeout)
    response.raise_for_status()
    data = pd.read_csv(io.BytesIO(response.content))
    if "SYMBOL" not in data.columns:
        raise ValueError("F&O CSV must contain a SYMBOL column.")
    symbols = data["SYMBOL"].astype(str).str.strip().str.upper()
    symbols = symbols[symbols.ne("") & symbols.ne("NAN")]
    return set(symbols.tolist())


def filter_fno_results(df, timeout=15):
    """Return rows from an existing scan result that are present in the F&O list."""
    if df is None:
        return pd.DataFrame()
    if df.empty:
        return df.copy()
    symbols = load_fno_symbols(timeout=timeout)
    normalized = df["Symbol"].astype(str).str.strip().str.upper()
    return df.loc[normalized.isin(symbols)].copy()
