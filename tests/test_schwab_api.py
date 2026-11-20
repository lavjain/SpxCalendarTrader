import json
from pathlib import Path

import pytest

from app.core import config, schwab_api
from app.core.models import ExpiryPair

CHAIN = json.loads((Path(__file__).parent / "fixtures" / "chain_sample.json").read_text())
# today is 2026-11-24 in the fixture
PAIR_A = ExpiryPair(short="2026-12-24", long="2026-12-31", short_dte=30, long_dte=37, width=7)
PAIR_THIRD = ExpiryPair(short="2026-12-18", long="2026-12-24", short_dte=24, long_dte=30, width=6)


def puts(pairs, **kw):
    return schwab_api.parse(CHAIN, pairs, **kw)


def test_same_strike_on_both_legs():
    rows = puts([PAIR_A])
    shorts = {q.strike for q in rows if q.expiry == PAIR_A.short}
    longs = {q.strike for q in rows if q.expiry == PAIR_A.long}
    assert shorts and shorts == longs
    for k in shorts:
        s, l = schwab_api.calendar_legs(rows, PAIR_A.short, PAIR_A.long, k)
        assert s.strike == l.strike == k and s.right == l.right == "P"


def test_calendar_legs_missing_leg_returns_none():
    rows = puts([PAIR_A])
    assert schwab_api.calendar_legs(rows, PAIR_A.short, PAIR_A.long, 1234.0) is None


def test_short_strikes_in_delta_band_and_on_spacing():
    lo, hi = config.DELTA_BAND
    for sets in (("10",), ("25",), ("10", "25")):
        rows = puts([PAIR_A], strike_sets=sets)
        shorts = [q for q in rows if q.expiry == PAIR_A.short]
        assert shorts
        for q in shorts:
            assert lo <= abs(q.delta) <= hi
            assert any(q.strike % int(s) == 0 for s in sets)
    only25 = {q.strike for q in puts([PAIR_A], strike_sets=("25",))}
    assert all(k % 25 == 0 for k in only25)


def test_long_leg_keeps_any_delta():
    wide = ExpiryPair(short="2026-12-18", long="2026-12-31", short_dte=24, long_dte=37, width=13)
    rows = puts([wide], delta_band=(0.35, 0.37))
    long_deltas = [abs(q.delta) for q in rows if q.expiry == wide.long]
    assert long_deltas and any(not 0.35 <= d <= 0.37 for d in long_deltas)


def test_no_spx_am_rows_on_third_friday():
    raw = [c for strikes in CHAIN["putExpDateMap"]["2026-12-18:24"].values() for c in strikes]
    assert {c["optionRoot"] for c in raw} == {"SPX", "SPXW"}    # the fixture has both
    rows = puts([PAIR_THIRD])
    third = [q for q in rows if q.expiry == "2026-12-18"]
    assert third
    spxw = {c["strikePrice"]: c["mark"] for strikes in CHAIN["putExpDateMap"]["2026-12-18:24"].values()
            for c in strikes if c["optionRoot"] == "SPXW"}
    assert len(third) == len({q.strike for q in third})          # one row per strike
    assert all(q.mark == spxw[q.strike] for q in third)         # the SPXW price, not the SPX twin


def test_root_fallback_to_symbol_when_field_missing():
    assert schwab_api._is_spxw({"symbol": "SPXW  261224P06700000"})
    assert not schwab_api._is_spxw({"symbol": "SPX   261218P06700000"})


def test_nothing_past_63_dte():
    far = ExpiryPair(short="2027-03-12", long="2027-03-19", short_dte=108, long_dte=115, width=7)
    assert puts([far]) == []
    with pytest.raises(ValueError):
        schwab_api.get_chain("$SPX", [far], today=__import__("datetime").date(2026, 11, 24))


def test_missing_values_become_none_and_rows_are_skipped():
    rows = puts([PAIR_A], strike_sets=("10",))
    assert all(None not in (q.mark, q.delta, q.iv) for q in rows)    # the "NaN" delta row is gone
    assert schwab_api._num("NaN") is None and schwab_api._num(-999) is None
    assert schwab_api._num(None) is None and schwab_api._num("1.5") == 1.5
    # a missing bid stays None, it is not turned into 0
    q = schwab_api._quote("2026-12-31", {"strikePrice": 6600.0, "bid": None, "ask": 5.0,
                                         "mark": 4.9, "delta": -0.2, "volatility": 15.0}, "P")
    assert q.bid is None and q.ask == 5.0


def test_call_nearest_the_money_on_each_expiry():
    calls = schwab_api.parse_calls(CHAIN, [PAIR_A, PAIR_THIRD])
    spot = CHAIN["underlyingPrice"]
    for exp in (PAIR_A.short, PAIR_A.long, PAIR_THIRD.short):
        near = min((q for q in calls if q.expiry == exp), key=lambda q: abs(q.strike - spot))
        assert near.right == "C" and abs(near.strike - spot) <= 5
    third = [q for q in calls if q.expiry == "2026-12-18"]
    assert len({q.strike for q in third}) == len(third)           # SPX twins dropped


def test_get_chain_requests_only_the_window(monkeypatch):
    seen = []
    monkeypatch.setattr(schwab_api, "_get_json", lambda url: seen.append(url) or {})
    schwab_api.get_chain("$SPX", [PAIR_A], today=__import__("datetime").date(2026, 11, 24))
    schwab_api.get_call_chain("$SPX", [PAIR_A])
    assert "fromDate=2026-12-24" in seen[0] and "toDate=2026-12-31" in seen[0]
    assert "contractType=PUT" in seen[0]
    assert "contractType=CALL" in seen[1] and f"strikeCount={config.CALL_STRIKE_COUNT}" in seen[1]
