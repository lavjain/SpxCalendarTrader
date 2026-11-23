"""The stability check before a fill: is the calendar's price steady enough to trust? No web imports.

Stable = the last STABLE_QUOTES quotes in a row all have a bid and ask, their mids stay within
STABLE_RANGE ($0.10) high to low, and the wider leg's bid-ask is at most MAX_SPREAD_PCT (10%) of that leg's mid.
(The calendar's own bid-ask is the sum of both legs' and is about 20% of its mid on SPX, so it is shown but is
not the test: a limit on it would never pass.)
While it is not stable the result says why, in a short sentence the dialog shows as is."""
import threading
import time
from collections import deque

from app.core import config
from app.core.models import CalendarQuote, OptionQuote, StabilityResult

_EPS = 1e-9


def calendar_quote_from_prices(short_bid, short_ask, long_bid, long_ask) -> CalendarQuote:
    """Bid = long bid - short ask, ask = long ask - short bid. A missing leg quote gives an all-None quote
    (never a 0 price)."""
    if None in (short_bid, short_ask, long_bid, long_ask):
        return CalendarQuote()
    bid, ask = long_bid - short_ask, long_ask - short_bid
    pcts = []
    for b, a in ((short_bid, short_ask), (long_bid, long_ask)):
        m = (b + a) / 2.0
        pcts.append((a - b) / m if m > 0 else float("inf"))
    return CalendarQuote(bid=bid, ask=ask, mid=(bid + ask) / 2.0, spread=ask - bid, leg_spread_pct=max(pcts))


def calendar_quote(short: OptionQuote, long: OptionQuote) -> CalendarQuote:
    return calendar_quote_from_prices(short.bid, short.ask, long.bid, long.ask)


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
    pct = last.leg_spread_pct
    if pct is None or pct > max_spread_pct + _EPS:
        shown = "?" if pct is None or pct == float("inf") else f"{pct:.0%}"
        return StabilityResult(is_stable=False, quotes_seen=seen, range_low=low, range_high=high,
                               waiting_reason=f"A leg's bid-ask is {shown} of its price (limit {max_spread_pct:.0%})")
    return StabilityResult(is_stable=True, quotes_seen=seen, range_low=low, range_high=high)


class StabilityTracker:
    """The recent quotes of each calendar being priced in a dialog, kept in memory (one uvicorn worker,
    CLAUDE.md rule 9). A key is the pair of leg symbols. After `silence_s` without a quote (the dialog was
    closed) the key starts over."""

    def __init__(self, clock=time.monotonic, max_quotes: int = 20, silence_s: float = config.WAIT_TIMEOUT_S):
        self._clock, self._max, self._silence = clock, max_quotes, silence_s
        self._lock = threading.Lock()
        self._keys: dict[tuple, dict] = {}

    def record(self, key: tuple, quote: CalendarQuote) -> tuple[StabilityResult, float]:
        """Add a quote; return (stability result, seconds spent waiting for a stable price)."""
        now = self._clock()
        with self._lock:
            st = self._keys.get(key)
            if st is None or now - st["last_time"] > self._silence:
                st = self._keys[key] = {"quotes": deque(maxlen=self._max), "unstable_since": None, "last_quote": None}
            st["last_time"] = now
            st["quotes"].append(quote)
            if _valid(quote):
                st["last_quote"] = quote
            result = check_stability(list(st["quotes"]))
            if result.is_stable:
                st["unstable_since"] = None
            elif st["unstable_since"] is None:
                st["unstable_since"] = now
            waited = 0.0 if result.is_stable else now - st["unstable_since"]
            st["result"] = result
            return result, waited

    def keep_waiting(self, key: tuple) -> None:
        """The user chose Keep Waiting: the 60 seconds start again."""
        with self._lock:
            st = self._keys.get(key)
            if st and st["unstable_since"] is not None:
                st["unstable_since"] = self._clock()

    def latest(self, key: tuple) -> tuple[CalendarQuote | None, StabilityResult | None]:
        """The last valid quote and the last stability result for a key (None, None if never seen)."""
        with self._lock:
            st = self._keys.get(key)
            return (st["last_quote"], st.get("result")) if st else (None, None)
