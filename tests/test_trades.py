from datetime import date

import pytest

from app.core import config, schwab_api, services
from app.core.models import Spot
from app.core.stability import StabilityTracker
from app.core.store import DuplicateTradeError, Store
from tests.test_services import CHAIN


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(services, "quote_tracker", StabilityTracker(clock=clock))
    monkeypatch.setattr(services, "market_today", lambda: date(2026, 11, 24))
    monkeypatch.setattr(schwab_api, "get_chain", lambda s, p, **kw: CHAIN)
    monkeypatch.setattr(schwab_api, "get_call_chain", lambda s, p, **kw: CHAIN)
    store = Store(str(tmp_path / "t.db"))
    store.init()
    res = services.get_finder(dte_range=(7, 56), widths=(7,))
    pair = next(p for p in res.pairs if p.rows)
    row = pair.near_target_delta
    quotes = {"mid": 12.80}

    def fake_get_quotes(symbols, use_cache=True):
        assert use_cache is False                   # a stability check must never read the cache
        m = quotes["mid"]
        # short 137.6 / 139.3, long = short + calendar: bid = lb - 139.3, ask = la - 137.6
        sb, sa = 137.6, 139.3
        lb, la = sa + m - 1.4, sb + m + 1.4        # calendar bid = lb - sa, ask = la - sb: m -/+ 1.4
        return {row.short.symbol: {"bid": sb, "ask": sa, "mark": None, "last": None},
                row.long.symbol: {"bid": lb, "ask": la, "mark": None, "last": None}}
    monkeypatch.setattr(schwab_api, "get_quotes", fake_get_quotes)
    return type("Env", (), dict(clock=clock, store=store, pair=pair, row=row, quotes=quotes,
                                spot=Spot(time="2026-11-24T10:00:00-05:00", spx=6800.0, vix=20.0, vix9d=19.0)))


def ask(env, **kw):
    return services.quote_spread(env.row.short.symbol, env.row.long.symbol, **kw)


def poll(env, n, step=2.0, **kw):
    out = None
    for _ in range(n):
        out = ask(env, **kw)
        env.clock.t += step
    return out


def test_five_steady_quotes_make_the_price_stable_and_one_jump_resets(env):
    first = ask(env)
    assert not first.is_stable and first.waiting_reason == "Waiting for 5 quotes (1 so far)"
    assert poll(env, 5).is_stable
    env.quotes["mid"] = 13.60
    jumped = ask(env)
    assert not jumped.is_stable and "Price moved" in jumped.waiting_reason


def test_suggested_price_is_mid_plus_ten_cents_on_the_nickel_grid(env):
    q = ask(env)
    assert q.mid == pytest.approx(12.80) and q.suggested_price == 12.90
    env.quotes["mid"] = 12.83
    assert ask(env).suggested_price == 12.95          # 12.93 rounds to the nearest 0.05


def test_give_up_after_sixty_unstable_seconds_and_keep_waiting_restarts_it(env):
    for i in range(33):                               # the price keeps moving: never stable
        env.quotes["mid"] = 12.0 + (i % 2) * 0.5
        last = ask(env)
        env.clock.t += 2.0
    assert not last.is_stable and last.give_up and last.seconds_waiting >= config.WAIT_TIMEOUT_S
    env.quotes["mid"] = 12.0
    again = ask(env, keep_waiting=True)
    assert not again.give_up and again.seconds_waiting == 0.0


def test_contracts_follow_the_size_by_request_not_the_finder(env):
    q = ask(env, size_mode="margin", size_value=10_000)
    assert q.contracts == 8 and q.margin == pytest.approx(8 * 12.80 * 100)
    assert q.cost == pytest.approx(8 * 12.90 * 100)
    assert ask(env, size_mode="contracts", size_value=3).contracts == 3
    assert ask(env, size_mode="margin", size_value=20_000).contracts == 16
    assert ask(env, fill_price=13.00).cost == pytest.approx(8 * 13.00 * 100)     # cost follows the typed price


def test_open_trade_saves_one_row_with_the_entry_snapshot(env):
    poll(env, 5)
    res = services.open_trade(env.store, env.pair, env.row, env.spot, "margin", 10_000, 8, 12.90)
    t = res.trade
    assert t.id and res.warnings == [] and len(env.store.list_trades()) == 1
    assert (t.strike, t.contracts, t.open_fill, t.open_suggested) == (env.row.strike, 8, 12.90, 12.90)
    assert t.open_price_source == "auto" and (t.open_bid, t.open_ask) == pytest.approx((11.4, 14.2))
    assert t.open_mid == pytest.approx(12.80) and t.open_range_low == t.open_range_high == pytest.approx(12.80)
    assert (t.entry_spx, t.entry_vix, t.entry_vix9d) == (6800.0, 20.0, 19.0)
    assert t.entry_skew == pytest.approx(env.row.skew) and t.entry_short_iv == env.row.short_iv
    assert t.entry_break_lower == env.row.break_evens.lower and t.entry_vol_pnl is None
    assert t.account == "Paper" and t.status == "open" and t.opened_at.startswith("20")


def test_a_typed_price_is_tagged_manual_and_outside_the_bid_ask_warns(env):
    poll(env, 5)
    res = services.open_trade(env.store, env.pair, env.row, env.spot, "margin", 10_000, 8, 15.00)
    assert res.trade.open_price_source == "manual"
    assert len(res.warnings) == 1 and "outside the bid-ask" in res.warnings[0]
    inside = services.open_trade(env.store, env.pair, env.row, env.spot, "margin", 10_000, 8, 12.95, account="B")
    assert inside.trade.open_price_source == "manual" and inside.warnings == []


def test_a_second_identical_open_is_refused(env):
    services.open_trade(env.store, env.pair, env.row, env.spot, "margin", 10_000, 8, 12.90)
    with pytest.raises(DuplicateTradeError):
        services.open_trade(env.store, env.pair, env.row, env.spot, "margin", 10_000, 8, 12.90)
    assert len(env.store.list_trades()) == 1


@pytest.mark.parametrize("kw,msg", [(dict(fill_price=0), "above zero"), (dict(contracts=0), "at least 1"),
                                    (dict(size_mode="shares"), "Size mode")])
def test_bad_requests_are_refused_and_save_nothing(env, kw, msg):
    args = dict(size_mode="margin", size_value=10_000, contracts=8, fill_price=12.9)
    args.update(kw)
    with pytest.raises(ValueError, match=msg):
        services.open_trade(env.store, env.pair, env.row, env.spot, **args)
    assert env.store.list_trades() == []


def test_vol_pnl_at_entry_uses_the_previous_days_ivs(env):
    from app.core.models import FinderResult
    prev = env.pair.model_copy(deep=True)
    for r in prev.rows:                              # yesterday's IVs were 1 vol point lower on both legs
        r.short_iv, r.long_iv = r.short_iv - 1.0, r.long_iv - 1.0
    yesterday = FinderResult(time="2026-11-23T16:20:00-05:00", spx=6800.0, filters={}, pairs=[prev])
    env.store.log_finder(yesterday)
    res = services.open_trade(env.store, env.pair, env.row, env.spot, "margin", 10_000, 8, 12.90,
                              opened_at="2026-11-24T10:00:00-05:00")
    expected = (-1.0 * env.row.short_vega + 1.0 * env.row.long_vega) * 100 * 8
    assert res.trade.entry_vol_pnl == pytest.approx(expected)
