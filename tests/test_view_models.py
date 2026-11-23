from datetime import date

import pytest

from app.core import schwab_api, services
from app.snapshots import SnapshotStore
from app import view_models as vm
from tests.test_services import CHAIN


@pytest.fixture
def snap(monkeypatch):
    monkeypatch.setattr(services, "market_today", lambda: date(2026, 11, 24))
    monkeypatch.setattr(schwab_api, "get_chain", lambda sym, pairs, **kw: CHAIN)
    monkeypatch.setattr(schwab_api, "get_call_chain", lambda sym, pairs, **kw: CHAIN)
    # three pairs so sorting and segments mean something
    res = services.get_finder(dte_range=(7, 56), widths=(7,))
    return SnapshotStore().put(res)


def test_parse_sort():
    assert vm.parse_sort(None) == ("date", False)
    assert vm.parse_sort("skew") == ("skew", True)
    assert vm.parse_sort("-price") == ("price", True) and vm.parse_sort("+skew") == ("skew", False)
    assert vm.parse_sort("nonsense") == ("date", False)


def test_segments_by_width_narrowest_first(snap):
    p = next(p for p in snap.result.pairs if p.rows)
    other = p.model_copy(update={"width": 4, "short_expiry": "2026-12-10", "long_expiry": "2026-12-14"})
    snap.result.pairs.append(other)
    segs = vm.segments(snap)
    assert [s["width"] for s in segs] == [4, 7]


def test_sorting_puts_missing_values_last(snap):
    p = next(p for p in snap.result.pairs if p.rows)
    empty = p.model_copy(update={"short_expiry": "2027-01-01", "long_expiry": "2027-01-08", "near_40_delta": None,
                                 "best_skew": None, "rows": [], "strike_count": 0})
    snap.result.pairs.append(empty)
    pairs = vm.segments(snap, "skew")[0]["pairs"]
    assert pairs[-1].near_40_delta is None


def test_default_pair_is_default_width_nearest_30_dte(snap):
    d = vm.default_pair(snap)
    assert d and d.width == 7
    assert abs(d.short_dte - 30) == min(abs(p.short_dte - 30) for p in snap.result.pairs if p.near_40_delta)


def test_results_context_opens_default_pair_with_40_delta_row(snap):
    c = vm.results_context(snap)
    assert c["open_key"] == vm.pair_key(c["open_pair"])
    assert c["row"].is_near_40_delta and c["selected_strike"] == c["row"].strike
    assert c["best_key"] == vm.best_skew_key(snap)


def test_results_context_honours_an_explicit_selection(snap):
    pair = next(p for p in snap.result.pairs if p.rows)
    other = next(r for r in pair.rows if not r.is_near_40_delta)
    c = vm.results_context(snap, open_key=vm.pair_key(pair), strike=other.strike)
    assert c["row"].strike == other.strike and not c["row"].is_near_40_delta


def test_panel_context_cost_includes_the_fill_offset(snap):
    pair = next(p for p in snap.result.pairs if p.rows)
    r = pair.near_40_delta
    c = vm.panel_context(snap, pair.short_expiry, pair.long_expiry, r.strike)
    assert c["cost"] == pytest.approx(r.contracts * (r.price + 0.10) * 100)
    assert vm.panel_context(snap, "x", "y", 1.0)["row"] is None


def test_status_strip_lists_unique_short_expiries(snap):
    s = vm.status_strip(snap)
    assert len({x["expiry"] for x in s["shorts"]}) == len(s["shorts"]) >= 1
    assert s["spx"] == 6800.0
