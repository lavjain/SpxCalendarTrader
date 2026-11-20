"""Command line for the core services. Run: uv run --env-file .env python -m cli candidates"""
import argparse
import sys

from app.core import config, services
from app.core.models import FinderResult
from app.core.schwab_api import SchwabError

COLS = ("{:>7}{:>5}{:>8}{:>9}{:>8}{:>9}{:>9}{:>7}{:>7}{:>7}{:>7}{:>8}")


def format_finder(result: FinderResult) -> str:
    out = [f"SPX {result.spx:,.2f}   {result.time}   filters: {result.filters}"]
    if not result.pairs:
        out.append("no expiry pairs for these filters")
    for p in result.pairs:
        out.append(f"\n{p.short_expiry} -> {p.long_expiry}   short {p.short_dte} DTE, long {p.long_dte} DTE, "
                   f"width {p.width}d   {p.strike_count} strikes")
        if not p.rows:
            out.append("  (no 35-45 delta strikes on the selected spacing)")
            continue
        out.append(COLS.format("strike", "ctr", "price", "margin", "delta", "theta", "vega",
                               "sIV", "lIV", "skew", "T/D", "Th/Mgn") + "   ")
        for r in p.rows:
            tag = ("*40D " if r.is_near_40_delta else "") + ("BEST-SKEW" if r.is_best_skew else "")
            out.append(COLS.format(f"{r.strike:.0f}", r.contracts, f"{r.price:.2f}", f"{r.margin:,.0f}",
                                   f"{r.delta:.2f}", f"{r.theta:,.0f}", f"{r.vega:,.0f}",
                                   f"{r.short_iv:.2f}", f"{r.long_iv:.2f}", f"{r.skew:.2f}",
                                   f"{r.td:.0f}", f"{r.theta_margin:.4f}") + f"   {tag}")
        n = p.near_40_delta
        if n and p.break_evens:
            be = p.break_evens
            out.append(f"  ~40D strike {n.strike:.0f}: break-evens at {be.at_date} "
                       f"{be.lower:,.0f} / {be.upper:,.0f}  "
                       f"({(be.lower - n.strike) / n.strike:+.1%} / {(be.upper - n.strike) / n.strike:+.1%})")
        elif n:
            out.append(f"  ~40D strike {n.strike:.0f}: break-evens unavailable (no put-call parity forward)")
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(prog="cli", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates", help="today's 35-45 delta SPX put calendars")
    c.add_argument("--dte-min", type=int, default=config.SHORT_DTE_DEFAULT[0])
    c.add_argument("--dte-max", type=int, default=config.SHORT_DTE_DEFAULT[1])
    c.add_argument("--widths", type=int, nargs="+", default=list(config.WIDTHS_DEFAULT))
    c.add_argument("--strike-sets", nargs="+", default=list(config.STRIKE_SETS), choices=config.STRIKE_SETS)
    c.add_argument("--size-mode", choices=config.SIZE_MODES, default="margin")
    c.add_argument("--size-value", type=float, default=config.MARGIN)
    args = p.parse_args(argv)
    try:
        result = services.get_finder((args.dte_min, args.dte_max), tuple(args.widths),
                                     tuple(args.strike_sets), args.size_mode, args.size_value)
    except (SchwabError, ValueError) as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    print(format_finder(result))


if __name__ == "__main__":
    main()
