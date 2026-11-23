import pytest

from app.core.models import CalendarQuote, OptionQuote
from app.core.stability import calendar_quote, check_stability


def q(mid, spread=0.50, leg_pct=0.02):
    return CalendarQuote(bid=mid - spread / 2, ask=mid + spread / 2, mid=mid, spread=spread, leg_spread_pct=leg_pct)


def opt(bid, ask, expiry="2026-12-24"):
    return OptionQuote(expiry=expiry, strike=7140, bid=bid, ask=ask)


def test_calendar_quote_is_long_minus_short_on_the_opposite_sides():
    c = calendar_quote(opt(137.6, 139.3), opt(150.7, 151.8, "2026-12-31"))
    assert c.bid == pytest.approx(150.7 - 139.3) and c.ask == pytest.approx(151.8 - 137.6)
    assert c.mid == pytest.approx((c.bid + c.ask) / 2) and c.spread == pytest.approx(c.ask - c.bid)
    assert c.leg_spread_pct == pytest.approx(1.7 / 138.45, rel=1e-3)      # the wider leg is the short put


def test_a_missing_leg_quote_is_not_a_zero_price():
    c = calendar_quote(opt(None, 139.3), opt(150.7, 151.8))
    assert c.mid is None and c.bid is None and c.spread is None


def test_five_steady_quotes_are_stable():
    r = check_stability([q(12.80), q(12.85), q(12.80), q(12.82), q(12.84)])
    assert r.is_stable and r.waiting_reason is None and r.quotes_seen == 5
    assert (r.range_low, r.range_high) == (12.80, 12.85)


def test_four_quotes_wait():
    r = check_stability([q(12.8)] * 4)
    assert not r.is_stable and r.waiting_reason == "Waiting for 5 quotes (4 so far)"


def test_an_empty_history_waits():
    assert check_stability([]).waiting_reason == "Waiting for 5 quotes (0 so far)"


def test_a_range_over_ten_cents_waits_with_the_amount():
    r = check_stability([q(12.80), q(12.91), q(12.80), q(12.85), q(12.82)])
    assert not r.is_stable and r.waiting_reason == "Price moved $0.11 in the last 5 quotes (limit $0.10)"


def test_exactly_ten_cents_is_still_stable():
    assert check_stability([q(12.80), q(12.90), q(12.85), q(12.85), q(12.85)]).is_stable


def test_a_wide_leg_bid_ask_waits():
    r = check_stability([q(10.0, leg_pct=0.12)] * 5)
    assert not r.is_stable and r.waiting_reason == "A leg's bid-ask is 12% of its price (limit 10%)"


def test_the_calendars_own_wide_spread_does_not_block_a_steady_price():
    # the calendar's bid-ask is the sum of the legs' (22% of mid here); only each leg's own spread is tested
    assert check_stability([q(12.8, spread=2.8, leg_pct=0.012)] * 5).is_stable


def test_a_missing_quote_waits_and_breaks_the_run():
    r = check_stability([q(12.8)] * 5 + [CalendarQuote()])
    assert not r.is_stable and r.waiting_reason == "A leg has no bid or ask"
    r = check_stability([q(12.8)] * 5 + [CalendarQuote()] + [q(12.8)] * 2)
    assert not r.is_stable and r.quotes_seen == 2


def test_a_stable_history_then_a_jump_waits_again():
    history = [q(12.8)] * 5
    assert check_stability(history).is_stable
    r = check_stability(history + [q(13.4)])
    assert not r.is_stable and "Price moved" in r.waiting_reason


def test_symbol_round_trips_and_is_parsed_from_the_chain():
    from app.core import schwab_api
    from tests.test_services import CHAIN
    pairs_quotes = [x for _, x in schwab_api._contracts(CHAIN, "putExpDateMap", "P")]
    assert pairs_quotes and all(x.symbol and x.symbol.startswith("SPXW") for x in pairs_quotes)
    assert OptionQuote.model_validate_json(pairs_quotes[0].model_dump_json()).symbol == pairs_quotes[0].symbol
