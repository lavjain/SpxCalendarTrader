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
                                   ("-" if r.td is None else f"{r.td:.0f}"), f"{r.theta_margin:.4f}") + f"   {tag}")
        n = p.near_40_delta
        if n and p.break_evens:
            be = p.break_evens
            out.append(f"  ~40D strike {n.strike:.0f}: break-evens at {be.at_date} "
                       f"{be.lower:,.0f} / {be.upper:,.0f}  "
                       f"({(be.lower - n.strike) / n.strike:+.1%} / {(be.upper - n.strike) / n.strike:+.1%})")
        elif n:
            out.append(f"  ~40D strike {n.strike:.0f}: break-evens unavailable (no put-call parity forward)")
    return "\n".join(out)


def format_diagnosis(d: dict) -> str:
    out = [f"SPX {d['spx']:,.2f}   pair {d['pair']}   strike {d['strike']:.0f}   calendar mid {d['price']:.2f}",
           f"parity forwards: short {d['forward_short']:,.2f}  long {d['forward_long']:,.2f}   "
           f"implied carry (r - q) {d['carry_per_year']:+.2%} per year", ""]
    out.append(f"{'leg':>6}{'expiry':>12}{'days':>5}{'bid':>8}{'ask':>8}{'mid':>8}{'schwab IV':>11}"
               f"{'model@IV':>10}{'IV from mid':>12}")
    for l in d["legs"]:
        iv = l["implied_iv_from_mid"]
        out.append(f"{l['leg']:>6}{l['expiry']:>12}{l['t_days']:>5}{l['bid']:>8.2f}{l['ask']:>8.2f}{l['mid']:>8.2f}"
                   f"{l['schwab_iv']:>11.2f}{l['model_at_schwab_iv']:>10.2f}{(iv if iv else float('nan')):>12.2f}")
    out.append("\nbreak-evens at the short expiry (distance from the strike in points):")
    k = d["strike"]
    for name, b in d["variants"].items():
        if not b:
            out.append(f"  {name:<28} none")
            continue
        line = f"  {name:<28} {b[0]:>8,.0f} / {b[1]:>8,.0f}   ({b[0] - k:+.0f} / {b[1] - k:+.0f})"
        if d.get("tos"):
            lo, hi = d["tos"]
            line += f"   vs tos: {((k - b[0]) / (k - lo) - 1):+.1%} / {((b[1] - k) / (hi - k) - 1):+.1%}"
        out.append(line)
    return "\n".join(out)


EXAMPLES = """\
examples:
  uv run --env-file .env python -m cli candidates
  uv run --env-file .env python -m cli candidates --dte-min 20 --dte-max 40 --widths 5 7
  uv run --env-file .env python -m cli candidates --size-mode contracts --size-value 2
  uv run --env-file .env python -m cli diagnose --tos 6871.92 7415.05

Defaults come from app/core/config.py. Run `... candidates --help` or `... diagnose --help` for each command."""


class _Fmt(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """Shows each option's default in --help and keeps the examples' line breaks."""


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="python -m cli", formatter_class=_Fmt, epilog=EXAMPLES,
        description="SPX calendar finder from the terminal. Needs a Schwab login (weekly) and keys in .env.")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="{candidates,diagnose}")
    c = sub.add_parser("candidates", formatter_class=_Fmt, epilog=EXAMPLES,
                       help="print today's 35-45 delta SPX put calendars, one table per expiry pair",
                       description="Pull the SPX chain and print every 35-45 delta put calendar for each short/long "
                                   "expiry pair, with the ~40 delta strike (*40D), the best skew (BEST-SKEW) and break-evens.")
    c.add_argument("--dte-min", type=int, default=config.SHORT_DTE_DEFAULT[0], help="shortest short-leg DTE")
    c.add_argument("--dte-max", type=int, default=config.SHORT_DTE_DEFAULT[1], help="longest short-leg DTE")
    c.add_argument("--widths", type=int, nargs="+", default=list(config.WIDTHS_DEFAULT), metavar="DAYS",
                   help=f"days between short and long expiry, any of {list(config.WIDTHS)}")
    c.add_argument("--strike-sets", nargs="+", default=list(config.STRIKE_SETS), choices=config.STRIKE_SETS,
                   metavar="SET", help="strike spacing: 10 = 10s plus 25/75, 25 = 25s")
    c.add_argument("--size-mode", choices=config.SIZE_MODES, default="margin",
                   help="margin: contracts = target margin / debit, rounded to the nearest whole contract; "
                        "contracts: a fixed number of contracts")
    c.add_argument("--size-value", type=float, default=config.MARGIN,
                   help="target margin in dollars (margin mode) or number of contracts (contracts mode)")
    d = sub.add_parser("diagnose", formatter_class=_Fmt, epilog=EXAMPLES,
                       help="show the inputs behind one calendar's break-evens (vs thinkorswim)",
                       description="Print the numbers behind a calendar's break-evens, and compare them with the "
                                   "break-evens thinkorswim shows in Analyze.")
    d.add_argument("--pair", type=int, default=None, help="pair number, 0 = first (default: nearest 30 DTE)")
    d.add_argument("--tos", type=float, nargs=2, metavar=("LOWER", "UPPER"),
                   help="thinkorswim break-evens at the short expiry")
    args = p.parse_args(argv)
    if args.cmd == "diagnose":
        try:
            print(format_diagnosis(services.diagnose_finder(pair_index=args.pair, tos=args.tos)))
        except (SchwabError, ValueError) as e:
            print(e, file=sys.stderr)
            sys.exit(1)
        return
    try:
        result = services.get_finder((args.dte_min, args.dte_max), tuple(args.widths),
                                     tuple(args.strike_sets), args.size_mode, args.size_value)
    except (SchwabError, ValueError) as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    print(format_finder(result))


if __name__ == "__main__":
    main()
