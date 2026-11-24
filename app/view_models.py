"""What the Finder templates show, worked out from a stored snapshot. Display plumbing only:
every number and flag comes from the services (get_finder); this only groups, sorts and selects rows."""
from app.core import config
from app.core.models import CalendarRow, PairSummary
from app.schemas import FinderSnapshot

SORTS = {                       # key -> (value of a pair, descending by default)
    "date": (lambda p: (p.short_expiry, p.long_expiry), False),
    "strike": (lambda p: p.near_target_delta.strike if p.near_target_delta else None, False),
    "contracts": (lambda p: p.near_target_delta.contracts if p.near_target_delta else None, True),
    "price": (lambda p: p.near_target_delta.price if p.near_target_delta else None, False),
    "theta": (lambda p: p.near_target_delta.theta if p.near_target_delta else None, True),
    "vega": (lambda p: p.near_target_delta.vega if p.near_target_delta else None, True),
    "skew": (lambda p: p.near_target_delta.skew if p.near_target_delta else None, True),
    "theta_margin": (lambda p: p.near_target_delta.theta_margin if p.near_target_delta else None, True),
    "best_skew": (lambda p: p.best_skew, True),
}


def pair_key(p: PairSummary) -> str:
    return f"{p.short_expiry}|{p.long_expiry}"


def parse_sort(sort: str | None) -> tuple[str, bool]:
    """'skew' -> sort by skew in its natural direction; '-skew' / '+skew' flips it."""
    sort = sort or "date"
    flip = sort[:1] in "+-"
    name = sort.lstrip("+-")
    if name not in SORTS:
        name, flip = "date", False
    desc = SORTS[name][1]
    if sort.startswith("-"):
        desc = True
    elif sort.startswith("+"):
        desc = False
    return name, desc


def segments(snap: FinderSnapshot, sort: str | None = None) -> list[dict]:
    """One segment per width, narrowest first; pairs sorted within each segment (missing values last)."""
    name, desc = parse_sort(sort)
    key = SORTS[name][0]
    out = []
    for width in sorted({p.width for p in snap.result.pairs}):
        pairs = [p for p in snap.result.pairs if p.width == width]
        have = sorted([p for p in pairs if key(p) is not None], key=key, reverse=desc)
        out.append({"width": width, "pairs": have + [p for p in pairs if key(p) is None]})
    return out


def best_skew_key(snap: FinderSnapshot) -> str | None:
    """The pair with the highest best-skew across the whole table (amber edge)."""
    ranked = [p for p in snap.result.pairs if p.best_skew is not None]
    return pair_key(max(ranked, key=lambda p: p.best_skew)) if ranked else None


def default_pair(snap: FinderSnapshot) -> PairSummary | None:
    """The pair holding the default trade: default width, short nearest 30 DTE."""
    have = [p for p in snap.result.pairs if p.near_target_delta]
    narrowed = [p for p in have if p.width == config.WIDTHS_DEFAULT[0]] or have
    return min(narrowed, key=lambda p: (abs(p.short_dte - config.SHORT_DTE_TARGET), p.short_expiry),
               default=None)


def find_pair(snap: FinderSnapshot, short: str, long: str) -> PairSummary | None:
    return next((p for p in snap.result.pairs if p.short_expiry == short and p.long_expiry == long), None)


def find_row(pair: PairSummary | None, strike: float | None) -> CalendarRow | None:
    if pair is None:
        return None
    if strike is None:
        return pair.near_target_delta
    return next((r for r in pair.rows if r.strike == strike), None)


def status_strip(snap: FinderSnapshot) -> dict:
    res = snap.result
    shorts = []
    for p in res.pairs:
        if not any(s["expiry"] == p.short_expiry for s in shorts):
            shorts.append({"expiry": p.short_expiry, "dte": p.short_dte})
    spot = snap.spot
    return {"time": res.time, "spx": (spot.spx if spot and spot.spx else res.spx) or None,
            "vix": spot.vix if spot else None, "shorts": shorts, "filters": res.filters}


COLLAPSED = "-"      # open="-": no pair open in the table (clicking the open pair again)


def results_context(snap: FinderSnapshot, sort: str | None = None, open_key: str | None = None,
                    strike: float | None = None, panel_key: str | None = None) -> dict:
    """Everything _results.html / _calendars_table.html need. With no selection given, the default pair is
    open with its target-delta strike selected. open_key COLLAPSED shows the table with no pair open; the panel
    then keeps `panel_key` (the calendar it was showing) or the default."""
    collapsed = open_key == COLLAPSED
    open_pair = None
    if open_key and not collapsed:
        open_pair = find_pair(snap, *open_key.partition("|")[::2])
    if collapsed:
        shown = find_pair(snap, *panel_key.partition("|")[::2]) if panel_key else None
        if shown is None:
            shown, strike = default_pair(snap), None
    else:
        if open_pair is None:
            open_pair = default_pair(snap)
            if open_key:
                strike = None          # the pair is gone (a new pull): the old strike belongs to it
        shown = open_pair
    row = find_row(shown, strike)
    sort_name, sort_desc = parse_sort(sort)
    return {"snapshot_id": snap.snapshot_id, "strip": status_strip(snap), "segments": segments(snap, sort),
            "sort": sort or "date", "sort_name": sort_name, "sort_desc": sort_desc, "best_key": best_skew_key(snap),
            "open_pair": open_pair, "open_key": pair_key(open_pair) if open_pair else None, "row": row,
            "selected_strike": row.strike if row else None, "pair": shown, "fill_offset": config.FILL_OFFSET,
            **_size(snap),
            "has_pairs": bool(snap.result.pairs)}


def _size(snap: FinderSnapshot) -> dict:
    """The Size By setting this snapshot was made with: the dialog sizes the trade the same way."""
    f = snap.result.filters or {}
    return {"size_mode": f.get("size_mode", "margin"), "size_value": f.get("size_value", config.MARGIN)}


def panel_context(snap: FinderSnapshot, short: str, long: str, strike: float | None) -> dict:
    pair = find_pair(snap, short, long)
    row = find_row(pair, strike)
    cost = row.contracts * (row.price + config.FILL_OFFSET) * 100 if row else None
    return {"snapshot_id": snap.snapshot_id, "pair": pair, "row": row, "cost": cost,
            "fill_offset": config.FILL_OFFSET, **_size(snap)}
