from datetime import date

import pandas as pd
import pytest

import stock_rs_telegram


def test_weekends_skip_without_fetching_holidays():
    def unexpected_fetch(_year):
        raise AssertionError("weekends do not need a holiday lookup")

    assert not stock_rs_telegram.is_nse_trading_day(date(2026, 11, 7), unexpected_fetch)


def test_nse_holiday_is_not_a_trading_day():
    holidays = {date(2026, 11, 3)}
    assert not stock_rs_telegram.is_nse_trading_day(date(2026, 11, 3), lambda _year: holidays)


def test_stock_csv_matches_main_results_columns_and_numbering():
    data = pd.DataFrame(
        {
            "Symbol": ["AAA", "BBB"],
            "Index": ["NIFTY 50", "NIFTY 500"],
            "Raw RS Score": [12.0, 10.0],
            "RS Rating": [99, 95],
        }
    )

    assert stock_rs_telegram.stock_results_csv(data).decode("utf-8") == (
        "S.No,Symbol,Index,RS Rating\n1,AAA,NIFTY 50,99\n2,BBB,NIFTY 500,95\n"
    )


def test_unparseable_holiday_calendar_fails_closed(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"CM": [{"tradingDate": "not a date"}]}

    class Session:
        headers = {}

        def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(stock_rs_telegram.requests, "Session", Session)
    with pytest.raises(RuntimeError, match="could not be parsed"):
        stock_rs_telegram.fetch_nse_holidays(2026)