#!/usr/bin/env python3
"""
calendar_math.py - calendar pricing/sizing math, screener, XSP overlay and fill/skew logger.

Reproduces the Sheridan/Lane Snell spreadsheet metrics exactly:
    Skew        = short-leg IV - long-leg IV   (vol points; want POSITIVE)
    T/D         = position theta / position delta
    Theta/Mgn   = position theta / margin      (margin == debit for a calendar)
    Contracts   = ceil(target_capital / (debit * 100))

Selection order, per the transcript: filter DTE FIRST, then rank. Lane passed on
rows scoring 3-6x better because their short leg was 7 DTE.

Subcommands
    selftest   validate against Lane's 2021-09-17 SPX sheet
    screen     rank calendars from a chain CSV
    overlay    XSP hedge sizing for a chosen core position
    logfill    record a midpoint-limit fill test (the go/no-go measurement)
    report     summarise the fill log and the skew log

Chain CSV format (one row per expiration, ATM strike only):
    dte,mark,delta,gamma,theta,vega,iv
    7,38.20,0.4985,0.0041,-2.8058,2.4851,0.1566
Greeks are PER SHARE. iv as a decimal (0.1566) or percent (15.66) - both accepted.
"""

import argparse, csv, math, os, sys
from datetime import date, datetime

# Logs go in data/ (gitignored). Override with CALENDAR_DATA_DIR.
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (file lives in app/core/)
LOG_DIR = os.environ.get("CALENDAR_DATA_DIR", os.path.join(_REPO, "data"))
SKEW_LOG = os.path.join(LOG_DIR, "skew_log.csv")
FILL_LOG = os.path.join(LOG_DIR, "fill_log.csv")

# ---------------------------------------------------------------- structures

class Leg:
    __slots__ = ("dte", "mark", "delta", "gamma", "theta", "vega", "iv", "label")

    def __init__(self, dte, mark, delta, gamma, theta, vega, iv, label=""):
        self.dte = int(dte)
        self.mark = float(mark)
        self.delta = float(delta)
        self.gamma = float(gamma)
        self.theta = float(theta)
        self.vega = float(vega)
        iv = float(iv)
        self.iv = iv / 100.0 if iv > 1.5 else iv   # accept 15.66 or 0.1566
        self.label = label or f"{self.dte}d"


class Calendar:
    """Short the near leg, long the far leg. All position greeks are per-contract
    (x100) then scaled by contract count, matching the source spreadsheet."""

    def __init__(self, short: Leg, long: Leg, capital: float):
        self.s, self.l = short, long
        self.debit = long.mark - short.mark
        self.width = long.dte - short.dte
        if self.debit <= 0:
            self.contracts = 0
        else:
            self.contracts = math.ceil(capital / (self.debit * 100.0))
        k = self.contracts * 100.0
        self.margin = self.debit * k
        self.delta = (long.delta - short.delta) * k
        self.gamma = (long.gamma - short.gamma) * k
        self.theta = (long.theta - short.theta) * k
        self.vega = (long.vega - short.vega) * k
        self.skew = (short.iv - long.iv) * 100.0          # vol points
        self.td = self.theta / self.delta if self.delta else float("nan")
        self.theta_margin = self.theta / self.margin if self.margin else float("nan")
        # front vega is the divergence exposure: $ lost per vol pt of front-vs-back
        self.front_vega = short.vega * k
        self.div_cost = self.front_vega / self.margin if self.margin else float("nan")

    @property
    def name(self):
        return f"{self.s.label}/{self.l.label}"


# ---------------------------------------------------------------- screening

def build(legs, capital, width=None):
    out = []
    for i, s in enumerate(legs):
        for l in legs[i + 1:]:
            if width is not None and (l.dte - s.dte) != width:
                continue
            c = Calendar(s, l, capital)
            if c.contracts > 0:
                out.append(c)
    return out


def screen(legs, capital, dte_lo, dte_hi, width, min_skew, rank_by):
    allc = build(legs, capital, width)
    passing = [c for c in allc
               if dte_lo <= c.s.dte <= dte_hi and c.skew >= min_skew]
    key = {"skew": lambda c: c.skew,
           "td": lambda c: c.td,
           "theta": lambda c: c.theta_margin}[rank_by]
    passing.sort(key=key, reverse=True)
    return allc, passing


def fmt_table(rows, title, note=""):
    if not rows:
        return f"\n{title}\n" + "-" * 96 + "\n  (none)\n"
    h = (f"{'calendar':>14}{'sDTE':>6}{'lDTE':>6}{'wid':>5}{'ctr':>5}"
         f"{'debit':>8}{'margin':>9}{'delta':>8}{'gamma':>8}"
         f"{'theta':>9}{'vega':>9}{'SKEW':>7}{'T/D':>7}{'Th/Mgn':>8}{'divCost':>9}")
    out = [f"\n{title}", "-" * 96, h, "-" * 96]
    for c in rows:
        out.append(f"{c.name:>14}{c.s.dte:>6}{c.l.dte:>6}{c.width:>5}{c.contracts:>5}"
                   f"{c.debit:>8.2f}{c.margin:>9,.0f}{c.delta:>8.2f}{c.gamma:>8.2f}"
                   f"{c.theta:>9,.2f}{c.vega:>9,.2f}{c.skew:>7.2f}{c.td:>7.0f}"
                   f"{c.theta_margin:>8.3f}{c.div_cost:>8.0%}")
    if note:
        out.append(note)
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- overlay

SPX_TO_MINI = 10.0   # XSP is exactly 1/10 SPX notional

def overlay(core_contracts, levels=(0.10, 0.15, 0.20, 0.33),
            mini_fee=0.90, mini_spread=0.06, margin=None):
    """XSP contracts needed to adjust a given % of an SPX core position.
    1 XSP == 0.1 SPX, so one XSP lot moves 10%/core_contracts of the position."""
    unit = 100.0 / (SPX_TO_MINI * core_contracts)   # % of position per XSP lot
    rows = []
    for pct in levels:
        n = max(1, round(pct * SPX_TO_MINI * core_contracts))
        actual = n * unit
        comm = mini_fee * 2 * n                     # a vertical = 2 legs
        slip = mini_spread * 100 * n * 0.5          # cross half the spread
        rows.append((pct, n, actual, comm, slip, comm + slip))
    return unit, rows


def print_overlay(core_contracts, margin, **kw):
    unit, rows = overlay(core_contracts, margin=margin, **kw)
    print(f"\nXSP ADJUSTMENT OVERLAY for a {core_contracts}-lot SPX core"
          f" (${margin:,.0f})")
    print("-" * 78)
    print(f"  1 XSP contract = {unit:.2f}% of the position"
          f"   |   Lane's band is 10-15% per adjustment")
    print(f"  SPX-only alternative: 1 of {core_contracts} = "
          f"{100/core_contracts:.1f}% (too coarse)\n")
    print(f"{'target':>8}{'XSP lots':>10}{'actual':>9}{'comm':>8}{'slip':>8}"
          f"{'total':>8}{'% of pos':>10}")
    for pct, n, actual, comm, slip, tot in rows:
        print(f"{pct:>7.0%}{n:>10}{actual:>8.1f}%{comm:>8.2f}{slip:>8.2f}"
              f"{tot:>8.2f}{tot/margin:>9.2%}")
    print("\n  Downside: sell an XSP call credit spread. Upside: buy an XSP call")
    print("  vertical. XSP is European and Section 1256 - no assignment, and no")
    print("  mixed-straddle problem against an SPX core.")


# ---------------------------------------------------------------- logging

def ensure_log(path, header):
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(header)


def log_skew(d, best, traded, note=""):
    ensure_log(SKEW_LOG, ["date", "calendar", "short_dte", "long_dte", "debit",
                          "skew", "td", "theta_margin", "div_cost",
                          "traded", "note"])
    with open(SKEW_LOG, "a", newline="") as f:
        w = csv.writer(f)
        if best is None:
            w.writerow([d, "", "", "", "", "", "", "", "", traded, note or "no qualifying row"])
        else:
            w.writerow([d, best.name, best.s.dte, best.l.dte, f"{best.debit:.2f}",
                        f"{best.skew:.2f}", f"{best.td:.0f}",
                        f"{best.theta_margin:.4f}", f"{best.div_cost:.3f}",
                        traded, note])


def log_fill(args):
    ensure_log(FILL_LOG, ["date", "symbol", "structure", "contracts", "bid", "ask",
                          "mid", "limit", "filled", "fill_price", "wait_min",
                          "slip_vs_mid", "slip_pct_of_debit"])
    mid = (args.bid + args.ask) / 2.0
    if args.fill_price is not None:
        slip = args.fill_price - mid
        pct = slip / mid if mid else float("nan")
    else:
        slip, pct = float("nan"), float("nan")
    with open(FILL_LOG, "a", newline="") as f:
        csv.writer(f).writerow([
            args.date or date.today().isoformat(), args.symbol, args.structure,
            args.contracts, f"{args.bid:.2f}", f"{args.ask:.2f}", f"{mid:.2f}",
            f"{args.limit:.2f}" if args.limit is not None else "",
            "Y" if args.fill_price is not None else "N",
            f"{args.fill_price:.2f}" if args.fill_price is not None else "",
            args.wait_min if args.wait_min is not None else "",
            f"{slip:.3f}" if slip == slip else "",
            f"{pct:.4f}" if pct == pct else ""])
    print(f"logged: mid {mid:.2f}"
          + (f", filled {args.fill_price:.2f}, slip {slip:+.3f} "
             f"({pct:+.2%} of debit)" if slip == slip else ", NO FILL"))


def report():
    print("\nFILL-QUALITY TEST  (the go/no-go measurement)")
    print("-" * 72)
    if not os.path.exists(FILL_LOG):
        print("  no fills logged yet")
    else:
        rows = list(csv.DictReader(open(FILL_LOG)))
        by = {}
        for r in rows:
            by.setdefault(r["symbol"], []).append(r)
        for sym, rs in by.items():
            filled = [r for r in rs if r["filled"] == "Y" and r["slip_pct_of_debit"]]
            n = len(rs)
            fr = len(filled) / n if n else 0
            if filled:
                sl = [float(r["slip_pct_of_debit"]) for r in filled]
                avg = sum(sl) / len(sl)
                worst = max(sl)
                print(f"  {sym:>6}: {n:>3} attempts, {fr:5.0%} filled | "
                      f"avg slip {avg:+.2%} of debit, worst {worst:+.2%}")
                rt = 2 * avg
                print(f"          -> round-trip slippage ~{rt:.2%}; "
                      f"{'VIABLE' if rt < 0.025 else 'TOO EXPENSIVE'} "
                      f"against a 12% target")
            else:
                print(f"  {sym:>6}: {n:>3} attempts, none filled")
    print("\nSKEW LOG")
    print("-" * 72)
    if not os.path.exists(SKEW_LOG):
        print("  no skew observations yet")
        return
    rows = [r for r in csv.DictReader(open(SKEW_LOG)) if r["skew"]]
    if not rows:
        print("  no qualifying rows observed yet")
        return
    sk = [float(r["skew"]) for r in rows]
    pos = sum(1 for s in sk if s >= 0)
    print(f"  {len(rows)} observations | best-row skew: "
          f"min {min(sk):+.2f}, median {sorted(sk)[len(sk)//2]:+.2f}, max {max(sk):+.2f}")
    print(f"  skew >= 0 on {pos}/{len(rows)} days ({pos/len(rows):.0%}) "
          f"-> implies ~{pos/len(rows)*52:.0f} entries/yr at one per week")
    traded = sum(1 for r in rows if r["traded"].upper().startswith("Y"))
    print(f"  traded on {traded} of them")


# ---------------------------------------------------------------- self test

LANE_2021_09_17 = [
    #  dte,  mark,  delta,  gamma,    theta,   vega,     iv%
    (   7, 38.20, 0.4985, 0.0041, -2.8058, 2.4851, 15.66),
    (  14, 51.20, 0.5015, 0.0031, -1.8626, 3.4907, 14.87),
    (  21, 61.80, 0.5034, 0.0025, -1.4930, 4.2653, 14.65),
    (  28, 70.75, 0.5049, 0.0022, -1.2921, 4.8947, 14.60),
    (  35, 81.50, 0.5066, 0.0019, -1.1767, 5.4959, 14.95),
    (  42, 90.95, 0.5079, 0.0017, -1.0930, 6.0173, 15.23),
    (  63,113.45, 0.5110, 0.0014, -0.9105, 7.3487, 15.53),
    (  91,142.30, 0.5146, 0.0011, -0.7884, 8.8304, 16.18),
    ( 126,176.05, 0.5187, 0.0009, -0.7028,10.3870, 17.00),
]

# (short_dte, long_dte, contracts, debit, margin, delta, gamma, theta, vega, skew, td)
LANE_EXPECTED = [
    ( 7, 14, 62, 13.00, 80600, 18.60, -6.20, 5847.84, 6234.72, 0.79, 314),
    ( 7, 21, 34, 23.60, 80240, 16.66, -5.44, 4463.52, 6052.68, 1.01, 268),
    ( 7, 28, 25, 32.55, 81375, 16.00, -4.75, 3784.25, 6024.00, 1.06, 237),
    (14, 21, 76, 10.60, 80560, 14.44, -4.56, 2808.96, 5886.96, 0.22, 195),
    (14, 28, 41, 19.55, 80155, 13.94, -3.69, 2339.05, 5756.40, 0.27, 168),
    (14, 35, 27, 30.30, 81810, 13.77, -3.24, 1851.93, 5414.04, -0.08, 134),
    (21, 28, 90,  8.95, 80550, 13.50, -2.70, 1808.10, 5664.60, 0.05, 134),
    (21, 35, 41, 19.70, 80770, 13.12, -2.46, 1296.83, 5045.46, -0.30,  99),
    (21, 42, 28, 29.15, 81620, 12.60, -2.24, 1120.00, 4905.60, -0.58,  89),
    (28, 35, 75, 10.75, 80625, 12.75, -2.25,  865.50, 4509.00, -0.35,  68),
    (28, 63, 19, 42.70, 81130, 11.59, -1.52,  725.04, 4662.60, -0.93,  63),
    (35, 63, 26, 31.95, 83070, 11.44, -1.30,  692.12, 4817.28, -0.58,  61),
    (35, 91, 14, 60.80, 85120, 11.20, -1.12,  543.62, 4668.30, -1.23,  49),
    (42, 63, 36, 22.50, 81000, 11.16, -1.08,  657.00, 4793.04, -0.30,  59),
    (42, 91, 16, 51.35, 82160, 10.72, -0.96,  487.36, 4500.96, -0.95,  45),
    (42,126, 10, 85.10, 85100, 10.80, -0.80,  390.20, 4369.70, -1.77,  36),
]


def selftest():
    legs = [Leg(*r) for r in LANE_2021_09_17]
    cals = {(c.s.dte, c.l.dte): c for c in build(legs, 80000)}
    print("SELF-TEST vs Lane Snell's SPX sheet, 2021-09-17 09:35, SPX 4438.56, 4440 calls")
    print("-" * 88)
    print(f"{'pair':>10}{'ctr':>7}{'debit':>9}{'margin':>10}{'delta':>9}"
          f"{'theta':>11}{'vega':>11}{'skew':>8}{'T/D':>7}   status")
    fails = 0
    for (sd, ld, ctr, deb, mgn, dl, gm, th, vg, sk, td) in LANE_EXPECTED:
        c = cals.get((sd, ld))
        if c is None:
            print(f"{sd:>4}/{ld:<5} MISSING"); fails += 1; continue
        chk = [abs(c.contracts - ctr) == 0,
               abs(c.debit - deb) < 0.005,
               abs(c.margin - mgn) < 1.0,
               abs(c.delta - dl) < 0.02,
               abs(c.gamma - gm) < 0.02,
               abs(c.theta - th) < 0.05,
               abs(c.vega - vg) < 0.05,
               abs(c.skew - sk) < 0.005,
               abs(c.td - td) < 1.0]
        ok = all(chk)
        fails += (not ok)
        print(f"{sd:>4}/{ld:<5}{c.contracts:>7}{c.debit:>9.2f}{c.margin:>10,.0f}"
              f"{c.delta:>9.2f}{c.theta:>11,.2f}{c.vega:>11,.2f}"
              f"{c.skew:>8.2f}{c.td:>7.0f}   {'OK' if ok else 'MISMATCH ' + str(chk)}")
    print("-" * 88)
    print(f"{len(LANE_EXPECTED) - fails}/{len(LANE_EXPECTED)} rows reproduce exactly."
          if fails == 0 else f"{fails} MISMATCHES")

    print("\nWhat the screener would have said that morning "
          "(short DTE 17-25, width 7, skew >= 0):")
    _, passing = screen(legs, 80000, 17, 25, 7, 0.0, "skew")
    print(fmt_table(passing, "PASSING"))
    _, unfiltered = screen(legs, 80000, 0, 999, 7, 0.0, "skew")
    print(fmt_table(unfiltered[:3], "TOP 3 IF YOU IGNORE THE DTE FILTER",
                    "  ^ Lane rejected these. 7 DTE short leg: gamma -6.20 vs -2.70."))
    print("  Lane's actual pick was 21/28 - the only row that passes the filter.\n")


# ---------------------------------------------------------------- io

def load_chain(path):
    legs = []
    with open(path) as f:
        for row in csv.DictReader(f):
            row = {k.strip().lower(): v for k, v in row.items() if k}
            legs.append(Leg(row["dte"], row["mark"], row["delta"], row["gamma"],
                            row["theta"], row["vega"], row["iv"],
                            row.get("label", "")))
    legs.sort(key=lambda l: l.dte)
    return legs


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("selftest", help="validate against Lane's 2021 sheet")

    sc = sub.add_parser("screen", help="rank calendars from a chain CSV")
    sc.add_argument("chain")
    sc.add_argument("--capital", type=float, default=80000.0)
    sc.add_argument("--dte-lo", type=int, default=17)
    sc.add_argument("--dte-hi", type=int, default=25)
    sc.add_argument("--width", type=int, default=7,
                    help="days between legs; 0 = any")
    sc.add_argument("--min-skew", type=float, default=0.0)
    sc.add_argument("--rank-by", choices=["skew", "td", "theta"], default="skew")
    sc.add_argument("--show-all", action="store_true")
    sc.add_argument("--log", action="store_true", help="append to the skew log")
    sc.add_argument("--traded", default="N")
    sc.add_argument("--note", default="")

    ov = sub.add_parser("overlay", help="XSP hedge sizing for an SPX core")
    ov.add_argument("--contracts", type=int, required=True)
    ov.add_argument("--debit", type=float, required=True,
                    help="SPX calendar debit per contract")
    ov.add_argument("--mini-fee", type=float, default=0.90)
    ov.add_argument("--mini-spread", type=float, default=0.06)

    lf = sub.add_parser("logfill", help="record a midpoint-limit fill test")
    lf.add_argument("--symbol", required=True)
    lf.add_argument("--structure", default="21/28 ATM cal")
    lf.add_argument("--contracts", type=int, required=True)
    lf.add_argument("--bid", type=float, required=True)
    lf.add_argument("--ask", type=float, required=True)
    lf.add_argument("--limit", type=float)
    lf.add_argument("--fill-price", type=float,
                    help="omit if the order did not fill")
    lf.add_argument("--wait-min", type=int)
    lf.add_argument("--date")

    sub.add_parser("report", help="summarise the fill and skew logs")

    a = p.parse_args()

    if a.cmd == "selftest":
        selftest()

    elif a.cmd == "screen":
        legs = load_chain(a.chain)
        width = None if a.width == 0 else a.width
        allc, passing = screen(legs, a.capital, a.dte_lo, a.dte_hi,
                               width, a.min_skew, a.rank_by)
        if a.show_all:
            allc.sort(key=lambda c: (c.s.dte, c.l.dte))
            print(fmt_table(allc, "ALL CANDIDATES"))
        print(fmt_table(passing,
                        f"PASSING  (short DTE {a.dte_lo}-{a.dte_hi}, "
                        f"width {a.width or 'any'}, skew >= {a.min_skew:+.2f}, "
                        f"ranked by {a.rank_by})"))
        if passing:
            b = passing[0]
            print(f"  PICK: {b.name}  {b.contracts} lots, ${b.margin:,.0f}, "
                  f"skew {b.skew:+.2f}, T/D {b.td:.0f}, "
                  f"theta/margin {b.theta_margin:.3f}")
            print(f"  divergence exposure: {b.div_cost:.0%} of the debit per vol "
                  f"point of front-vs-back move")
            print_overlay(b.contracts, b.margin)
        else:
            print("  NO TRADE TODAY. Log it and wait - sitting out is the "
                  "mechanism that keeps annual friction survivable.")
        if a.log:
            log_skew(date.today().isoformat(), passing[0] if passing else None,
                     a.traded, a.note)
            print(f"\n  appended to {SKEW_LOG}")

    elif a.cmd == "overlay":
        print_overlay(a.contracts, a.debit * 100 * a.contracts,
                      mini_fee=a.mini_fee, mini_spread=a.mini_spread)

    elif a.cmd == "logfill":
        log_fill(a)

    elif a.cmd == "report":
        report()


if __name__ == "__main__":
    main()
