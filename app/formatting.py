"""Display formatting, shared by Jinja (the filters in pages.py) and static/js/lib/format.js.

Services return raw numbers (12.85); only the edge formats them. Both implementations are checked
against the same examples in tests/format_cases.json. Rules: None -> "—"; a value that rounds to zero
never shows a minus sign; thousands separators; avoid exact binary ties (0.125) in examples.
"""
from datetime import date

DASH = "—"


def _body(x: float, digits: int) -> tuple[str, bool]:
    s = f"{abs(x):,.{digits}f}"
    return s, any(c in "123456789" for c in s)


def num(x, digits: int = 0) -> str:
    """1234.5 -> '1,235' (digits=0), '1,234.50' (digits=2)."""
    if x is None:
        return DASH
    s, nonzero = _body(x, digits)
    return ("-" if x < 0 and nonzero else "") + s


def money(x, digits: int = 2) -> str:
    """12.85 -> '$12.85'; -3 -> '-$3.00'; money(10240, 0) -> '$10,240'."""
    if x is None:
        return DASH
    s, nonzero = _body(x, digits)
    return ("-" if x < 0 and nonzero else "") + "$" + s


def pct(x, digits: int = 1) -> str:
    """A fraction as a percent: 0.0321 -> '3.2%'; -0.1 with digits=0 -> '-10%'."""
    if x is None:
        return DASH
    s, nonzero = _body(x * 100, digits)
    return ("-" if x < 0 and nonzero else "") + s + "%"


def signed(x, digits: int = 2) -> str:
    """Always shows the sign: 1.2 -> '+1.20'; -0.5 (digits=1) -> '-0.5'; 0 -> '0.00'."""
    if x is None:
        return DASH
    s, nonzero = _body(x, digits)
    if not nonzero:
        return s
    return ("-" if x < 0 else "+") + s


def pts(x, digits: int = 2) -> str:
    """Vol points, plain: 24.4912 -> '24.49'."""
    return DASH if x is None else num(x, digits)


def edate(iso) -> str:
    """'2026-12-24' -> 'Thu Dec 24'."""
    if not iso:
        return DASH
    d = date.fromisoformat(iso[:10])
    return f"{d:%a %b} {d.day}"


def mdate(iso) -> str:
    """'2026-12-25' -> 'Dec 25' (no weekday)."""
    if not iso:
        return DASH
    d = date.fromisoformat(iso[:10])
    return f"{d:%b} {d.day}"


def strike(x) -> str:
    """7120.0 -> '7120' (no separators on strikes)."""
    return DASH if x is None else f"{x:.0f}"


def etime(iso) -> str:
    """'2026-11-23T12:42:39-05:00' -> '12:42:39 PM ET' (timestamps are already in market time)."""
    if not iso:
        return DASH
    h, m, sec = int(iso[11:13]), iso[14:16], iso[17:19]
    return f"{h % 12 or 12}:{m}:{sec} {'AM' if h < 12 else 'PM'} ET"


def gamma(x, digits: int = 3) -> str:
    """Position gamma is tiny: under 0.001 it is shown as a plain '0.00'."""
    if x is None:
        return DASH
    return "0.00" if abs(x) < 0.001 else num(x, digits)
