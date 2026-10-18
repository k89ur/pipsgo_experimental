from __future__ import annotations

import numpy as np
import pandas as pd

from vcp_engine import analyze_vcp


def make_frame() -> pd.DataFrame:
    n = 300
    close = pd.Series(100.0 + np.arange(n) * 0.2)
    frame = pd.DataFrame(
        {
            "Open": close - 0.1,
            "Close": close,
            "High": close + 0.5,
            "Low": close - 0.5,
            "Volume": 1000,
        },
        index=pd.bdate_range("2025-01-01", periods=n),
    )
    return frame


def base_kwargs() -> dict:
    return {
        "trend_filter": False,
        "use_52w_high": False,
        "use_52w_low": False,
        "dma_position_filter": False,
        "sma44_position_filter": False,
        "low_44sma_filter": False,
        "bullish_candle_filter": False,
        "close_above_44_50_sma_filter": False,
    }


def test_bullish_candle_filter_can_be_enabled_or_disabled():
    frame = make_frame()
    frame.iloc[-1, frame.columns.get_loc("Open")] = frame.Close.iloc[-1] + 1

    enabled = analyze_vcp("TEST", frame, **(base_kwargs() | {"bullish_candle_filter": True}))
    disabled = analyze_vcp("TEST", frame, **base_kwargs())

    assert enabled["Bullish Candle OK"] is False
    assert enabled["Bullish Candle Filter OK"] is False
    assert enabled["VCP"] is False
    assert disabled["Bullish Candle Filter OK"] is True
    assert disabled["VCP"] is True


def test_close_above_both_44_and_50_sma_filter_can_be_enabled_or_disabled():
    frame = make_frame()
    # Make the latest close fall below both moving averages.
    frame.iloc[-1, frame.columns.get_loc("Close")] = frame.Close.iloc[-2] - 10
    frame.iloc[-1, frame.columns.get_loc("Open")] = frame.Close.iloc[-1] - 0.1

    enabled = analyze_vcp(
        "TEST", frame, **(base_kwargs() | {"close_above_44_50_sma_filter": True})
    )
    disabled = analyze_vcp("TEST", frame, **base_kwargs())

    assert enabled["Close Above 44&50 SMA OK"] is False
    assert enabled["Close Above 44&50 SMA Filter OK"] is False
    assert enabled["VCP"] is False
    assert disabled["Close Above 44&50 SMA Filter OK"] is True
    assert disabled["VCP"] is True


def test_both_new_filters_pass_for_bullish_close_above_both_mas():
    result = analyze_vcp(
        "TEST",
        make_frame(),
        **(base_kwargs() | {
            "bullish_candle_filter": True,
            "close_above_44_50_sma_filter": True,
        }),
    )

    assert result["Bullish Candle OK"] is True
    assert result["Close Above 44&50 SMA OK"] is True
    assert result["Bullish Candle Filter OK"] is True
    assert result["Close Above 44&50 SMA Filter OK"] is True
    assert result["VCP"] is True
