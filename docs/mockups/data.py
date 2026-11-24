"""Simulated data for the screen mockups. Every number comes from code:
Black-Scholes on a made-up SPX chain, sized and scored by the repo's calendar_math.
Nothing here is real market data."""
import math, random, sys
from datetime import date, datetime, timedelta
from pathlib import Path
from scipy.stats import norm
from scipy.optimize import brentq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root
from app.core import config  # the delta band and target the real Finder uses
from app.core.calendar_math import Leg, Calendar  # the repo's own sizing/greeks/skew math

R, Q = 0.040, 0.013
MARGIN, FILL = 10_000, 0.10
HOLIDAYS = {  # NYSE closures used by the mockups
    date(2026, 11, 26), date(2026, 12, 25), date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15),
    date(2027, 3, 26), date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6)}


def bs_put(S, K, T, v):
    T = max(T, 1e-6)
    d1 = (math.log(S / K) + (R - Q + 0.5 * v * v) * T) / (v * math.sqrt(T))
    d2 = d1 - v * math.sqrt(T)
    px = K * math.exp(-R * T) * norm.cdf(-d2) - S * math.exp(-Q * T) * norm.cdf(-d1)
    delta = -math.exp(-Q * T) * norm.cdf(-d1)
    gamma = math.exp(-Q * T) * norm.pdf(d1) / (S * v * math.sqrt(T))
    vega = S * math.exp(-Q * T) * norm.pdf(d1) * math.sqrt(T) / 100
    theta = (-S * math.exp(-Q * T) * norm.pdf(d1) * v / (2 * math.sqrt(T))
             + R * K * math.exp(-R * T) * norm.cdf(-d2)
             - Q * S * math.exp(-Q * T) * norm.cdf(-d1)) / 365
    return px, delta, gamma, theta, vega


def iv(S, K, dte, atm):
    """Put skew, steeper in the front (scales with 1/sqrt(T))."""
    m = math.log(K / S)
    return atm - 0.95 * m * math.sqrt(30 / dte)


WIDTHS = (3, 4, 5, 6, 7)


def trading_day(d):
    return d.weekday() < 5 and d not in HOLIDAYS


STRIKE_SETS = ("10", "25")  # "10": multiples of 10; "25": multiples of 25. Both on (default) = 10s plus 25s/75s


def strike_ok(K, sets=STRIKE_SETS):
    """Strikes SPX reliably lists a month out: multiples of 10 and/or 25, as switched on."""
    return ("10" in sets and K % 10 == 0) or ("25" in sets and K % 25 == 0)


def short_fridays(today, dte_lo=25, dte_hi=35):
    """Fridays whose DTE falls in the short-leg DTE filter (7 to 56 days)."""
    return [today + timedelta(days=d) for d in range(dte_lo, dte_hi + 1)
            if (today + timedelta(days=d)).weekday() == 4]


def pick_expiries(today, width=7, friday=None):
    """Short: the given Friday (default: the one nearest 30 DTE), Thursday if that Friday is a holiday.
    Long: that Friday + width days, moved back to the previous trading day if needed;
    None if that lands on or before the short."""
    fri = friday or min(short_fridays(today), key=lambda f: abs((f - today).days - 30))
    short = fri
    while not trading_day(short):
        short -= timedelta(days=1)
    long = fri + timedelta(days=width)
    while not trading_day(long):
        long -= timedelta(days=1)
    return short, (long if long > short else None)


def leg_quote(S, K, today, exp, atm):
    dte = (exp - today).days
    v = iv(S, K, dte, atm)
    px, de, ga, th, ve = bs_put(S, K, dte / 365, v)
    half = max(0.10, round(px * 0.0015 / 0.05) * 0.05)  # ~0.3% wide, 5-cent ticks
    mark = round(px / 0.05) * 0.05
    return dict(dte=dte, iv=v, mark=mark, bid=mark - half, ask=mark + half,
                delta=de, gamma=ga, theta=th, vega=ve)


def leg_obj(q):
    return Leg(q["dte"], q["mark"], q["delta"], q["gamma"], q["theta"], q["vega"], q["iv"])


def finder(S, now, atm_s, atm_l, band=config.DELTA_BAND, width=7, friday=None, sets=STRIKE_SETS):
    today = now.date()
    se, le = pick_expiries(today, width, friday)
    rows = []
    if le is None:  # no long expiry for this width this week
        return dict(now=now, spx=S, width=width, short_exp=se, long_exp=None, rows=[], best=None, near=None)
    for K in range(int(S // 5 * 5) - 400, int(S // 5 * 5) + 1, 5):
        if not strike_ok(K, sets):
            continue
        s = leg_quote(S, K, today, se, atm_s)
        if not band[0] <= abs(s["delta"]) <= band[1]:
            continue
        l = leg_quote(S, K, today, le, atm_l)
        c = Calendar(leg_obj(s), leg_obj(l), MARGIN)
        rows.append(dict(strike=K, s=s, l=l, cal=c,
                         bid=round(l["bid"] - s["ask"], 2), ask=round(l["ask"] - s["bid"], 2)))
    best = max(rows, key=lambda r: r["cal"].skew)
    starrable = [r for r in rows if config.STAR_STRIKE_MULTIPLE and r["strike"] % config.STAR_STRIKE_MULTIPLE == 0] or rows   # same rule as the app
    near = min(starrable, key=lambda r: abs(abs(r["s"]["delta"]) - config.DELTA_TARGET))
    for r in rows:
        r["is_best_skew"] = r is best
        r["is_near_target_delta"] = r is near
    return dict(now=now, spx=S, width=width, short_exp=se, long_exp=le, rows=rows, best=best, near=near)


def value_at_short_expiry(S_T, K, days_left, v_long):
    return bs_put(S_T, K, days_left / 365, v_long)[0] - max(K - S_T, 0.0)


def break_evens(K, short_exp, long_exp, v_long, entry_price):
    days_left = (long_exp - short_exp).days
    f = lambda x: value_at_short_expiry(x, K, days_left, v_long) - entry_price
    peak = max(range(int(K) - 100, int(K) + 101), key=lambda x: f(x))
    return brentq(f, K * 0.85, peak), brentq(f, peak, K * 1.15)


def contracts_for(price):
    return math.ceil(MARGIN / (price * 100))
