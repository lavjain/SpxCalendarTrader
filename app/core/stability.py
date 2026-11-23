"""The stability check before a fill: is the calendar's price steady enough to trust? No web imports.

Stable = the last STABLE_QUOTES quotes in a row all have a bid and ask, their mids stay within
STABLE_RANGE ($0.10) high to low, and the latest bid-ask is at most MAX_SPREAD_PCT (10%) of mid.
While it is not stable the result says why, in a short sentence the dialog shows as is."""
from app.core import config
from app.core.models import CalendarQuote, OptionQuote, StabilityResult

_EPS = 1e-9


def calendar_quote(short: OptionQuote, long: OptionQuote) -> CalendarQuote:
    """Bid = long bid - short ask, ask = long ask - short bid. A missing leg quote gives an all-None quote
    (never a 0 price)."""
    if None in (short.bid, short.ask, long.bid, long.ask):
        return CalendarQuote()
    bid, ask = long.bid - short.ask, long.ask - short.bid
    return CalendarQuote(bid=bid, ask=ask, mid=(bid + ask) / 2.0, spread=ask - bid)


def _valid(q: CalendarQuote | None) -> bool:
    return q is not None and q.mid is not None and q.bid is not None and q.ask is not None


def check_stability(history: list[CalendarQuote | None], quotes_needed: int = config.STABLE_QUOTES,
                    max_range: float = config.STABLE_RANGE,
                    max_spread_pct: float = config.MAX_SPREAD_PCT) -> StabilityResult:
    """`history` is oldest first. Only the unbroken run of valid quotes at the end counts."""
    run: list[CalendarQuote] = []
    for q in reversed(history):
        if not _valid(q):
            break
        run.append(q)
    run.reverse()
    seen = len(run)
    if history and not _valid(history[-1]):
        return StabilityResult(is_stable=False, waiting_reason="A leg has no bid or ask", quotes_seen=0)
    if seen < quotes_needed:
        return StabilityResult(is_stable=False, quotes_seen=seen,
                               waiting_reason=f"Waiting for {quotes_needed} quotes ({seen} so far)")
    window = run[-quotes_needed:]
    mids = [q.mid for q in window]
    low, high = min(mids), max(mids)
    if high - low > max_range + _EPS:
        return StabilityResult(is_stable=False, quotes_seen=seen, range_low=low, range_high=high,
                               waiting_reason=f"Price moved ${high - low:.2f} in the last {quotes_needed} quotes "
                                              f"(limit ${max_range:.2f})")
    last = window[-1]
    if last.mid <= 0:
        return StabilityResult(is_stable=False, quotes_seen=seen, range_low=low, range_high=high,
                               waiting_reason="The mid price is zero or negative")
    pct = last.spread / last.mid
    if pct > max_spread_pct + _EPS:
        return StabilityResult(is_stable=False, quotes_seen=seen, range_low=low, range_high=high,
                               waiting_reason=f"Bid-ask is {pct:.0%} of mid (limit {max_spread_pct:.0%})")
    return StabilityResult(is_stable=True, quotes_seen=seen, range_low=low, range_high=high)
