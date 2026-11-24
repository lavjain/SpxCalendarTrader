"""Pydantic models for service inputs and outputs (week 1: the Finder).

Numbers are plain float/int (never numpy), dates are ISO strings, so every model
round-trips through JSON unchanged.
"""
from typing import Literal

from pydantic import BaseModel


class OptionQuote(BaseModel):
    expiry: str                      # ISO date
    strike: float
    right: Literal["P", "C"] = "P"   # puts for the calendar, a few calls for the forward
    symbol: str | None = None        # Schwab's option symbol, e.g. "SPXW  261224P07140000" (to re-quote one leg)
    bid: float | None = None         # a missing quote is None, never 0
    ask: float | None = None
    mark: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    iv: float | None = None          # vol points (e.g. 15.2)


class ExpiryPair(BaseModel):
    short: str                       # ISO date
    long: str                        # ISO date
    short_dte: int
    long_dte: int
    width: int                       # nominal days, counted from the Friday


class BreakEvens(BaseModel):
    lower: float
    upper: float
    at_date: str                     # ISO date the P/L curve was evaluated on


class CalendarRow(BaseModel):
    strike: float
    width: int
    short: OptionQuote
    long: OptionQuote
    contracts: int
    price: float                     # calendar debit per share
    bid: float | None = None         # the calendar's bid per share: long bid - short ask
    ask: float | None = None         # long ask - short bid
    margin: float
    delta: float
    gamma: float
    theta: float
    vega: float
    short_iv: float
    long_iv: float
    short_vega: float
    long_vega: float
    short_iv_implied: float | None = None   # IV that reproduces the leg's mid with our Black-Scholes;
    long_iv_implied: float | None = None    # P/L and break-evens use it (Schwab's IV doesn't match its marks)
    skew: float                      # short IV - long IV, vol points
    td: float | None = None          # None when the position delta is near zero
    theta_margin: float
    iv_ratio: float | None = None    # short IV / long IV
    break_evens: BreakEvens | None = None   # at the short expiry, for this strike
    long_forward: float | None = None   # put-call-parity forward of the long expiry: the risk profile reprices from it
    is_best_skew: bool = False
    is_near_target_delta: bool = False


class PairSummary(BaseModel):
    short_expiry: str
    long_expiry: str
    short_dte: int
    long_dte: int
    width: int
    near_target_delta: CalendarRow | None = None
    best_skew: float | None = None
    best_skew_strike: float | None = None
    break_evens: BreakEvens | None = None   # of the target-delta row, None if no forward could be built
    strike_count: int = 0
    rows: list[CalendarRow] = []


class FinderResult(BaseModel):
    time: str                        # ISO timestamp, market time
    spx: float
    filters: dict
    pairs: list[PairSummary]


class Spot(BaseModel):
    time: str                        # ISO timestamp, market time
    spx: float | None = None
    vix: float | None = None
    vix9d: float | None = None


class HolidayNote(BaseModel):
    date: str                        # ISO date of the market holiday
    name: str
    moves_to: str                    # the trading day an expiry on that date moves to


class ExpirationsResult(BaseModel):
    pairs: list[ExpiryPair]          # for the requested widths
    unavailable_widths: list[int]    # widths (of all 3-7) with no pair this week in the DTE range
    holidays: list[HolidayNote] = []   # holidays that move a short or long expiry for pairs in this range


class CalendarQuote(BaseModel):
    """The calendar as one instrument, from both legs' quotes: you buy it at the ask and sell it at the bid."""
    bid: float | None = None         # long bid - short ask
    ask: float | None = None         # long ask - short bid
    mid: float | None = None
    spread: float | None = None      # ask - bid
    leg_spread_pct: float | None = None   # the wider leg's bid-ask as a fraction of that leg's own mid


class StabilityResult(BaseModel):
    is_stable: bool
    waiting_reason: str | None = None
    quotes_seen: int = 0             # valid quotes in a row, newest last
    range_low: float | None = None   # lowest and highest mid over the window checked
    range_high: float | None = None


class Trade(BaseModel):
    """One paper trade, as saved in the `trades` table. Market quote and fill are separate fields and are
    never overwritten by one another (Fill rules). Timestamps are ISO strings in market time (ET)."""
    id: int | None = None
    account: str = "Paper"
    status: Literal["open", "closed"] = "open"
    # the open side
    opened_at: str
    short_expiry: str
    long_expiry: str
    strike: float
    width: int
    short_dte: int
    contracts: int
    size_mode: Literal["margin", "contracts"]
    size_value: float
    # market quote at confirm
    open_bid: float | None = None
    open_ask: float | None = None
    open_mid: float | None = None
    open_range_low: float | None = None
    open_range_high: float | None = None
    # price
    open_suggested: float | None = None
    open_fill: float
    open_price_source: Literal["auto", "manual", "pasted"]
    # entry snapshot
    entry_spx: float | None = None
    entry_vix: float | None = None
    entry_vix9d: float | None = None
    entry_short_iv: float | None = None
    entry_long_iv: float | None = None
    entry_skew: float | None = None
    entry_break_lower: float | None = None
    entry_break_upper: float | None = None
    entry_vol_pnl: float | None = None            # None until a previous-close log exists
    entry_snapshot_source: Literal["refresh", "fresh quote"] | None = None
    notes: str = ""
    closed_at: str | None = None                  # the rest of the close side arrives with Close Trade


class QuoteSpread(BaseModel):
    """One re-quote of the calendar for the Open Trade dialog (the dialog only displays these fields)."""
    time: str                        # ISO, market time
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    spread: float | None = None
    suggested_price: float | None = None     # mid + FILL_OFFSET on the tick grid
    is_stable: bool = False
    waiting_reason: str | None = None
    quotes_seen: int = 0
    seconds_waiting: float = 0.0
    stability_required: bool = False   # the dialog only waits for a stable price when this is True
    give_up: bool = False            # unstable for WAIT_TIMEOUT_S: the dialog asks Keep Waiting / Cancel
    range_low: float | None = None
    range_high: float | None = None
    contracts: int | None = None     # for the requested size, at the mid
    cost: float | None = None        # contracts x fill price x 100 (fill = the typed price, else the suggestion)
    margin: float | None = None      # contracts x mid x 100
    target_price: float | None = None   # the calendar price that is +FLAG_TARGET above the fill
    flag_price: float | None = None     # ...and the price that is FLAG_LOSS below it (the position gets flagged there)


class OpenTradeResult(BaseModel):
    trade: Trade
    warnings: list[str] = []         # e.g. a fill outside the bid-ask: allowed, but said out loud


class TosOrder(BaseModel):
    """A thinkorswim calendar order line, read into fields."""
    side: Literal["BUY", "SELL"]
    contracts: int
    short_expiry: str                # ISO date
    long_expiry: str
    strike: float
    price: float


class ComparisonRow(BaseModel):
    """The target-delta calendar of one short expiry, for one contract (the Weekly Comparison)."""
    target_dte: int                  # the DTE asked for; short_dte is the nearest Friday that exists
    short_expiry: str
    long_expiry: str
    short_dte: int
    long_dte: int
    strike: float
    bid: float | None                # the calendar's bid per share: long bid - short ask
    ask: float | None                # long ask - short bid
    delta: float                     # position greeks for one contract
    gamma: float
    theta: float
    vega: float
    short_iv: float                  # percent, the IVs the row was priced with
    long_iv: float
    skew: float                      # short IV - long IV, in points


class ComparisonResult(BaseModel):
    time: str
    spx: float
    width: int
    strike: float | None = None      # the one strike every row uses
    rows: list[ComparisonRow]


class RiskProfile(BaseModel):
    """P/L of the calendar over SPX, for the whole position (dollars). Plain lists of floats for the canvas."""
    spot: float
    as_of: str
    short_expiry: str
    contracts: int
    spx: list[float]
    today: list[float]               # P/L if SPX moved there today (each leg's IV held fixed)
    at_expiry: list[float]           # P/L at the short expiry
    sd_low: float                    # +-1 standard deviation to the short expiry, from the short leg's IV
    sd_high: float
    break_evens: BreakEvens | None = None
    cost: float                      # debit paid, including the fill offset
    max_profit: float
    max_loss: float                  # = -cost
    pl_now: float                    # P/L at today's SPX: about minus the fill offset, because mid is the fair price
    delta: float
    theta: float
    vega: float
