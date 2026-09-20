"""Audit #12.15.2: compare Yahoo 10D stale recovery with an NSE-close-only candidate.

This is diagnostic only. It does not change production scanner behavior.

Run explicitly:
    RUN_EOD_RECOVERY_AUDIT=1 python -m pytest tests/test_eod_recovery_comparison.py -q -s
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
import requests

import rs_engine


NSE_BHAVCOPY_URLS = (
    "https://archives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv",
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv",
)
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/csv,application/octet-stream,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

RUN = os.getenv("RUN_EOD_RECOVERY_AUDIT") == "1"
MAX_STALE = int(os.getenv("EOD_RECOVERY_AUDIT_MAX_STALE", "0"))


def _latest(frame: pd.DataFrame) -> str | None:
    return rs_engine._latest_date(frame)


def _download_base_universe(symbols: list[str]) -> dict[str, pd.DataFrame]:
    data: dict[str, pd.DataFrame] = {}
    batch_size = rs_engine.DEFAULT_BATCH_SIZE
    total = len(symbols)

    for start in range(0, total, batch_size):
        group = symbols[start:start + batch_size]
        started = time.perf_counter()
        batch = rs_engine._download_batch(
            group, retries=2, threads=True, period="2y"
        )
        data.update(batch)
        print(
            f"BASE {min(start + len(group), total):4d}/{total} "
            f"received={len(batch):3d} elapsed={time.perf_counter() - started:.2f}s"
        )

    return data


def _fetch_latest_nse_close() -> tuple[str, dict[str, float]]:
    today = datetime.now(rs_engine.IST).date()
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    last_error = None

    for offset in range(0, 6):
        day = today - timedelta(days=offset)
        date_str = day.strftime("%d%m%Y")

        for template in NSE_BHAVCOPY_URLS:
            try:
                response = session.get(template.format(date=date_str), timeout=15)
                response.raise_for_status()

                if not response.content or response.content.lstrip().startswith(b"<"):
                    raise ValueError("NSE returned non-CSV content")

                df = pd.read_csv(pd.io.common.BytesIO(response.content))
                df.columns = [
                    str(c).replace("\ufeff", "").strip() for c in df.columns
                ]

                required = {"SYMBOL", "SERIES", "DATE1", "CLOSE_PRICE"}
                if not required.issubset(df.columns):
                    raise ValueError("NSE bhavcopy missing required columns")

                df["SERIES"] = df["SERIES"].astype(str).str.strip().str.upper()
                df = df[df["SERIES"].isin({"EQ", "BE"})].copy()
                df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip().str.upper()
                df["CLOSE_PRICE"] = pd.to_numeric(
                    df["CLOSE_PRICE"], errors="coerce"
                )
                df = df.dropna(subset=["SYMBOL", "CLOSE_PRICE"])
                df = df[df["CLOSE_PRICE"] > 0].drop_duplicates(
                    "SYMBOL", keep="last"
                )

                actual = pd.to_datetime(df["DATE1"].iloc[0], errors="coerce")
                if pd.isna(actual):
                    continue

                return actual.date().isoformat(), dict(
                    zip(df["SYMBOL"], df["CLOSE_PRICE"].astype(float))
                )
            except Exception as exc:
                last_error = exc

    raise RuntimeError(f"Unable to fetch recent NSE bhavcopy: {last_error}")


def _patch_with_nse_close(
    frame: pd.DataFrame,
    nse_date: str,
    nse_close: float,
) -> pd.DataFrame:
    x = frame.copy()
    target = pd.Timestamp(nse_date)

    factor = 1.0
    if "Adjustment Factor" in x.columns:
        factors = pd.to_numeric(x["Adjustment Factor"], errors="coerce")
        valid = factors[factors.notna() & factors.gt(0)]
        if not valid.empty:
            factor = float(valid.iloc[-1])

    scaled_close = float(nse_close) * factor

    if target in x.index:
        x.loc[target, "Close"] = scaled_close
    else:
        row = {column: float("nan") for column in x.columns}
        row["Close"] = scaled_close
        if "Adjustment Factor" in row:
            row["Adjustment Factor"] = factor
        x = pd.concat([x, pd.DataFrame([row], index=[target])])

    return rs_engine._clean_history(x)


def _metrics(symbol: str, frame: pd.DataFrame) -> dict:
    return rs_engine._metrics(
        symbol,
        frame,
        rising_days=20,
        calculate_ma_rising=True,
        snapshot_mode="eod",
    )


def _raw_rs(row: dict) -> float:
    return (
        float(row["3M %"]) * 0.40
        + float(row["6M %"]) * 0.20
        + float(row["9M %"]) * 0.20
        + float(row["12M %"]) * 0.20
    )


@pytest.mark.skipif(
    not RUN,
    reason="Set RUN_EOD_RECOVERY_AUDIT=1 to run this network-heavy diagnostic",
)
def test_eod_recovery_vs_nse_close_candidate() -> None:
    symbols = rs_engine.get_nse_symbols()
    base = _download_base_universe(symbols)

    dates = {
        symbol: _latest(frame)
        for symbol, frame in base.items()
        if _latest(frame)
    }
    target_date = max(dates.values()) if dates else None
    assert target_date, "No usable Yahoo history returned"

    stale = [
        symbol
        for symbol in symbols
        if symbol in base
        and dates.get(symbol)
        and dates[symbol] < target_date
    ]
    stale.sort()

    print("\n" + "=" * 78)
    print("EOD RECOVERY ARCHITECTURE AUDIT #12.15.2")
    print("=" * 78)
    print(f"Universe received : {len(base):,}")
    print(f"Target Yahoo date : {target_date}")
    print(f"Stale symbols     : {len(stale):,}")

    if MAX_STALE > 0:
        stale = stale[:MAX_STALE]
        print(f"Audit sample      : first {len(stale):,} stale symbols")

    nse_date, nse_closes = _fetch_latest_nse_close()

    # A clean CI Yahoo download can legitimately return one common latest
    # date for the whole universe. Production can still see mixed-date data
    # when persistent cached batches were created on different market days.
    # If the clean download has no stale symbols, switch to a controlled
    # lag simulation so the architecture comparison remains meaningful.
    simulated = False
    if not stale:
        simulated = True
        sample_size = MAX_STALE if MAX_STALE > 0 else 100
        sample = [s for s in symbols if s in base and s in nse_closes][:sample_size]
        if not sample:
            pytest.skip("Clean Yahoo run has no stale symbols and no comparable NSE sample")
        stale = sample
        print(f"Audit mode       : controlled lag simulation ({len(stale):,} symbols)")
    print(f"NSE latest date   : {nse_date}")
    print(f"NSE closes        : {len(nse_closes):,}")

    # CURRENT: same recovery semantics as production. For real stale data,
    # use Yahoo 10D recovery. For a clean CI download, simulate a lagged
    # cached batch by withholding the final daily rows from the base history.
    current: dict[str, pd.DataFrame] = {}
    candidate_base: dict[str, pd.DataFrame] = {}
    for symbol in stale:
        source = base[symbol]
        if simulated:
            lag = 1 if hash(symbol) % 3 else min(5, max(1, len(source) - 260))
            if len(source) <= lag + 260:
                lag = 1
            old = source.iloc[:-lag].copy()
            recent = source.iloc[-lag:].copy()
            candidate_base[symbol] = old
            current[symbol] = rs_engine._merge_history(old, recent)
        else:
            candidate_base[symbol] = source

    if not simulated:
        for start in range(0, len(stale), 50):
            group = stale[start:start + 50]
            recovered = rs_engine._download_batch(
                group, retries=2, threads=True, period="10d"
            )
            for symbol in group:
                recent = recovered.get(symbol)
                if recent is not None and not recent.empty:
                    current[symbol] = rs_engine._merge_history(
                        base[symbol], recent
                    )

    rows = []
    missing_current = []
    missing_nse = []

    for symbol in stale:
        old = candidate_base.get(symbol, base[symbol])
        cur = current.get(symbol)
        nse_close = nse_closes.get(symbol)

        if cur is None:
            missing_current.append(symbol)
            continue
        if nse_close is None:
            missing_nse.append(symbol)
            continue

        # CURRENT production path also receives the authoritative NSE EOD
        # close after Yahoo 10D recovery. Apply that patch here before comparing.
        current_with_nse = _patch_with_nse_close(cur, nse_date, nse_close)
        candidate = _patch_with_nse_close(old, nse_date, nse_close)
        cur_metrics = _metrics(symbol, current_with_nse)
        candidate_metrics = _metrics(symbol, candidate)

        if not cur_metrics or not candidate_metrics:
            continue

        cur_rs = _raw_rs(cur_metrics)
        candidate_rs = _raw_rs(candidate_metrics)

        rows.append(
            {
                "Symbol": symbol,
                "Base Date": _latest(old),
                "Current Date": _latest(current_with_nse),
                "Candidate Date": _latest(candidate),
                "Base Rows": len(old),
                "Current Rows": len(current_with_nse),
                "Candidate Rows": len(candidate),
                "Current RS": cur_rs,
                "Candidate RS": candidate_rs,
                "RS Diff": candidate_rs - cur_rs,
                "Current 12M": float(cur_metrics["12M %"]),
                "Candidate 12M": float(candidate_metrics["12M %"]),
            }
        )

    result = pd.DataFrame(rows)

    print(f"Current recovered : {len(current):,}/{len(stale):,}")
    print(f"Comparable rows   : {len(result):,}")
    print(f"NSE close missing : {len(missing_nse):,}")
    print(f"Recovery missing  : {len(missing_current):,}")

    assert not result.empty, "No comparable stale-symbol rows were produced"

    changed = result[
        ~np.isclose(
            result["Current RS"],
            result["Candidate RS"],
            rtol=1e-6,
            atol=1e-6,
        )
    ].copy()

    row_delta = result["Candidate Rows"] - result["Current Rows"]

    print(f"RS changes        : {len(changed):,}/{len(result):,}")
    print(f"Max |RS diff|     : {result['RS Diff'].abs().max():.12g}")
    print(f"Row-count deltas  : {sorted(row_delta.unique().tolist())}")

    if not changed.empty:
        print("\nTop RS differences:")
        print(
            changed.assign(abs_diff=changed["RS Diff"].abs())
            .sort_values("abs_diff", ascending=False)
            .head(20)
            .to_string(index=False)
        )

    print("=" * 78)

    # Diagnostic gate only: ensure both paths produced usable histories.
    # We intentionally do not assert numerical equivalence yet.
    assert result["Current Rows"].gt(0).all()
    assert result["Candidate Rows"].gt(0).all()
