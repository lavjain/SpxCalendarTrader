"""Black-Scholes pricing of one put calendar, its P/L curve and break-evens. No web imports.

Conventions: prices and P/L are dollars per share (x100 x contracts for a position); IVs arrive
in vol points (15.2) and are converted here; time is calendar days / 365; plain floats out.
"""
import math
from datetime import date

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

from app.core import config
from app.core.models import BreakEvens, CalendarRow, OptionQuote


# ---------------------------------------------------------------- Black-Scholes, forward form

def bs_put(forward, strike, t, iv, rate=config.RATE):
    """European put on a forward. `iv` is a decimal (0.15). Vectorised over `forward`."""
    f = np.asarray(forward, dtype=float)
    if t <= 0 or iv <= 0:
        return np.maximum(strike - f, 0.0)
    sd = iv * math.sqrt(t)
    d1 = (np.log(f / strike) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    return math.exp(-rate * t) * (strike * norm.cdf(-d2) - f * norm.cdf(-d1))


def bs_call(forward, strike, t, iv, rate=config.RATE):
    f = np.asarray(forward, dtype=float)
    if t <= 0 or iv <= 0:
        return np.maximum(f - strike, 0.0)
    sd = iv * math.sqrt(t)
    d1 = (np.log(f / strike) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    return math.exp(-rate * t) * (f * norm.cdf(d1) - strike * norm.cdf(d2))


def bs_put_delta(forward, strike, t, iv, spot, rate=config.RATE):
    """Put delta per share per 1 SPX point (negative), with the forward moving with spot.
    Schwab's delta has 3 decimals, which makes a calendar's small net delta (and T/D) jumpy."""
    if t <= 0 or iv <= 0:
        return -1.0 if forward < strike else 0.0
    sd = iv * math.sqrt(t)
    d1 = (math.log(forward / strike) + 0.5 * sd * sd) / sd
    return float(-math.exp(-rate * t) * norm.cdf(-d1) * forward / spot)


def dividend_yield(forward, spot, t, rate=config.RATE):
    """The carry q in F = S e^((r-q)T), read from a put-call-parity forward."""
    return rate - math.log(forward / spot) / t


def call_minus_put(q, strike, t, spot, rate=config.RATE):
    """What a call at the same strike and expiry adds to the put's delta and theta, per share (theta per day).
    Put-call parity: C - P = S e^(-qT) - K e^(-rT). Gamma and vega are the same for both."""
    if t <= 0:
        return 0.0, 0.0
    carry = math.exp(-q * t)
    return float(carry), float((q * spot * carry - rate * strike * math.exp(-rate * t)) / 365.0)


def bs_gamma(forward, strike, t, iv, spot, rate=config.RATE):
    """Gamma of the option per share, per 1 SPX point, with the forward moving with spot
    (F = spot x carry). Schwab's gamma is rounded to 3 decimals, which is too coarse for a calendar."""
    if t <= 0 or iv <= 0:
        return 0.0
    sd = iv * math.sqrt(t)
    d1 = (math.log(forward / strike) + 0.5 * sd * sd) / sd
    return float(math.exp(-rate * t) * norm.pdf(d1) * forward / (spot * spot * sd))


# ---------------------------------------------------------------- quotes and the forward

def mid(q: OptionQuote) -> float:
    """(bid + ask) / 2 when both exist, else the mark. A quote with neither is an error, not 0."""
    if q.bid is not None and q.ask is not None:
        return (q.bid + q.ask) / 2
    if q.mark is not None:
        return float(q.mark)
    raise ValueError(f"no price for {q.expiry} {q.right} {q.strike}")


def years(from_date: date, to_date: date) -> float:
    return (to_date - from_date).days / 365


def forward_from_parity(quotes, expiry: str, as_of: date, rate=config.RATE) -> float:
    """F = K + e^(rT) (call - put) at the strike nearest the money for `expiry`.

    "Nearest the money" is the strike where call and put are closest in price, which is where
    K is closest to the forward. Needs a call and a put at the same strike; no dividend input."""
    t = years(as_of, date.fromisoformat(expiry))
    if t <= 0:
        raise ValueError("expiry is not after as_of")
    calls = {q.strike: q for q in quotes if q.expiry == expiry and q.right == "C"}
    puts = {q.strike: q for q in quotes if q.expiry == expiry and q.right == "P"}
    common = sorted(set(calls) & set(puts))
    if not common:
        raise ValueError(f"no strike with both a call and a put on {expiry}")
    k = min(common, key=lambda x: abs(mid(calls[x]) - mid(puts[x])))
    return float(k + math.exp(rate * t) * (mid(calls[k]) - mid(puts[k])))


def implied_iv(q: OptionQuote, forward: float, as_of: date) -> float | None:
    """Vol points that make Black-Scholes reproduce the put's mid on `forward`, or None if no IV can
    (price at or below intrinsic, expiry not after as_of). Schwab's own `volatility` field does not
    reproduce its marks (10+ points off on a 7120 put), so pricing uses this instead."""
    t = years(as_of, date.fromisoformat(q.expiry))
    if t <= 0:
        return None
    try:
        return 100 * brentq(lambda v: float(bs_put(forward, q.strike, t, v)) - mid(q), 0.01, 3.0)
    except ValueError:
        return None


def calendar_value_now(short: OptionQuote, long: OptionQuote) -> float:
    """What the calendar is worth at mid right now: long - short."""
    return float(mid(long) - mid(short))


# ---------------------------------------------------------------- P/L

def _carry(spot: float, long_forward: float, long_t: float) -> float:
    """Net cost of carry (r - q) implied by the long expiry's parity forward."""
    return math.log(long_forward / spot) / long_t if long_t > 0 else 0.0


def pl_curve(trade: CalendarRow, spx_levels, spot: float, long_forward: float, as_of: date,
             at_date: date | None = None, rate=config.RATE, fill_offset=config.FILL_OFFSET):
    """P/L in dollars per share at each SPX level on `at_date` (default: the short expiry).

    Each leg's IV is held fixed (the mid-implied IV when the row has it, else Schwab's). A leg that has expired is worth its intrinsic value; otherwise
    it is priced with Black-Scholes at its IV and remaining days, on a forward that keeps the
    carry implied by `long_forward`. Entry cost is the calendar's mid debit plus `fill_offset`."""
    short_exp = date.fromisoformat(trade.short.expiry)
    long_exp = date.fromisoformat(trade.long.expiry)
    at_date = at_date or short_exp
    if not as_of <= at_date <= short_exp:
        raise ValueError("at_date must be between as_of and the short expiry")
    k = trade.short.strike
    carry = _carry(spot, long_forward, years(as_of, long_exp))
    x = np.asarray(spx_levels, dtype=float)

    def leg(iv, exp):
        t = years(at_date, exp)
        f = x * math.exp(carry * max(t, 0.0))
        return bs_put(f, k, t, (iv or 0.0) / 100, rate)

    long_iv = trade.long_iv_implied or trade.long.iv
    short_iv = trade.short_iv_implied or trade.short.iv
    value = leg(long_iv, long_exp) - leg(short_iv, short_exp)
    return [float(v) for v in value - (trade.price + fill_offset)]


def break_evens(trade: CalendarRow, spot: float, long_forward: float, as_of: date,
                at_date: date | None = None, rate=config.RATE,
                fill_offset=config.FILL_OFFSET) -> BreakEvens:
    """SPX levels where P/L = 0 on `at_date` (default: the short expiry), one each side of the peak."""
    k = trade.short.strike
    at = at_date or date.fromisoformat(trade.short.expiry)

    def f(x):
        return pl_curve(trade, [x], spot, long_forward, as_of, at, rate, fill_offset)[0]

    grid = np.linspace(0.7 * k, 1.3 * k, 1201)
    pl = np.asarray(pl_curve(trade, grid, spot, long_forward, as_of, at, rate, fill_offset))
    peak = int(pl.argmax())
    if pl[peak] <= 0:
        raise ValueError("the calendar never makes money at that date: no break-evens")
    if peak == 0 or peak == len(grid) - 1 or pl[0] > 0 or pl[-1] > 0:
        raise ValueError("break-even outside the 70%-130% strike window")
    lower = brentq(f, grid[0], grid[peak])
    upper = brentq(f, grid[peak], grid[-1])
    return BreakEvens(lower=float(lower), upper=float(upper), at_date=at.isoformat())


def vol_pnl(d_short_iv: float, d_long_iv: float, short_vega: float, long_vega: float, contracts: int) -> float:
    """Tom Conley's Vol P&L in dollars: [(change in short IV) x short vega x (-1) + (change in long IV) x
    long vega] x 100 x contracts. IV changes are in vol points, vegas are per share."""
    return float((-d_short_iv * short_vega + d_long_iv * long_vega) * 100.0 * contracts)
