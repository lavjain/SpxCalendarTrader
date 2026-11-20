import json

import pytest

from app.core import config
from app.core.models import (BreakEvens, CalendarRow, ExpiryPair, FinderResult,
                             OptionQuote, PairSummary)


def quote(expiry, strike=5000.0, iv=15.0):
    return OptionQuote(expiry=expiry, strike=strike, bid=10.0, ask=10.4, mark=10.2,
                       delta=-0.4, gamma=0.002, theta=-1.1, vega=4.5, iv=iv)


def row():
    return CalendarRow(strike=5000.0, width=7, short=quote("2026-12-24", iv=16.0),
                       long=quote("2026-12-31", iv=15.2), contracts=8, price=12.5,
                       margin=10_000.0, delta=-1.2, gamma=-0.01, theta=40.0, vega=300.0,
                       short_iv=16.0, long_iv=15.2, short_vega=4.0, long_vega=4.5,
                       skew=0.8, td=3.2, theta_margin=0.004,
                       is_best_skew=True, is_near_40_delta=True)


def all_models():
    r = row()
    summary = PairSummary(short_expiry="2026-12-24", long_expiry="2026-12-31", short_dte=30,
                          long_dte=37, width=7, near_40_delta=r, best_skew=0.8,
                          best_skew_strike=5000.0, strike_count=1, rows=[r],
                          break_evens=BreakEvens(lower=4900.5, upper=5100.25, at_date="2026-12-24"))
    return [
        quote("2026-12-24"),
        ExpiryPair(short="2026-12-24", long="2026-12-31", short_dte=30, long_dte=37, width=7),
        r,
        BreakEvens(lower=4900.5, upper=5100.25, at_date="2026-12-24"),
        summary,
        FinderResult(time="2026-11-24T10:00:00-05:00", spx=5000.0,
                     filters={"dte_range": [25, 35], "widths": [7]}, pairs=[summary]),
    ]


@pytest.mark.parametrize("m", all_models(), ids=lambda m: type(m).__name__)
def test_json_round_trip(m):
    assert type(m).model_validate_json(m.model_dump_json()) == m


def _numbers(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from _numbers(v)
    elif isinstance(o, list):
        for v in o:
            yield from _numbers(v)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        yield o


@pytest.mark.parametrize("m", all_models(), ids=lambda m: type(m).__name__)
def test_only_plain_python_numbers(m):
    # model_dump() keeps Python types; json.loads proves they're JSON-native, no numpy
    for n in _numbers(m.model_dump()):
        assert type(n) in (int, float)
    assert json.loads(m.model_dump_json()) is not None


def test_missing_quote_is_none_not_zero():
    q = OptionQuote(expiry="2026-12-24", strike=5000)
    assert q.bid is None and q.ask is None and q.mark is None


def test_config_consistency():
    assert config.MAX_DTE == config.SHORT_DTE_LIMITS[1] + 7
    assert config.DELTA_BAND[0] < config.DELTA_TARGET < config.DELTA_BAND[1]
    assert set(config.WIDTHS_DEFAULT) <= set(config.WIDTHS)
