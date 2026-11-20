"""Which short Fridays and long dates the Finder looks at. Plain dates in market time, no web imports."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core import config
from app.core.models import ExpiryPair


def market_today() -> date:
    return datetime.now(ZoneInfo(config.MARKET_TZ)).date()


def is_trading_day(d: date, holidays=config.MARKET_HOLIDAYS) -> bool:
    return d.weekday() < 5 and d.isoformat() not in holidays


def previous_trading_day(d: date, holidays=config.MARKET_HOLIDAYS) -> date:
    """d itself if it trades, otherwise the closest earlier trading day."""
    while not is_trading_day(d, holidays):
        d -= timedelta(days=1)
    return d


def pick_expiries(today: date, dte_range=config.SHORT_DTE_DEFAULT, widths=config.WIDTHS_DEFAULT,
                  holidays=config.MARKET_HOLIDAYS) -> list[ExpiryPair]:
    """One short per Friday whose DTE is inside `dte_range`; long = that Friday + width days.

    A holiday short Friday moves to the Thursday before, and so does a holiday long date. Widths
    are counted from the nominal Friday, not from the adjusted Thursday; a pair whose long ends up
    on or before the short is dropped. DTE is counted to the actual (adjusted) expiry."""
    lo, hi = dte_range
    lim_lo, lim_hi = config.SHORT_DTE_LIMITS
    if not (lim_lo <= lo <= hi <= lim_hi):
        raise ValueError(f"dte_range must sit inside {config.SHORT_DTE_LIMITS}, got {dte_range}")
    bad = [w for w in widths if w not in config.WIDTHS]
    if bad:
        raise ValueError(f"widths must be from {config.WIDTHS}, got {bad}")

    pairs = []
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    # a holiday Friday can pull its expiry one day earlier, so look a few days past the range
    while (friday - today).days <= hi + 7:
        short = previous_trading_day(friday, holidays)
        short_dte = (short - today).days
        if lo <= short_dte <= hi:
            for w in sorted(set(widths)):
                long = previous_trading_day(friday + timedelta(days=w), holidays)
                if long > short:
                    pairs.append(ExpiryPair(short=short.isoformat(), long=long.isoformat(),
                                            short_dte=short_dte, long_dte=(long - today).days,
                                            width=w))
        friday += timedelta(days=7)
    return pairs
