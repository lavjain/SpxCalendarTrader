"""One plain function per endpoint (CLAUDE.md rule 2). Pydantic in, Pydantic out; no web imports.

Week 1 implements get_finder(); the other eight keep their signatures and raise
NotImplementedError until their week in docs/PLAN.md.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import math

from scipy.optimize import brentq

from app.core import config, pricing, schwab_api, tos
from app.core.calendar_math import Calendar, Leg
from app.core.expiries import market_today, pick_expiries, previous_trading_day
from app.core.calendar_math import _whole
from app.core.models import (CalendarRow, ExpirationsResult, ExpiryPair, FinderResult, HolidayNote, OpenTradeResult,
                             OptionQuote, PairSummary, QuoteSpread, Spot, TosOrder, Trade)
from app.core.stability import StabilityTracker, calendar_quote_from_prices

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
    for every strike in config.DELTA_BAND. Per pair: one `is_near_target_delta` row (the name is historical: short delta nearest config.DELTA_TARGET)
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
            if config.MODEL_GREEKS and f_short and f_long and implied[0] and implied[1]:
                # Schwab's gamma has 3 decimals (0.001 on both legs, so the difference is exactly 0):
                # use the model gamma at the mid-implied IVs instead
                g_s = pricing.bs_gamma(f_short, legs[0].strike, pricing.years(today, date.fromisoformat(pair.short)),
                                       implied[0] / 100, spx)
                g_l = pricing.bs_gamma(f_long, legs[1].strike, pricing.years(today, date.fromisoformat(pair.long)),
                                       implied[1] / 100, spx)
                row.gamma = (g_l - g_s) * cal.contracts * 100.0
                d_s = pricing.bs_put_delta(f_short, legs[0].strike, pricing.years(today, date.fromisoformat(pair.short)),
                                           implied[0] / 100, spx)
                d_l = pricing.bs_put_delta(f_long, legs[1].strike, pricing.years(today, date.fromisoformat(pair.long)),
                                           implied[1] / 100, spx)
                row.delta = (d_l - d_s) * cal.contracts * 100.0
                row.td = row.theta / abs(row.delta) if abs(row.delta) >= config.TD_MIN_DELTA else None
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
            near.is_near_target_delta, best.is_best_skew = True, True
        be = near.break_evens if near else None
        summaries.append(PairSummary(
            short_expiry=pair.short, long_expiry=pair.long, short_dte=pair.short_dte,
            long_dte=pair.long_dte, width=pair.width, near_target_delta=near,
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
                             unavailable_widths=[w for w in config.WIDTHS if w not in present],
                             holidays=_holiday_notes(dte_range))


def _holiday_notes(dte_range) -> list[HolidayNote]:
    """Holidays that touch a short Friday inside the DTE range or any long date 3-7 days after it."""
    today = market_today()
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    found = {}
    while (friday - today).days <= dte_range[1] + 7:
        if dte_range[0] <= (previous_trading_day(friday) - today).days <= dte_range[1]:
            for d in [friday] + [friday + timedelta(days=w) for w in config.WIDTHS]:
                if d.isoformat() in config.HOLIDAY_NAMES:
                    found[d] = HolidayNote(date=d.isoformat(), name=config.HOLIDAY_NAMES[d.isoformat()],
                                           moves_to=previous_trading_day(d).isoformat())
        friday += timedelta(days=7)
    return [found[d] for d in sorted(found)]


# ---------------------------------------------------------------- break-even diagnostics

def diagnose_finder(dte_range=config.SHORT_DTE_DEFAULT, widths=config.WIDTHS_DEFAULT,
                    strike_sets=config.STRIKE_SETS, pair_index=None, tos=None) -> dict:
    """Why do the break-evens differ from thinkorswim? Returns the inputs behind the target-delta row of
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
    row = summary.near_target_delta
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


def _tick(x: float) -> float:
    """Round a price to the SPX option tick: $0.05 from $3 up, $0.01 below."""
    step = 0.05 if x >= 3 else 0.01
    return round(round(x / step) * step, 2)


def _size_contracts(size_mode: str, size_value: float, mid: float | None) -> int | None:
    """Whole contracts for a size at the calendar's mid (the same rule the Finder uses)."""
    if size_mode == "contracts":
        return int(size_value)
    if mid is None or mid <= 0:
        return None
    return _whole(size_value / (mid * 100.0), config.SIZE_ROUNDING)


def _now_et() -> str:
    return datetime.now(ZoneInfo(config.MARKET_TZ)).isoformat(timespec="seconds")


quote_tracker = StabilityTracker()          # in memory, one per server (CLAUDE.md rule 9)


def quote_spread(short_symbol: str, long_symbol: str, size_mode: str = "margin", size_value: float = config.MARGIN,
                 fill_price: float | None = None, keep_waiting: bool = False) -> QuoteSpread:
    """Re-quote the two legs (never from the cache), add the quote to the stability window and say whether the
    price is steady. `fill_price` is the price in the dialog's box (for the cost); `keep_waiting` restarts the
    60 seconds after the dialog asked Keep Waiting / Cancel."""
    key = (short_symbol, long_symbol)
    if keep_waiting:
        quote_tracker.keep_waiting(key)
    q = schwab_api.get_quotes([short_symbol, long_symbol], use_cache=False)
    s, l = q.get(short_symbol) or {}, q.get(long_symbol) or {}
    cq = calendar_quote_from_prices(s.get("bid"), s.get("ask"), l.get("bid"), l.get("ask"))
    result, waited = quote_tracker.record(key, cq)
    suggested = _tick(cq.mid + config.FILL_OFFSET) if cq.mid is not None else None
    contracts = _size_contracts(size_mode, size_value, cq.mid)
    price = fill_price if fill_price else suggested
    return QuoteSpread(
        time=_now_et(), bid=cq.bid, ask=cq.ask, mid=cq.mid, spread=cq.spread, suggested_price=suggested,
        is_stable=result.is_stable, waiting_reason=result.waiting_reason, quotes_seen=result.quotes_seen,
        seconds_waiting=round(waited, 1), stability_required=config.REQUIRE_STABLE, give_up=(not result.is_stable and waited >= config.WAIT_TIMEOUT_S),
        range_low=result.range_low, range_high=result.range_high, contracts=contracts,
        cost=(contracts * price * 100.0) if contracts and price else None,
        margin=(contracts * cq.mid * 100.0) if contracts and cq.mid is not None else None)


def tos_order(side: str, contracts: int, short_expiry: str, long_expiry: str, strike: float, price: float) -> str:
    """The thinkorswim order line to paste into TOS. The app sends nothing."""
    return tos.format_order(side, contracts, short_expiry, long_expiry, strike, price)


def parse_tos_order(text: str, short_expiry: str | None = None, long_expiry: str | None = None,
                    strike: float | None = None) -> TosOrder:
    """Read a pasted thinkorswim line for the open dialog. It must be a BUY (a SELL is a closing order, week 5) and,
    when the dialog's calendar is given, must be that calendar. Raises tos.TosParseError with the reason."""
    order = tos.parse_order(text)
    if order.side == "SELL":
        raise tos.TosParseError("This is a closing order: paste it in Close Trade (week 5)")
    if short_expiry and (order.short_expiry, order.long_expiry) != (short_expiry, long_expiry):
        raise tos.TosParseError(f"This line is for {order.short_expiry} / {order.long_expiry}, not {short_expiry} / {long_expiry}")
    if strike is not None and abs(order.strike - strike) > 1e-6:
        raise tos.TosParseError(f"This line is for strike {order.strike:g}, not {strike:g}")
    return order


def open_trade(store, pair: PairSummary, row: CalendarRow, spot: Spot | None, size_mode: str, size_value: float,
               contracts: int, fill_price: float, price_source: str | None = None,
               snapshot_source: str = "refresh", account: str = "Paper",
               opened_at: str | None = None) -> OpenTradeResult:
    """Save a paper trade. `pair` and `row` come from the Finder snapshot the dialog was opened from (expiries,
    IVs, skew, break-evens); `spot` is a fresh SPX/VIX/VIX9D quote. The market quote saved with the trade is the
    last one the stability check saw for these two legs; the fill price is the one confirmed. `contracts` is what
    the dialog showed. Raises ValueError for a bad request and DuplicateTradeError for an open duplicate."""
    if fill_price is None or fill_price <= 0:
        raise ValueError("The fill price must be above zero")
    if contracts is None or contracts < 1:
        raise ValueError("Contracts must be at least 1")
    if pair.width not in config.WIDTHS:
        raise ValueError(f"A {pair.width}-day width is outside {config.WIDTHS[0]}-{config.WIDTHS[-1]} days")
    if size_mode not in config.SIZE_MODES:
        raise ValueError(f"Size mode must be one of {config.SIZE_MODES}")
    quote, _ = quote_tracker.latest((row.short.symbol, row.long.symbol))
    suggested = _tick(quote.mid + config.FILL_OFFSET) if quote and quote.mid is not None else None
    source = price_source or ("auto" if suggested is not None and abs(fill_price - suggested) < 1e-9 else "manual")
    warnings = []
    if quote and quote.bid is not None and not (quote.bid - 1e-9 <= fill_price <= quote.ask + 1e-9):
        warnings.append(f"The fill ${fill_price:.2f} is outside the bid-ask ${quote.bid:.2f} to ${quote.ask:.2f}")
    when = opened_at or _now_et()
    vol = None
    prev = store.previous_close_ivs(when[:10], pair.short_expiry, pair.long_expiry, row.strike)
    if prev and prev[0] is not None and prev[1] is not None:
        vol = pricing.vol_pnl(row.short_iv - prev[0], row.long_iv - prev[1], row.short_vega, row.long_vega, contracts)
    be = row.break_evens
    trade = Trade(
        account=account, opened_at=when, short_expiry=pair.short_expiry, long_expiry=pair.long_expiry,
        strike=row.strike, width=pair.width, short_dte=pair.short_dte, contracts=contracts,
        size_mode=size_mode, size_value=size_value,
        open_bid=quote.bid if quote else None, open_ask=quote.ask if quote else None,
        open_mid=quote.mid if quote else None,
        open_range_low=None, open_range_high=None,
        open_suggested=suggested, open_fill=fill_price, open_price_source=source,
        entry_spx=spot.spx if spot else None, entry_vix=spot.vix if spot else None,
        entry_vix9d=spot.vix9d if spot else None, entry_short_iv=row.short_iv, entry_long_iv=row.long_iv,
        entry_skew=row.skew, entry_break_lower=be.lower if be else None, entry_break_upper=be.upper if be else None,
        entry_vol_pnl=vol, entry_snapshot_source=snapshot_source)
    _, result = quote_tracker.latest((row.short.symbol, row.long.symbol))
    if result is not None:
        trade.open_range_low, trade.open_range_high = result.range_low, result.range_high
    trade.id = store.insert_trade(trade)
    return OpenTradeResult(trade=trade, warnings=warnings)


def close_trade(trade_id: int, price: float, price_source: str = "auto", exit_reason: str | None = None,
                notes: str | None = None):
    """In: trade id plus fill and exit reason. Out: Trade (closed, with realised P/L)."""
    raise NotImplementedError("close_trade: weeks 3-4")
