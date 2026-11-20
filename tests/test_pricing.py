import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from app.core import config, pricing, schwab_api
from app.core.models import CalendarRow, ExpiryPair, OptionQuote

CHAIN = json.loads((Path(__file__).parent / "fixtures" / "chain_sample.json").read_text())
AS_OF = date(2026, 11, 24)
SPOT = CHAIN["underlyingPrice"]
PAIR = ExpiryPair(short="2026-12-24", long="2026-12-31", short_dte=30, long_dte=37, width=7)


def parity_quotes():
    return schwab_api.parse_parity_quotes(CHAIN, CHAIN, [PAIR])


def sample_trade():
    """A ~40-delta calendar built from the fixture chain."""
    rows = schwab_api.parse(CHAIN, [PAIR], strike_sets=("25",))
    k = min((q for q in rows if q.expiry == PAIR.short), key=lambda q: abs(abs(q.delta) - 0.40)).strike
    s, l = schwab_api.calendar_legs(rows, PAIR.short, PAIR.long, k)
    price = pricing.calendar_value_now(s, l)
    return CalendarRow(strike=k, width=7, short=s, long=l, contracts=1, price=price, margin=price * 100,
                       delta=0, gamma=0, theta=0, vega=0, short_iv=s.iv, long_iv=l.iv,
                       short_vega=s.vega, long_vega=l.vega, skew=s.iv - l.iv, td=0, theta_margin=0)


def long_forward():
    return pricing.forward_from_parity(parity_quotes(), PAIR.long, AS_OF)


def test_black_scholes_put_call_parity():
    f, k, t, iv, r = 6800.0, 6700.0, 0.25, 0.16, 0.04
    c, p = pricing.bs_call(f, k, t, iv, r), pricing.bs_put(f, k, t, iv, r)
    assert float(c - p) == pytest.approx(math.exp(-r * t) * (f - k), abs=1e-9)


def test_bs_put_at_expiry_is_intrinsic():
    assert float(pricing.bs_put(6600.0, 6700.0, 0.0, 0.15)) == 100.0
    assert float(pricing.bs_put(6800.0, 6700.0, 0.0, 0.15)) == 0.0


def test_forward_from_parity_recovers_the_forward():
    # the fixture was generated with forward = 6800 for every expiry
    for exp in (PAIR.short, PAIR.long):
        assert pricing.forward_from_parity(parity_quotes(), exp, AS_OF) == pytest.approx(6800.0, abs=0.1)


def test_forward_needs_a_call_and_a_put():
    only_puts = [q for q in parity_quotes() if q.right == "P"]
    with pytest.raises(ValueError):
        pricing.forward_from_parity(only_puts, PAIR.short, AS_OF)


def test_mid_prefers_bid_ask_and_never_returns_zero_for_missing():
    q = OptionQuote(expiry="2026-12-24", strike=6700, bid=1.0, ask=2.0, mark=1.9)
    assert pricing.mid(q) == 1.5
    assert pricing.mid(OptionQuote(expiry="2026-12-24", strike=6700, mark=1.9)) == 1.9
    with pytest.raises(ValueError):
        pricing.mid(OptionQuote(expiry="2026-12-24", strike=6700))


def test_calendar_value_now_is_long_minus_short():
    t = sample_trade()
    assert t.price == pytest.approx(pricing.mid(t.long) - pricing.mid(t.short))
    assert t.price > 0


def test_pl_peaks_near_the_strike_and_is_negative_far_away():
    t = sample_trade()
    xs = np.linspace(0.85 * t.strike, 1.15 * t.strike, 601)
    pl = pricing.pl_curve(t, xs, SPOT, long_forward(), AS_OF)
    assert all(type(v) is float for v in pl)
    peak = xs[int(np.argmax(pl))]
    assert abs(peak - t.strike) / t.strike < 0.02
    assert max(pl) > 0
    assert pl[0] < 0 and pl[-1] < 0
    assert pl[-1] == pytest.approx(-(t.price + config.FILL_OFFSET), abs=0.5)   # long ~worthless far above


def test_break_evens_straddle_the_strike_and_are_zero_pl():
    t = sample_trade()
    be = pricing.break_evens(t, SPOT, long_forward(), AS_OF)
    assert be.lower < t.strike < be.upper
    assert be.at_date == PAIR.short
    for x in (be.lower, be.upper):
        assert pricing.pl_curve(t, [x], SPOT, long_forward(), AS_OF)[0] == pytest.approx(0.0, abs=1e-6)
    assert type(be.lower) is float and type(be.upper) is float


def test_entry_cost_is_in_the_pl():
    t = sample_trade()
    x = [t.strike]
    with_fill = pricing.pl_curve(t, x, SPOT, long_forward(), AS_OF)[0]
    without = pricing.pl_curve(t, x, SPOT, long_forward(), AS_OF, fill_offset=0.0)[0]
    assert without - with_fill == pytest.approx(config.FILL_OFFSET)


def test_earlier_date_is_wider_than_expiry_and_later_date_is_rejected():
    t = sample_trade()
    f = long_forward()
    at_expiry = pricing.break_evens(t, SPOT, f, AS_OF)
    midway = pricing.break_evens(t, SPOT, f, AS_OF, at_date=date(2026, 12, 10))
    assert (midway.upper - midway.lower) > (at_expiry.upper - at_expiry.lower)
    with pytest.raises(ValueError):
        pricing.pl_curve(t, [t.strike], SPOT, f, AS_OF, at_date=date(2026, 12, 28))


def test_losing_calendar_has_no_break_evens():
    t = sample_trade().model_copy(update={"price": 10_000.0})
    with pytest.raises(ValueError):
        pricing.break_evens(t, SPOT, long_forward(), AS_OF)


def test_core_has_no_web_imports():
    import subprocess
    out = subprocess.run(["grep", "-rn", "streamlit\\|fastapi\\|starlette\\|jinja2", "app/core"],
                         capture_output=True, text=True, cwd=Path(__file__).parents[1])
    assert out.stdout == ""
