"""thinkorswim order lines: write one (Copy to TOS) and read one (Paste from TOS). Plain Python, no web imports.

Format, as thinkorswim writes it (the later expiry first):
    BUY +13 CALENDAR SPX 100 (Weeklys) 19 FEB 27/12 FEB 27 6800 PUT @7.70 LMT
    SELL -13 CALENDAR SPX 100 (Weeklys) 12 FEB 27/5 FEB 27 6735 PUT @8.70 LMT
"""
import re
from datetime import date

from app.core import config
from app.core.models import TosOrder

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
_DATE = r"\d{1,2} [A-Z]{3} \d{2}"


class TosParseError(ValueError):
    """The line could not be read; the message says which part."""


def _fmt_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year % 100:02d}"


def _read_date(text: str) -> str:
    day, mon, yy = text.split()
    if mon not in MONTHS:
        raise TosParseError(f"Could not read the expiry '{text}'")
    try:
        return date(2000 + int(yy), MONTHS.index(mon) + 1, int(day)).isoformat()
    except ValueError:
        raise TosParseError(f"Could not read the expiry '{text}'")


def format_order(side: str, contracts: int, short_expiry: str, long_expiry: str, strike: float, price: float) -> str:
    """The order line for a SPX put calendar: buy (open) or sell (close) the long, sell or buy the short."""
    if side not in ("BUY", "SELL"):
        raise ValueError("Side must be BUY or SELL")
    sign = "+" if side == "BUY" else "-"
    return (f"{side} {sign}{contracts} CALENDAR SPX 100 (Weeklys) {_fmt_date(long_expiry)}/{_fmt_date(short_expiry)} "
            f"{strike:g} PUT @{price:.2f} LMT")


def parse_order(text: str) -> TosOrder:
    """Read one order line. Raises TosParseError with a message naming what is wrong."""
    lines = [" ".join(l.upper().split()) for l in (text or "").splitlines() if l.strip()]
    lines = [l for l in lines if "CALENDAR" in l] or lines
    if not lines:
        raise TosParseError("There is nothing to read: paste the order line from thinkorswim")
    if len(lines) > 1:
        raise TosParseError("Paste one order line at a time")
    line = lines[0]
    m = re.match(r"(BUY|SELL)\b", line)
    if not m:
        raise TosParseError("Could not read BUY or SELL at the start of the line")
    side, rest = m.group(1), line[m.end():].strip()
    m = re.match(r"([+-]?\d+)\b", rest)
    if not m:
        raise TosParseError("Could not read the quantity")
    contracts, rest = abs(int(m.group(1))), rest[m.end():].strip()
    if contracts < 1:
        raise TosParseError("The quantity must be at least 1")
    if not rest.startswith("CALENDAR"):
        raise TosParseError("This is not a calendar order (no CALENDAR)")
    rest = rest[len("CALENDAR"):].strip()
    m = re.match(r"SPX\s+100\s*(\(([A-Z]+)\))?\s*", rest)
    if not m:
        raise TosParseError("Could not read SPX 100: only SPX calendars are supported")
    if m.group(2) != "WEEKLYS":
        raise TosParseError("Only SPXW (Weeklys) expiries are supported")
    rest = rest[m.end():]
    dates = re.match(rf"({_DATE})\s*/\s*({_DATE})\s*", rest)
    if not dates:
        raise TosParseError("Could not read both expiries")
    a, b = _read_date(dates.group(1)), _read_date(dates.group(2))
    short, long_ = sorted([a, b])
    if short == long_:
        raise TosParseError("The two expiries are the same day")
    width = (date.fromisoformat(long_) - date.fromisoformat(short)).days
    if width not in config.WIDTHS:
        raise TosParseError(f"A {width}-day width is outside {config.WIDTHS[0]}-{config.WIDTHS[-1]} days")
    rest = rest[dates.end():]
    m = re.match(r"(\d+(?:\.\d+)?)\s+(PUT|CALL)\b\s*", rest)
    if not m:
        raise TosParseError("Could not read the strike")
    if m.group(2) != "PUT":
        raise TosParseError("Put calendars only for now")
    strike, rest = float(m.group(1)), rest[m.end():]
    m = re.match(r"@\s*(\d+(?:\.\d+)?)\s*(LMT)?\s*", rest)
    if not m:
        raise TosParseError("Could not read the price")
    price, rest = float(m.group(1)), rest[m.end():]
    if rest.strip():
        raise TosParseError(f"Unexpected text after the price: {rest.strip()[:30]}")
    if price <= 0:
        raise TosParseError("The price must be above zero")
    return TosOrder(side=side, contracts=contracts, short_expiry=short, long_expiry=long_, strike=strike, price=price)
