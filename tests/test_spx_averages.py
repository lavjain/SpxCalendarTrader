from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core import schwab_api, services
from app.core.indicators import simple_moving_average

ET = ZoneInfo("America/New_York")


def test_simple_moving_average_is_the_mean_of_the_last_n_closes():
    closes = list(range(1, 61))                                # 1..60
    assert simple_moving_average(closes, 10) == pytest.approx(sum(range(51, 61)) / 10)
    assert simple_moving_average(closes, 50) == pytest.approx(sum(range(11, 61)) / 50)
    assert simple_moving_average(closes[:9], 10) is None and simple_moving_average(closes, 0) is None


def test_parse_daily_closes_uses_the_new_york_date_and_sorts():
    ms = lambda y, m, d, h: int(datetime(y, m, d, h, tzinfo=ET).timestamp() * 1000)
    data = {"candles": [{"datetime": ms(2026, 11, 24, 1), "close": 6850.5}, {"datetime": ms(2026, 11, 23, 1), "close": 6800.0},
                        {"datetime": None, "close": 1.0}, {"datetime": ms(2026, 11, 20, 1)}]}
    assert schwab_api.parse_daily_closes(data) == [("2026-11-23", 6800.0), ("2026-11-24", 6850.5)]
    assert schwab_api.parse_daily_closes({}) == []


@pytest.fixture
def bars(monkeypatch):
    closes = [(f"2026-{m:02d}-{d:02d}", 6000.0 + 10 * i) for i, (m, d) in enumerate(
        [(9 + (k + 1) // 30, (k % 28) + 1) for k in range(70)])]
    closes = sorted(set(closes))
    monkeypatch.setattr(schwab_api, "get_daily_closes", lambda symbol="$SPX", use_cache=True: closes)
    monkeypatch.setattr(schwab_api, "get_quotes", lambda syms, use_cache=True: {"$SPX": {"last": 7000.0, "mark": 7000.0}})
    monkeypatch.setitem(services._bars, "closes", [])
    return closes


def test_averages_compare_spx_with_each_window(bars):
    res = services.get_spx_averages()
    assert [r.days for r in res.rows] == [10, 20, 50] and res.missing == []
    for r in res.rows:
        assert r.pct_from == pytest.approx((7000.0 / r.value - 1) * 100) and r.side == ("above" if r.pct_from >= 0 else "below")
    assert res.rows[0].value > res.rows[1].value > res.rows[2].value          # rising closes: the short average is highest


def test_a_window_with_too_few_closes_is_reported_missing(monkeypatch):
    monkeypatch.setattr(schwab_api, "get_daily_closes", lambda symbol="$SPX", use_cache=True: [(f"2026-01-{d:02d}", 6000.0) for d in range(1, 16)])
    monkeypatch.setattr(schwab_api, "get_quotes", lambda syms, use_cache=True: {"$SPX": {"last": 6100.0}})
    monkeypatch.setitem(services._bars, "closes", [])
    res = services.get_spx_averages()
    assert [r.days for r in res.rows] == [10] and res.missing == [20, 50]
