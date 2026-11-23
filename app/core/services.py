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
from app.core.models import CalendarRow, ExpiryPair, FinderResult, OptionQuote, PairSummary

SYMBOL = "$SPX"


# ---------------------------------------------------------------- the Finder

def _leg(q: OptionQuote, dte: int) -> Leg:
    return Leg(dte, q.mark, q.delta, q.gamma or 0.0, q.theta or 0.0, q.vega or 0.0, q.iv)


def _calendar(short: OptionQuote, long: OptionQuote, pair: ExpiryPair, size_mode, size_value):
    s, l = _leg(short, pair.short_dte), _leg(long, pair.long_dte)
    debit = l.mark - s.mark
    if debit <= 0:
        return None
    if size_mode == "margin":
        capital = size_value
    else:                                    # a fixed contract count: ceil((n - 0.5)) == n
        capital = (size_value - 0.5) * debit * 100.0
    cal = Calendar(s, l, capital)
    return cal if cal.contracts > 0 else None


def _row(short, long, pair, cal) -> CalendarRow:
    return CalendarRow(
        strike=short.strike, width=pair.width, short=short, long=long, contracts=cal.contracts,
        price=float(cal.debit), margin=float(cal.margin), delta=float(cal.delta),
        gamma=float(cal.gamma), theta=float(cal.theta), vega=float(cal.vega),
        short_iv=float(short.iv), long_iv=float(long.iv),
        short_vega=float(short.vega or 0.0), long_vega=float(long.vega or 0.0),
        skew=float(cal.skew), td=float(cal.td), theta_margin=float(cal.theta_margin))


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
            cal = _calendar(*legs, pair, size_mode, size_value) if legs else None
            if cal:
                row = _row(*legs, pair, cal)
                if f_short and f_long:      # IVs that reproduce the mids, for P/L and break-evens
                    row.short_iv_implied = pricing.implied_iv(row.short, f_short, today)
                    row.long_iv_implied = pricing.implied_iv(row.long, f_long, today)
                rows.append(row)
        near = best = None
        if rows:
            near = min(rows, key=lambda r: abs(abs(r.short.delta) - config.DELTA_TARGET))
            best = max(rows, key=lambda r: r.skew)
            near.is_near_40_delta, best.is_best_skew = True, True
        be = None
        if near and f_long:
            try:
                be = pricing.break_evens(near, spx, f_long, today)
            except ValueError:
                be = None
        summaries.append(PairSummary(
            short_expiry=pair.short, long_expiry=pair.long, short_dte=pair.short_dte,
            long_dte=pair.long_dte, width=pair.width, near_40_delta=near,
            best_skew=best.skew if best else None, best_skew_strike=best.strike if best else None,
            break_evens=be, strike_count=len(rows), rows=rows))
    return FinderResult(time=now.isoformat(timespec="seconds"), spx=spx, filters=filters,
                        pairs=summaries)


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
