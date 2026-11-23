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
    is_best_skew: bool = False
    is_near_40_delta: bool = False


class PairSummary(BaseModel):
    short_expiry: str
    long_expiry: str
    short_dte: int
    long_dte: int
    width: int
    near_40_delta: CalendarRow | None = None
    best_skew: float | None = None
    best_skew_strike: float | None = None
    break_evens: BreakEvens | None = None   # of the ~40-delta row, None if no forward could be built
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


class ExpirationsResult(BaseModel):
    pairs: list[ExpiryPair]          # for the requested widths
    unavailable_widths: list[int]    # widths (of all 3-7) with no pair this week in the DTE range


class CalendarQuote(BaseModel):
    """The calendar as one instrument, from both legs' quotes: you buy it at the ask and sell it at the bid."""
    bid: float | None = None         # long bid - short ask
    ask: float | None = None         # long ask - short bid
    mid: float | None = None
    spread: float | None = None      # ask - bid


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
