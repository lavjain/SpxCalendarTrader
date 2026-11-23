"""One plain function per endpoint (CLAUDE.md rule 2). Pydantic in, Pydantic out; no web imports.

Week 1 implements get_finder(); the other eight keep their signatures and raise
NotImplementedError until their week in docs/PLAN.md.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import math

from scipy.optimize import brentq

from app.core import config, pricing, schwab_api
from app.core.calendar_math import Calendar, Leg
from app.core.expiries import market_today, pick_expiries
from app.core.models import (CalendarRow, ExpirationsResult, ExpiryPair, FinderResult, OptionQuote,
                             PairSummary, Spot)

SYMBOL = "$SPX"


# ---------------------------------------------------------------- the Finder

def _leg(q: OptionQuote, dte: int, iv: float) -> Leg:
    return Leg(dte, q.mark, q.delta, q.gamma or 0.0, q.theta or 0.0, q.vega or 0.0, iv)


def _td(cal) -> float | None:
    """Theta / delta, or None when position delta is too small for the ratio to mean anything."""
    if abs(cal.delta) < config.TD_MIN_DELTA:
        return None
    return float(cal.td)


def _calendar(short: OptionQuote, long: OptionQuote, pair: ExpiryPair, size_mode, size_value,
              short_iv: float, long_iv: float):
    s, l = _leg(short, pair.short_dte, short_iv), _leg(long, pair.long_dte, long_iv)
    debit = l.mark - s.mark
    if debit <= 0:
        return None
    if size_mode == "margin":
        cal = Calendar(s, l, size_value, rounding=config.SIZE_ROUNDING)
    else:                                    # a fixed contract count
        cal = Calendar(s, l, 0.0, contracts=int(size_value))
    return cal if cal.contracts > 0 else None


def _row(short, long, pair, cal, short_iv, long_iv, implied) -> CalendarRow:
    """short_iv / long_iv are the IVs used (mid-implied when available, else Schwab's)."""
    return CalendarRow(
        strike=short.strike, width=pair.width, short=short, long=long, contracts=cal.contracts,
        price=float(cal.debit), margin=float(cal.margin), delta=float(cal.delta),
        gamma=float(cal.gamma), theta=float(cal.theta), vega=float(cal.vega),
        short_iv=float(short_iv), long_iv=float(long_iv),
        short_vega=float(short.vega or 0.0), long_vega=float(long.vega or 0.0),
        short_iv_implied=implied[0], long_iv_implied=implied[1],
        skew=float(cal.skew), td=_td(cal), theta_margin=float(cal.theta_margin),
        iv_ratio=float(short_iv / long_iv) if long_iv else None)


def _spot(chain) -> float:
    spot = chain.get("underlyingPrice") or (chain.get("underlying") or {}).get("last")
    if not spot:
        raise ValueError("the chain has no underlying price")
    return float(spot)


def get_finder(dte_range=config.SHORT_DTE_DEFAULT, widths=config.WIDTHS_DEFAULT,
               strike_sets=config.STRIKE_SETS, size_mode="margin",
               size_value=config.MARGIN) -> FinderResult:
    """Pick expiry pairs, pull the chain, and return one PairSummary per pair with a CalendarRow
    for every 35-45 delta strike. Per pair: one `is_near_40_delta` row (short delta nearest 0.40)
    and one `is_best_skew` row (highest short IV - long IV)."""
    if size_mode not in config.SIZE_MODES:
        raise ValueError(f"size_mode must be one of {config.SIZE_MODES}")
    if size_value <= 0 or (size_mode == "contracts" and int(size_value) != size_value):
        raise ValueError("size_value must be positive (a whole number for contracts)")
    today = market_today()
    pairs = pick_expiries(today, dte_range, widths)
    now = datetime.now(ZoneInfo(config.MARKET_TZ))
    filters = {"dte_range": list(dte_range), "widths": list(widths), "strike_sets": list(strike_sets),
               "size_mode": size_mode, "size_value": size_value}
    if not pairs:
        return FinderResult(time=now.isoformat(timespec="seconds"), spx=0.0, filters=filters, pairs=[])

    put_chain = schwab_api.get_chain(SYMBOL, pairs, today=today)
    call_chain = schwab_api.get_call_chain(SYMBOL, pairs)
    spx = _spot(put_chain)
    puts = schwab_api.parse(put_chain, pairs, strike_sets)
    parity = schwab_api.parse_parity_quotes(put_chain, call_chain, pairs)

    def forward(expiry):
        try:
            return pricing.forward_from_parity(parity, expiry, today)
        except ValueError:
            return None

    summaries = []
    for pair in pairs:
        f_short, f_long = forward(pair.short), forward(pair.long)
        strikes = sorted({q.strike for q in puts if q.expiry == pair.short})
        rows = []
        for k in strikes:
            legs = schwab_api.calendar_legs(puts, pair.short, pair.long, k)
            if not legs:
                continue
            implied = (None, None)
            if f_short and f_long:      # IVs that reproduce the mids, for skew, P/L and break-evens
                implied = (pricing.implied_iv(legs[0], f_short, today),
                           pricing.implied_iv(legs[1], f_long, today))
            s_iv, l_iv = implied[0] or legs[0].iv, implied[1] or legs[1].iv
            cal = _calendar(*legs, pair, size_mode, size_value, s_iv, l_iv)
            if not cal:
                continue
            row = _row(*legs, pair, cal, s_iv, l_iv, implied)
            if f_long:
                try:
                    row.break_evens = pricing.break_evens(row, spx, f_long, today)
                except ValueError:
                    row.break_evens = None
            rows.append(row)
        near = best = None
        if rows:
            near = min(rows, key=lambda r: abs(abs(r.short.delta) - config.DELTA_TARGET))
            best = max(rows, key=lambda r: r.skew)
            near.is_near_40_delta, best.is_best_skew = True, True
        be = near.break_evens if near else None
        summaries.append(PairSummary(
            short_expiry=pair.short, long_expiry=pair.long, short_dte=pair.short_dte,
            long_dte=pair.long_dte, width=pair.width, near_40_delta=near,
            best_skew=best.skew if best else None, best_skew_strike=best.strike if best else None,
            break_evens=be, strike_count=len(rows), rows=rows))
    return FinderResult(time=now.isoformat(timespec="seconds"), spx=spx, filters=filters,
                        pairs=summaries)


# ---------------------------------------------------------------- spot and expirations

def _px(d: dict) -> float | None:
    """Last price for an index quote, else the mark; None if Schwab sent neither."""
    return d.get("last") if d.get("last") is not None else d.get("mark")


def get_spot() -> Spot:
    """SPX, VIX and VIX9D in one batched quotes call. Anything Schwab doesn't send is None."""
    q = schwab_api.get_quotes(["$SPX", "$VIX", "$VIX9D"])
    now = datetime.now(ZoneInfo(config.MARKET_TZ)).isoformat(timespec="seconds")
    return Spot(time=now, spx=_px(q.get("$SPX", {})), vix=_px(q.get("$VIX", {})),
                vix9d=_px(q.get("$VIX9D", {})))


def get_expirations(dte_range=config.SHORT_DTE_DEFAULT, widths=config.WIDTHS_DEFAULT) -> ExpirationsResult:
    """The expiry pairs for the filters, and which of the widths 3-7 have no pair this week."""
    all_pairs = pick_expiries(market_today(), dte_range, config.WIDTHS)
    present = {p.width for p in all_pairs}
    return ExpirationsResult(pairs=[p for p in all_pairs if p.width in widths],
                             unavailable_widths=[w for w in config.WIDTHS if w not in present])


# ---------------------------------------------------------------- break-even diagnostics

def diagnose_finder(dte_range=config.SHORT_DTE_DEFAULT, widths=config.WIDTHS_DEFAULT,
                    strike_sets=config.STRIKE_SETS, pair_index=None, tos=None) -> dict:
    """Why do the break-evens differ from thinkorswim? Returns the inputs behind the ~40-delta row of
    one pair (default: the short nearest 30 DTE) and the break-evens under variants: no fill offset,
    zero carry (forward = spot), and Schwab's IV field instead of the mid-implied IVs.

    `tos` = (lower, upper) break-evens read from thinkorswim, to print the distance error of each."""
    today = market_today()
    result = get_finder(dte_range, widths, strike_sets)
    if not result.pairs:
        raise ValueError("no pairs")
    summaries = result.pairs
    i = pair_index if pair_index is not None else min(
        range(len(summaries)), key=lambda j: abs(summaries[j].short_dte - config.SHORT_DTE_TARGET))
    summary = summaries[i]
    row = summary.near_40_delta
    if row is None:
        raise ValueError("that pair has no rows")
    pair = pick_expiries(today, dte_range, widths)[i]
    put_chain = schwab_api.get_chain(SYMBOL, [pair], today=today)       # cached: same URL as above
    call_chain = schwab_api.get_call_chain(SYMBOL, [pair])
    parity = schwab_api.parse_parity_quotes(put_chain, call_chain, [pair])
    spot = result.spx
    f_s = pricing.forward_from_parity(parity, pair.short, today)
    f_l = pricing.forward_from_parity(parity, pair.long, today)
    t_l = pricing.years(today, date.fromisoformat(pair.long))
    legs = []
    for name, q, f in (("short", row.short, f_s), ("long", row.long, f_l)):
        t = pricing.years(today, date.fromisoformat(q.expiry))
        mid = pricing.mid(q)
        legs.append({"leg": name, "expiry": q.expiry, "strike": q.strike, "t_days": (date.fromisoformat(q.expiry) - today).days,
                     "bid": q.bid, "ask": q.ask, "mark": q.mark, "mid": mid, "schwab_iv": q.iv,
                     "forward": f, "model_at_schwab_iv": float(pricing.bs_put(f, q.strike, t, q.iv / 100)),
                     "implied_iv_from_mid": pricing.implied_iv(q, f, today)})
    schwab_ivs = row.model_copy(update={"short_iv_implied": None, "long_iv_implied": None})

    def be(trade, fwd, offset):
        try:
            b = pricing.break_evens(trade, spot, fwd, today, fill_offset=offset)
            return b.lower, b.upper
        except ValueError:
            return None

    variants = {"app (IVs implied from mids)": be(row, f_l, config.FILL_OFFSET),
                "old: Schwab's IV field": be(schwab_ivs, f_l, config.FILL_OFFSET),
                "app, no fill offset": be(row, f_l, 0.0),
                "app, carry 0 (forward = spot)": be(row, spot, config.FILL_OFFSET)}
    out = {"spx": spot, "strike": row.strike, "pair": f"{pair.short} -> {pair.long}", "price": row.price,
           "forward_short": f_s, "forward_long": f_l,
           "carry_per_year": math.log(f_l / spot) / t_l, "legs": legs, "variants": variants}
    if tos:
        out["tos"] = list(tos)
    return out


# ---------------------------------------------------------------- later weeks (signatures only)

def get_holdings(account: str = "Paper"):
    """In: account. Out: HoldingsResult (summary cards, open trades with flags, closed list)."""
    raise NotImplementedError("get_holdings: week 4")


def get_performance(account: str = "Paper", period: str = "all", group: str = "month"):
    """In: account, period, grouping. Out: PerformanceResult (summary, groupings, exits, trades)."""
    raise NotImplementedError("get_performance: weeks 5-6")


def get_risk_profile(trade_id: int | None = None, calendar: CalendarRow | None = None):
    """In: a saved trade or a Finder CalendarRow. Out: RiskProfile (SPX grid, curves, break-evens)."""
    raise NotImplementedError("get_risk_profile: week 3")


def get_spx_history(range: str = "3M"):
    """In: range chip (1M-2Y). Out: SpxHistory (daily candles, averages, tiles)."""
    raise NotImplementedError("get_spx_history: week 5")


def quote_spread(short: OptionQuote, long: OptionQuote):
    """In: the two legs. Out: SpreadQuote (bid/ask/mid, is_stable, waiting_reason, suggested_price)."""
    raise NotImplementedError("quote_spread: week 3")


def parse_tos_order(line: str):
    """In: a thinkorswim order line. Out: ParsedOrder (legs, price, contracts, side)."""
    raise NotImplementedError("parse_tos_order: week 3")


def open_trade(calendar: CalendarRow, size_mode: str, size_value: float, price: float,
               price_source: str = "auto", account: str = "Paper"):
    """In: a CalendarRow plus size and fill. Out: Trade (saved, with entry snapshot and tos_order)."""
    raise NotImplementedError("open_trade: week 3")


def close_trade(trade_id: int, price: float, price_source: str = "auto", exit_reason: str | None = None,
                notes: str | None = None):
    """In: trade id plus fill and exit reason. Out: Trade (closed, with realised P/L)."""
    raise NotImplementedError("close_trade: weeks 3-4")
