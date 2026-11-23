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


def test_margin_sizing_rounds_to_the_nearest_whole_contract(mocked):
    for r in flat(services.get_finder(size_value=10_000)):
        assert r.contracts == max(1, int(10_000 / (r.price * 100) + 0.5))
        assert abs(r.margin - 10_000) <= r.price * 50 + 1e-6 or r.contracts == 1   # within half a contract
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
    ("parse_tos_order", ("",)), ("close_trade", (1, 1.0))])
def test_the_later_week_signatures_exist_and_raise(name, args):
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
    app = d["variants"]["app (IVs implied from mids)"]
    assert app[0] < d["strike"] < app[1]
    assert "old: Schwab's IV field" in d["variants"]
    text = cli.format_diagnosis(d)
    assert "implied carry" in text and "vs tos" in text


def test_rows_carry_mid_implied_ivs_close_to_the_fixture_ivs(mocked):
    for r in flat(services.get_finder()):
        assert r.short_iv_implied == pytest.approx(r.short_iv, abs=0.3)
        assert r.long_iv_implied == pytest.approx(r.long_iv, abs=0.3)


# ------------------------------------------------------------- week 2, step 1 and 4 services
from types import SimpleNamespace


def test_td_is_none_when_position_delta_is_near_zero():
    assert services._td(SimpleNamespace(delta=0.0, td=float("nan"))) is None
    assert services._td(SimpleNamespace(delta=-1.0, td=-528.0)) is None
    assert services._td(SimpleNamespace(delta=-6.0, td=-87.0)) == -87.0


def test_rows_use_implied_ivs_for_skew_and_have_iv_ratio_and_break_evens(mocked):
    rows = flat(services.get_finder())
    for r in rows:
        assert r.short_iv_implied and r.long_iv_implied
        assert r.short_iv == r.short_iv_implied and r.long_iv == r.long_iv_implied
        assert r.skew == pytest.approx(r.short_iv - r.long_iv, abs=1e-6)
        assert r.iv_ratio == pytest.approx(r.short_iv / r.long_iv)
        assert r.break_evens and r.break_evens.lower < r.strike < r.break_evens.upper
        assert r.td is None or isinstance(r.td, float)
    p = services.get_finder().pairs[0]
    assert p.break_evens == p.near_40_delta.break_evens


def test_row_with_a_nan_td_still_round_trips():
    r = flat_row_with_td(None)
    assert type(r).model_validate_json(r.model_dump_json()) == r


def flat_row_with_td(td):
    from tests.test_models import row
    return row().model_copy(update={"td": td})


def test_get_spot_batches_one_call_and_tolerates_missing(monkeypatch):
    calls = []
    monkeypatch.setattr(schwab_api, "get_quotes", lambda syms: calls.append(syms) or {
        "$SPX": {"bid": None, "ask": None, "mark": 7000.5, "last": 7001.0},
        "$VIX": {"bid": None, "ask": None, "mark": 18.0, "last": None}})
    s = services.get_spot()
    assert calls == [["$SPX", "$VIX", "$VIX9D"]]
    assert (s.spx, s.vix, s.vix9d) == (7001.0, 18.0, None)


def test_get_expirations_flags_widths_without_a_pair(monkeypatch):
    monkeypatch.setattr(services, "market_today", lambda: date(2027, 1, 12))
    res = services.get_expirations((25, 35), (4, 7))
    assert 3 in res.unavailable_widths                        # Presidents' Day kills the 3-day pair
    assert {p.width for p in res.pairs} == {4, 7}


def test_cli_table_survives_a_dash_td(mocked, capsys):
    import cli
    res = services.get_finder()
    res.pairs[0].rows[0].td = None
    assert "-" in cli.format_finder(res)
