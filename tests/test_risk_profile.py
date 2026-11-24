from datetime import date

import pytest

from app.core import schwab_api, services
from tests.test_services import CHAIN


@pytest.fixture
def calendar(monkeypatch):
    monkeypatch.setattr(services, "market_today", lambda: date(2026, 11, 24))
    monkeypatch.setattr(schwab_api, "get_chain", lambda s, p, **kw: CHAIN)
    monkeypatch.setattr(schwab_api, "get_call_chain", lambda s, p, **kw: CHAIN)
    res = services.get_finder(dte_range=(7, 56), widths=(7,))
    pair = next(p for p in res.pairs if p.near_target_delta)
    return pair.near_target_delta, res.spx


def test_the_grid_and_curves_are_plain_float_lists_of_one_length(calendar):
    row, spx = calendar
    rp = services.get_risk_profile(row, spx, half_range=150, points=61)
    assert len(rp.spx) == len(rp.today) == len(rp.at_expiry) == 61
    assert rp.spx[0] == pytest.approx(round(spx / 5) * 5 - 150) and rp.spx[-1] == pytest.approx(round(spx / 5) * 5 + 150)
    assert all(type(v) is float for v in rp.spx + rp.today + rp.at_expiry)


def test_pl_now_is_about_minus_the_fill_offset_and_cost_matches_the_row(calendar):
    row, spx = calendar
    rp = services.get_risk_profile(row, spx)
    assert rp.pl_now == pytest.approx(-0.10 * 100 * row.contracts, abs=0.02 * 100 * row.contracts)
    assert rp.cost == pytest.approx(row.contracts * (row.price + 0.10) * 100) and rp.max_loss == -rp.cost
    assert (rp.delta, rp.theta, rp.vega) == (row.delta, row.theta, row.vega)


def test_the_expiry_line_crosses_zero_at_the_break_evens(calendar):
    row, spx = calendar
    rp = services.get_risk_profile(row, spx, half_range=500, points=201)
    lo, hi = rp.break_evens.lower, rp.break_evens.upper
    below = [v for x, v in zip(rp.spx, rp.at_expiry) if x < lo - 5]
    inside = [v for x, v in zip(rp.spx, rp.at_expiry) if lo + 5 < x < hi - 5]
    assert below and all(v < 0 for v in below)
    assert inside and all(v > 0 for v in inside)
    assert rp.max_profit >= max(rp.at_expiry) - 1e-6


def test_the_one_sd_band_brackets_spot_and_a_calendar_without_a_forward_is_refused(calendar):
    row, spx = calendar
    rp = services.get_risk_profile(row, spx)
    assert rp.sd_low < spx < rp.sd_high
    with pytest.raises(ValueError, match="forward"):
        services.get_risk_profile(row.model_copy(update={"long_forward": None}), spx)
    with pytest.raises(ValueError, match="range"):
        services.get_risk_profile(row, spx, half_range=0)
