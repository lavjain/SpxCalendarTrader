import json
from datetime import date
from pathlib import Path

import pytest

from app.core import config, schwab_api, services
from app.core.models import FinderResult

CHAIN = json.loads((Path(__file__).parent / "fixtures" / "chain_sample.json").read_text())


@pytest.fixture
def mocked(monkeypatch):
    monkeypatch.setattr(services, "market_today", lambda: date(2026, 11, 24))
    monkeypatch.setattr(schwab_api, "get_chain", lambda sym, pairs, **kw: CHAIN)
    monkeypatch.setattr(schwab_api, "get_call_chain", lambda sym, pairs, **kw: CHAIN)


def flat(result):
    return [r for p in result.pairs for r in p.rows]


def test_exactly_one_best_skew_and_one_near_40_delta(mocked):
    res = services.get_finder()
    assert isinstance(res, FinderResult)
    assert len(res.pairs) == 1
    p = res.pairs[0]
    assert (p.short_expiry, p.long_expiry, p.width) == ("2026-12-24", "2026-12-31", 7)
    assert sum(r.is_best_skew for r in flat(res)) == 1
    assert sum(r.is_near_40_delta for r in flat(res)) == 1
    assert p.strike_count == len(p.rows) > 1


def test_summary_matches_its_rows(mocked):
    p = services.get_finder().pairs[0]
    near = next(r for r in p.rows if r.is_near_40_delta)
    best = next(r for r in p.rows if r.is_best_skew)
    assert p.near_40_delta == near
    assert (p.best_skew, p.best_skew_strike) == (best.skew, best.strike)
    assert best.skew == max(r.skew for r in p.rows)
    assert abs(abs(near.short.delta) - 0.40) == min(abs(abs(r.short.delta) - 0.40) for r in p.rows)
    assert all(r.short.strike == r.long.strike == r.strike for r in p.rows)


def test_margin_sizing_matches_ceil_rule(mocked):
    for r in flat(services.get_finder(size_value=10_000)):
        assert r.contracts == -(-10_000 // (r.price * 100)) or r.contracts * r.price * 100 >= 10_000
        assert r.margin == pytest.approx(r.price * 100 * r.contracts)
        assert r.contracts == int(r.contracts)


def test_fixed_contract_sizing(mocked):
    rows = flat(services.get_finder(size_mode="contracts", size_value=3))
    assert rows and all(r.contracts == 3 for r in rows)
    assert all(r.margin == pytest.approx(r.price * 300) for r in rows)


def test_break_evens_on_the_near_40_row(mocked):
    p = services.get_finder().pairs[0]
    be = p.break_evens
    assert be and be.lower < p.near_40_delta.strike < be.upper and be.at_date == p.short_expiry


def test_result_is_plain_json(mocked):
    res = services.get_finder()
    assert FinderResult.model_validate_json(res.model_dump_json()) == res


def test_strike_sets_filter(mocked):
    only25 = flat(services.get_finder(strike_sets=("25",)))
    assert only25 and all(r.strike % 25 == 0 for r in only25)


def test_bad_inputs(mocked):
    with pytest.raises(ValueError):
        services.get_finder(size_mode="shares")
    with pytest.raises(ValueError):
        services.get_finder(size_mode="contracts", size_value=2.5)
    with pytest.raises(ValueError):
        services.get_finder(size_value=0)


def test_no_pairs_returns_empty_result(monkeypatch):
    monkeypatch.setattr(services, "market_today", lambda: date(2026, 11, 24))
    monkeypatch.setattr(services, "pick_expiries", lambda *a, **k: [])
    assert services.get_finder().pairs == []


@pytest.mark.parametrize("name,args", [
    ("get_holdings", ()), ("get_performance", ()), ("get_risk_profile", ()), ("get_spx_history", ()),
    ("quote_spread", (None, None)), ("parse_tos_order", ("",)), ("open_trade", (None, "margin", 1, 1)),
    ("close_trade", (1, 1.0))])
def test_the_other_eight_signatures_exist_and_raise(name, args):
    with pytest.raises(NotImplementedError):
        getattr(services, name)(*args)


def test_cli_table_prints_flags_and_break_evens(mocked, capsys):
    import cli
    print(cli.format_finder(services.get_finder()))
    out = capsys.readouterr().out
    assert "*40D" in out and "BEST-SKEW" in out and "break-evens" in out and "2026-12-24 -> 2026-12-31" in out


def test_diagnose_reports_inputs_and_variants(mocked):
    import cli
    d = services.diagnose_finder(tos=(6600.0, 6850.0))
    assert d["spx"] == 6800.0 and d["carry_per_year"] == pytest.approx(0.0, abs=0.01)
    assert {l["leg"] for l in d["legs"]} == {"short", "long"}
    for l in d["legs"]:   # the fixture was priced with these IVs, so the model reproduces the mids
        assert l["model_at_schwab_iv"] == pytest.approx(l["mid"], abs=0.1)
        assert l["implied_iv_from_mid"] == pytest.approx(l["schwab_iv"], abs=0.2)
    assert d["variants"]["as the app computes it"][0] < d["strike"] < d["variants"]["as the app computes it"][1]
    text = cli.format_diagnosis(d)
    assert "implied carry" in text and "vs tos" in text
