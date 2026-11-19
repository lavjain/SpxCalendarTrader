"""Build Streamlit-style (dark theme) mockup pages from data.py and screenshot them.

Run from the repo root:  uv run --group mockups python docs/mockups/render.py
Writes docs/images/*.png and, for quick browser previews, docs/mockups/build/*.html."""
import io, math, os, random, statistics
from pathlib import Path
from datetime import date, datetime, timedelta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from playwright.sync_api import sync_playwright
from data import *

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "images"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#4A4D5A", "axes.labelcolor": "#A3A8B8", "xtick.color": "#A3A8B8", "ytick.color": "#A3A8B8", "figure.facecolor": "#0E1117", "axes.facecolor": "#0E1117", "savefig.facecolor": "#0E1117"})
BUILD = HERE / "build"
NOW = datetime(2027, 1, 12, 11, 5)
S_NOW, ATM_S, ATM_L = 6850.0, 0.141, 0.138

CSS = """
*{box-sizing:border-box} body{margin:0;font-family:Inter,'Source Sans Pro',sans-serif;color:#FAFAFA;background:#0E1117;font-size:14px}
.wrap{width:1400px;padding:22px 48px 36px}
.banner{background:#3B3317;border:1px solid #7A6420;color:#F5D97A;padding:7px 12px;border-radius:6px;font-size:12.5px;margin-bottom:14px}
h1{font-size:30px;margin:0 0 4px;font-weight:700} .sub{color:#A3A8B8;font-size:13px;margin-bottom:14px}
.tabs{display:flex;gap:28px;border-bottom:1px solid #31333F;margin-bottom:18px}
.tab{padding:8px 0;color:#FAFAFA;font-size:15px} .tab.on{color:#1C83E1;border-bottom:2px solid #1C83E1;font-weight:600}
.row{display:flex;gap:16px;align-items:flex-start}
.btn{display:inline-block;border:1px solid #5C606D;border-radius:8px;padding:7px 14px;background:#3A3D49;color:#F0F1F4;font-size:14px}
.btn.primary{background:#545867;color:#FFFFFF;border-color:#7D8190;font-weight:600}
h3{font-size:17px;margin:18px 0 8px;font-weight:600}
table{border-collapse:collapse;font-size:12.5px;font-variant-numeric:tabular-nums}
th{background:#1A1C24;color:#A3A8B8;font-weight:600;text-align:right;padding:6px 8px;border:1px solid #31333F;white-space:nowrap}
td{padding:5px 8px;border:1px solid #262730;text-align:right;white-space:nowrap}
th.l,td.l{text-align:left}
tr.best td{background:#3D3416} tr.sel td{outline:2px solid #1C83E1;outline-offset:-2px}
.pos{color:#3DD56D} .neg{color:#FF6C6C} .muted{color:#8B90A0}
.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11.5px;font-weight:600}
.pill.red{background:#4A1D1F;color:#FF8A8A} .pill.green{background:#173D24;color:#6BE38F} .pill.amber{background:#45360F;color:#FFC94D}
.card{border:1px solid #31333F;background:#0E1117;border-radius:10px;padding:14px 16px}
.card .muted{white-space:nowrap}
.sidebar{width:300px;flex:none;background:#262730;padding:26px 22px;min-height:100%;box-sizing:border-box} .sidebar .lab{font-size:12.5px;color:#A3A8B8;margin:20px 0 7px} .sidebar h4{margin:0 0 4px;font-size:16px} .sidebar .chip{padding:4px 9px;font-size:12.5px}
.filters{display:grid;grid-template-columns:minmax(320px,1fr) minmax(320px,1fr);gap:20px 48px;margin-bottom:6px;padding:16px 20px} .metric .lab{font-size:12.5px;color:#A3A8B8} .metric .val{font-size:26px;font-weight:600;margin-top:2px}
.overlay{position:absolute;inset:0;background:rgba(0,0,0,.6)}
.modal{position:absolute;left:50%;top:120px;transform:translateX(-50%);width:760px;background:#1A1C24;border:1px solid #31333F;border-radius:12px;padding:22px 26px;box-shadow:0 12px 40px rgba(0,0,0,.5)}
.input{border:1px solid #4A4D5A;border-radius:8px;padding:7px 10px;width:140px;font-size:15px;background:#262730;color:#FAFAFA}
.status{padding:9px 12px;border-radius:8px;font-size:13px}
.status.ok{background:#173D24;color:#6BE38F}
.code{font-family:"DejaVu Sans Mono",monospace;font-size:12.5px;background:#262730;border:1px solid #31333F;border-radius:8px;padding:8px 10px;color:#E6E6E6}
.seg{display:inline-flex;white-space:nowrap;border:1px solid #4A4D5A;border-radius:8px;overflow:hidden} .seg span{padding:6px 14px;font-size:13.5px} .seg span.on{background:#1C83E1;color:#fff}
.select{display:inline-block;border:1px solid #4A4D5A;border-radius:8px;padding:6px 12px;background:#262730;font-size:13.5px;min-width:230px}
.chip{display:inline-block;white-space:nowrap;border:1px solid #4A4D5A;border-radius:14px;padding:4px 12px;font-size:13px} .chip.on{background:#1C83E1;border-color:#1C83E1;color:#fff} .chip.off{color:#A3A8B8}
.toast{display:inline-block;background:#1A1C24;border:1px solid #31333F;border-radius:8px;padding:8px 12px;font-size:13px}
.kv td{border:none;padding:3px 14px 3px 0;text-align:left;font-size:13.5px}
.kv td:first-child{color:#A3A8B8}
"""

def money(x, d=0):
    s = f"{abs(x):,.{d}f}"
    return ("−$" if x < 0 else "$") + s
def sgn(x, d=2, suf=""):
    return ("+" if x > 0 else "−" if x < 0 else "") + f"{abs(x):,.{d}f}{suf}"
def cls(x): return "pos" if x > 0 else "neg" if x < 0 else ""
def dstr(d): return d.strftime("%b %-d")
def tos_order(side, n, K, se, le, price):
    """thinkorswim order line for a put calendar (SPXW). Check against an order copied from TOS before relying on it."""
    sign = "+" if side == "BUY" else "-"
    return f"{side} {sign}{n} CALENDAR SPX 100 (Weeklys) {le.strftime('%-d %b %y').upper()}/{se.strftime('%-d %b %y').upper()} {K} PUT @{price:.2f} LMT"

def dialog_page(body, mock_note):
    """A dialog on its own, without the screen behind it; the screenshot is cropped to .shot."""
    return (f"""<html><head><meta charset="utf-8"><style>{CSS} .shot .modal{{position:static;transform:none;box-shadow:none}}</style></head><body><div class="shot" style="display:inline-block;padding:24px 28px">"""
            f"""<div class="banner" style="width:760px;box-sizing:border-box;margin-bottom:16px"><b>Mockup</b> · {mock_note}</div>"""
            f"""<div style="position:relative">{body}</div></div></body></html>""")

def page(active, body, mock_note, sidebar=None):
    tabs = "".join(f'<div class="tab{" on" if t == active else ""}">{t}</div>' for t in ("Finder", "Holdings", "Performance"))
    head = f"""<div class="banner"><b>Mockup</b> · {mock_note}</div>
<h1>SPX Calendar Trader</h1><div class="sub">Paper trading only: no orders are sent. Prices from the Schwab API.</div>
<div class="tabs">{tabs}</div>"""
    if sidebar is None:
        return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="wrap" style="position:relative">{head}{body}</div></body></html>"""
    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div style="display:flex;position:relative;width:1400px">
<div class="sidebar">{sidebar}</div><div class="wrap" style="width:auto;flex:1;padding-left:36px;padding-right:36px">{head}{body}</div></div></body></html>"""

# ---------------------------------------------------------------- Finder
DTE_RANGE = (21, 35)   # short-leg DTE filter shown in the mockup (slider runs 7-56; default 25-35)
WIDTHS_ON = (5, 7)     # width chips switched on in the mockup
STRIKES_ON = ("10", "25")  # strike chips switched on: multiples of 10 and/or 25 (default: both)
FRIDAYS = short_fridays(NOW.date(), *DTE_RANGE)
F_ALL = {(fr, w): finder(S_NOW, NOW, ATM_S, ATM_L, width=w, friday=fr, sets=STRIKES_ON) for fr in FRIDAYS for w in WIDTHS}
F = finder(S_NOW, NOW, ATM_S, ATM_L, width=7)          # the default trade: Friday nearest 30 DTE, 7 days wide
SEL = F["near"]
ROWS = sorted((dict(r, width=w, short_exp=F_ALL[(fr, w)]["short_exp"], long_exp=F_ALL[(fr, w)]["long_exp"])
               for fr in FRIDAYS for w in WIDTHS_ON for r in F_ALL[(fr, w)]["rows"]),
              key=lambda r: (r["short_exp"], r["width"], r["strike"]))
_best = max(ROWS, key=lambda r: r["cal"].skew)
for _r in ROWS:
    _r["is_best_skew"] = _r is _best
    _r["is_sel"] = _r["strike"] == SEL["strike"] and _r["width"] == 7 and _r["short_exp"] == F["short_exp"]

def slider():
    lo, hi = DTE_RANGE; x = lambda d: (d - 7) / 49 * 250
    return (f'<div style="position:relative;width:250px;height:28px"><div style="position:absolute;top:12px;left:0;right:0;height:4px;background:#31333F;border-radius:2px"></div>'
            f'<div style="position:absolute;top:12px;left:{x(lo):.0f}px;width:{x(hi)-x(lo):.0f}px;height:4px;background:#1C83E1"></div>'
            + "".join(f'<div style="position:absolute;top:6px;left:{x(v)-8:.0f}px;width:16px;height:16px;border-radius:8px;background:#1C83E1"></div>' for v in (lo, hi))
            + '</div>')

def chip(w):
    if all(F_ALL[(fr, w)]["long_exp"] is None for fr in FRIDAYS):
        return f'<span class="chip off" title="No expiry that day (market holiday)" style="text-decoration:line-through;opacity:.45">{w}d</span>'
    return f'<span class="chip {"on" if w in WIDTHS_ON else "off"}">{"✓ " if w in WIDTHS_ON else ""}{w}d</span>'

def overview_row(p, top):
    c = p["near"]["cal"]; klass = " ".join(k for k, on in (("best", p is top), ("sel", p["sel"])) if on)
    return (f"<tr class='{klass}'><td class=l>{p['se']:%a %b %-d} / {p['le']:%a %b %-d}</td><td>{c.s.dte}</td><td>{c.l.dte}</td><td>{p['near']['width']}d</td>"
            f"<td>{p['near']['strike']}</td><td>{c.contracts}</td><td>{c.debit:.2f}</td><td>{c.margin:,.0f}</td><td>{c.theta:.1f}</td><td>{c.vega:.1f}</td>"
            f"<td class='{cls(round(c.skew,2))}'>{sgn(c.skew)}</td><td>{c.theta_margin*100:.2f}%</td>"
            f"<td class='{cls(round(p['best']['cal'].skew,2))}'>{sgn(p['best']['cal'].skew)} <span class=muted>@ {p['best']['strike']}</span></td><td>{len(p['sec'])}</td></tr>")

def finder_sidebar():
    lab = lambda t: f'<div class="lab">{t}</div>'
    strike_chip = lambda s: f'<span class="chip {"on" if s in STRIKES_ON else "off"}">{"✓ " if s in STRIKES_ON else ""}{s}s</span>'
    return f"""<div class="row" style="justify-content:space-between;align-items:center"><h4>Finder settings</h4><span class="btn" style="padding:2px 9px;font-size:14px">«</span></div><div class="muted" style="font-size:12px">« hides these settings; » brings them back</div>
{lab(f'Short-leg DTE: <b style="color:#FAFAFA">{DTE_RANGE[0]}–{DTE_RANGE[1]} days</b><br><span style="opacity:.7">range 7–56, default 25–35</span>')}{slider()}
{lab("Days between short and long")}<div class="row" style="gap:6px;flex-wrap:wrap">{"".join(chip(w) for w in WIDTHS)}</div>
{lab("Strikes (both = 10s plus 25s/75s)")}<div class="row" style="gap:6px">{strike_chip("10")}{strike_chip("25")}</div>
{lab("Size by")}<div class="seg" style="width:100%"><span class="on" style="flex:1;text-align:center">Margin</span><span style="flex:1;text-align:center">Contracts</span></div>
<div class="input" style="width:100%;margin-top:8px;box-sizing:border-box">$10,000</div>
<div style="margin-top:26px"><div class="btn primary" style="display:block;text-align:center">↻ Refresh</div><div class="muted" style="font-size:12px;margin-top:6px;text-align:center">Updated 11:05:12 AM</div></div>"""

def spx_history(n_days=260, seed=4):
    """Simulated daily SPX bars ending at S_NOW on NOW's date (the app pulls these from Schwab's price history)."""
    rnd = random.Random(seed)
    days, d = [], NOW.date()
    while len(days) < n_days:
        if d.weekday() < 5 and d not in HOLIDAYS: days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    closes = [S_NOW]
    for _ in range(n_days - 1):
        closes.append(closes[-1] / math.exp(rnd.gauss(0.0003, 0.0085)))
    closes.reverse()
    bars = []
    for i, (d, c) in enumerate(zip(days, closes)):
        o = closes[i - 1] * math.exp(rnd.gauss(0, 0.002)) if i else c
        hi = max(o, c) * (1 + abs(rnd.gauss(0, 0.003))); lo = min(o, c) * (1 - abs(rnd.gauss(0, 0.003)))
        bars.append(dict(d=d, o=o, h=hi, l=lo, c=c))
    return bars

def spx_chart(bars, n=63, K=None, be=None, se=None, le=None):
    """Candles for the last n trading days, 20/50-day averages, the selected strike and break-evens, and the two expiries ahead."""
    closes = [b["c"] for b in bars]
    sma = lambda k: [statistics.mean(closes[i - k + 1:i + 1]) if i >= k - 1 else None for i in range(len(closes))]
    s20, s50 = sma(20), sma(50)
    B = bars[-n:]; off = len(bars) - n
    fut, d = [], NOW.date()
    while le and (not fut or fut[-1] < le):
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in HOLIDAYS: fut.append(d)
    dates = [b["d"] for b in B] + fut
    fig, ax = plt.subplots(figsize=(12.6, 3.5))
    if K is not None:
        ax.axhspan(be[0], be[1], color="#FFC94D", alpha=.07, lw=0)
        for v in be: ax.axhline(v, color="#FFC94D", lw=.7, ls=(0, (2, 3)))
        ax.axhline(K, color="#FF4B4B", lw=1, ls="--")
        ax.text(len(dates) - .5, K, f" {K:,} strike", color="#FF4B4B", fontsize=8, va="center")
        ax.text(len(dates) - .5, be[0], f" {be[0]:,.0f} BE", color="#FFC94D", fontsize=8, va="center")
        ax.text(len(dates) - .5, be[1], f" {be[1]:,.0f} BE", color="#FFC94D", fontsize=8, va="center")
    for i, b in enumerate(B):
        col = "#3DD56D" if b["c"] >= b["o"] else "#FF6C6C"
        ax.vlines(i, b["l"], b["h"], color=col, lw=.8)
        ax.bar(i, max(abs(b["c"] - b["o"]), .6), bottom=min(b["o"], b["c"]), color=col, width=.6)
    ax.plot(range(n), s20[off:], color="#6CA0FF", lw=1.2, label="20-day avg")
    ax.plot(range(n), s50[off:], color="#C792EA", lw=1.2, label="50-day avg")
    ax.axvline(n - 1, color="#A3A8B8", lw=.8, ls=":")
    lo_y = min([b["l"] for b in B] + ([be[0]] if be else [])); hi_y = max([b["h"] for b in B] + ([be[1]] if be else []))
    pad = (hi_y - lo_y) * .08; ax.set_ylim(lo_y - pad, hi_y + pad * 2.5)     # fit the candles; averages may run off the edge
    for j, (e, lab) in enumerate(((se, "short"), (le, "long"))):
        if e in dates:
            x = dates.index(e); ax.axvline(x, color="#4A4D5A", lw=1, ls="--")
            ax.text(x, lo_y - pad * (.3 + .9 * j), f" {lab} {e:%b %-d}", color="#A3A8B8", fontsize=8, va="bottom")
    ticks = [i for i, d in enumerate(dates) if d.weekday() == 0 and (d.day <= 7 or n <= 30)] or list(range(0, len(dates), 10))
    ax.set_xticks(ticks); ax.set_xticklabels([dates[i].strftime("%b %-d") for i in ticks], fontsize=8)
    ax.set_xlim(-1, len(dates) + 9); ax.grid(axis="y", color="#262730")
    ax.set_title(f"SPX daily · last 3 months · {B[-1]['c']:,.2f}", loc="left", fontsize=10, color="#FAFAFA")
    lg = ax.legend(frameon=False, loc="upper left", fontsize=8, ncol=2)
    for t in lg.get_texts(): t.set_color("#A3A8B8")
    return svg(fig)

def spx_section(bars, n=63, K=None, be=None, se=None, le=None, iv=None):
    B = bars[-n:]; c = [b["c"] for b in bars]
    hi, lo = max(b["h"] for b in B), min(b["l"] for b in B)
    rets = [math.log(c[i] / c[i - 1]) for i in range(len(c) - 20, len(c))]
    rv = statistics.stdev(rets) * math.sqrt(252) * 100
    s20 = statistics.mean(c[-20:]); chg5 = (c[-1] / c[-6] - 1) * 100
    stats = [("3-month high / low", f"{hi:,.0f} / {lo:,.0f}"), ("From 3-month high", f"{(c[-1]/hi-1)*100:+.1f}%"),
             ("5-day change", f"{chg5:+.1f}%"), ("vs 20-day avg", f"{(c[-1]/s20-1)*100:+.1f}%"),
             ("20-day realized vol", f"{rv:.1f}%" + (f" (short IV {iv*100:.1f}%)" if iv else ""))]
    st = "".join(f'<div class="card metric" style="padding:8px 12px"><div class="lab">{a}</div><div class="val" style="font-size:17px">{b}</div></div>' for a, b in stats)
    chips = "".join(f'<span class="chip {"on" if x == "3M" else "off"}">{x}</span>' for x in ("1M", "3M", "6M", "1Y", "2Y"))
    tog = "".join(f'<span class="chip on">✓ {x}</span>' for x in ("20/50-day avg", "Strike & break-evens", "Expiries"))
    return f"""<h3>SPX <span class="muted" style="font-weight:400;font-size:13px">· daily bars · where SPX is now against the recent past, with the selected calendar drawn on</span></h3>
<div class="row" style="gap:8px;align-items:center;margin-bottom:10px">{chips}<span style="width:14px"></span>{tog}</div>
<div class="row" style="gap:10px;margin-bottom:10px">{st}</div>
<div class="card" style="width:fit-content">{spx_chart(bars, n, K, be, se, le)}</div>"""

def settings_bar():
    """Shown above Inputs when the settings sidebar is collapsed: what is applied, plus Refresh, so nothing needs the sidebar."""
    item = lambda a, b: f'<span class="muted">{a}</span> <b>{b}</b>'
    parts = " <span class='muted'>·</span> ".join([item("Short DTE", f"{DTE_RANGE[0]}–{DTE_RANGE[1]}"), item("Widths", ", ".join(f"{w}d" for w in WIDTHS_ON)),
        item("Strikes", " + ".join(f"{x}s" for x in STRIKES_ON)), item("Size by", f"Margin {money(MARGIN)}")])
    return (f'<div class="card row" style="align-items:center;gap:16px;padding:10px 14px;margin:6px 0 4px;width:fit-content">'
            f'<span class="btn" style="padding:3px 10px">» Settings</span><span style="font-size:14px">{parts}</span>'
            f'<span class="btn primary" style="padding:5px 14px">↻ Refresh</span><span class="muted" style="font-size:12px">Updated 11:05:12 AM</span></div>')

def finder_body(collapsed=False):
    inputs = f"""<table><tr><th class=l>Time (ET)</th><th>SPX</th><th class=l>Short expiries (DTE filter)</th><th class=l>Widths on</th><th>Size by</th></tr>
<tr><td class=l>{NOW:%a %b %-d, %Y %-I:%M %p}</td><td>{F['spx']:,.2f}</td><td class=l>{' · '.join(f'{fr:%a %b %-d} ({(fr - NOW.date()).days}d)' for fr in FRIDAYS)}</td><td class=l>{', '.join(f'{w}d' for w in WIDTHS_ON)}</td><td>Margin {money(MARGIN)}</td></tr></table>"""

    # ---- Overview: one row per short/long pair, at its ~40-delta strike
    pairs = {}
    for r in ROWS:
        pairs.setdefault((r["short_exp"], r["long_exp"]), []).append(r)
    ov = []
    for (se, le), sec in pairs.items():
        near = min(sec, key=lambda x: abs(abs(x["s"]["delta"]) - 0.40))
        best = max(sec, key=lambda x: x["cal"].skew)
        ov.append(dict(se=se, le=le, sec=sec, near=near, best=best, sel=any(x["is_sel"] for x in sec)))
    ov.sort(key=lambda p: p["best"]["cal"].skew, reverse=True)          # the mockup shows the table sorted by Best skew
    top = ov[0]
    ohdr = "".join(f"<th{' class=l' if h == 'Short / Long' else ''}>{h}</th>" for h in
        ["Short / Long", "Sht DTE", "Lng DTE", "Width", "~40Δ strike", "Contracts", "Price", "Margin", "Theta", "Vega", "Skew", "Θ/Mgn", "Best skew ▼", "Strikes"])
    otr = ""; ncol = 14
    for w in sorted({p["near"]["width"] for p in ov}):                      # one segment per width, narrowest first
        seg = [p for p in ov if p["near"]["width"] == w]
        otr += (f"<tr><td class=l colspan={ncol} style='background:#1A1C24;color:#FAFAFA;font-weight:600;padding-top:9px;padding-bottom:7px'>"
                f"{w}-day width <span style='font-weight:400;color:#A3A8B8'>· {len(seg)} pair{'s' if len(seg) != 1 else ''} · long leg {w} days after the short's Friday</span></td></tr>")
        otr += "".join(overview_row(p, top) for p in seg)
    overview = f"<table><tr>{ohdr}</tr>{otr}</table>"

    # ---- Detail: every strike of the selected pair
    P = next(p for p in ov if p["sel"])
    dhdr = "".join(f"<th>{h}</th>" for h in
        ["Strike", "Short Δ", "Contracts", "Price", "Margin", "Delta", "Gamma", "Theta", "Vega", "Skew", "T/D", "Θ/Mgn"])
    dtr = ""
    for r in P["sec"]:
        c = r["cal"]; star = " ★" if r is P["near"] else ""
        klass = " ".join(k for k, on in (("best", r is P["best"]), ("sel", r["is_sel"])) if on)
        dtr += (f"<tr class='{klass}'><td>{r['strike']}{star}</td><td>{abs(r['s']['delta'])*100:.1f}</td><td>{c.contracts}</td><td>{c.debit:.2f}</td>"
                f"<td>{c.margin:,.0f}</td><td>{c.delta:.1f}</td><td>{c.gamma:.2f}</td><td>{c.theta:.1f}</td><td>{c.vega:.1f}</td>"
                f"<td class='{cls(round(c.skew,2))}'>{sgn(c.skew)}</td><td>{'—' if abs(c.delta) < 0.5 else f'{c.td:.1f}'}</td><td>{c.theta_margin*100:.2f}%</td></tr>")
    pc = P["near"]["cal"]
    detail = f"<table><tr>{dhdr}</tr>{dtr}</table>"
    dtitle = (f"<h3>Detail <span class='muted' style='font-weight:400;font-size:13px'>· short {P['se']:%a %b %-d} ({pc.s.dte} DTE) / long {P['le']:%a %b %-d} ({pc.l.dte} DTE) · "
              f"{P['near']['width']}-day width · all {len(P['sec'])} strikes in the 35–45Δ band</span></h3>")

    lg = lambda name, q, e: f"<tr><td class=l>{name}</td><td class=l>{e:%b %-d}</td><td>{q['dte']}</td><td>{q['mark']:.2f}</td><td>{q['bid']:.2f}</td><td>{q['ask']:.2f}</td><td>{q['delta']:.3f}</td><td>{q['gamma']:.4f}</td><td>{q['theta']:.2f}</td><td>{q['vega']:.2f}</td><td>{q['iv']*100:.2f}%</td></tr>"
    legs = f"""<table><tr><th class=l>Leg ({SEL['strike']} put)</th><th class=l>Expiry</th><th>DTE</th><th>Mark</th><th>Bid</th><th>Ask</th><th>Delta</th><th>Gamma</th><th>Theta</th><th>Vega</th><th>IV</th></tr>
{lg('Short', SEL['s'], F['short_exp'])}{lg('Long', SEL['l'], F['long_exp'])}</table>"""

    _mid = round((SEL["bid"] + SEL["ask"]) / 2, 2); _price = round(_mid + FILL, 2); _n = contracts_for(_price)
    note = lambda t: f'<div class="muted" style="margin-top:6px;font-size:12px">{t}</div>'
    _be = break_evens(SEL["strike"], F["short_exp"], F["long_exp"], SEL["l"]["iv"], round((SEL["bid"] + SEL["ask"]) / 2 + FILL, 2))
    spx = spx_section(spx_history(), 63, SEL["strike"], _be, F["short_exp"], F["long_exp"], SEL["s"]["iv"])
    bar = settings_bar() if collapsed else ""
    return f"""{bar}<h3>Inputs</h3>{inputs}
{spx}
<div class="muted" style="margin-top:6px;font-size:12px">Range chips: 1M, 3M (default), 6M, 1Y, 2Y. Red dashed: selected strike; yellow band: its break-evens at the short expiry; dashed verticals: the short and long expiries ahead. Updates with the selected Detail row.</div>
<h3>Overview <span class="muted" style="font-weight:400;font-size:13px">· one row per short/long pair at its ~40Δ strike · sized to {money(MARGIN)} margin</span></h3>{overview}
{note("One segment per width (days between short and long). Click a column header to sort within each segment (here: Best skew). Highlighted: highest best skew overall. Red outline: the selected pair, shown in Detail below. Click any row to select it.")}
{dtitle}{detail}
{note("★: strike nearest 40Δ. Highlighted: highest skew in this pair. T/D shows — when position delta is near zero. Red outline: selected strike. Click a row to open the trade panel.")}
<h3>Risk profile <span class="muted" style="font-weight:400;font-size:13px">· selected calendar, sized as it would open ({_n} × at {_price:.2f})</span></h3>
<div class="card" style="width:fit-content">{risk_profile(SEL['strike'], F['short_exp'], F['long_exp'], NOW.date(), _price, _n, SEL['s']['iv'], SEL['l']['iv'], S_NOW, f"{SEL['strike']} put calendar · {F['short_exp']:%b %-d} / {F['long_exp']:%b %-d}")}</div>
{note("Like thinkorswim Analyze: solid = P/L at the short expiry (long leg priced with Black-Scholes at its IV), dashed = P/L today. Yellow dots: break-evens. Dotted line: SPX now.")}
<h3>Legs</h3>{legs}"""

def dialog_body():
    mid = round((SEL["bid"] + SEL["ask"]) / 2, 2)
    price = round(mid + FILL, 2)
    n = contracts_for(price)
    cost = price * 100 * n
    lo, hi = break_evens(SEL["strike"], F["short_exp"], F["long_exp"], SEL["l"]["iv"], price)
    c = SEL["cal"]
    return f"""<div class="modal">
<div style="font-size:20px;font-weight:700;margin-bottom:12px">Open trade</div>
<div style="font-size:14.5px;margin-bottom:14px">SPX {SEL['strike']:,} put calendar, short {dstr(F['short_exp'])} / long {dstr(F['long_exp'])}, <b>{n} contracts</b></div>
<div class="status ok" style="margin-bottom:14px">✓ Stable price: 5 quotes in a row within $0.10 · spread bid {SEL['bid']:.2f} / ask {SEL['ask']:.2f} · mid {mid:.2f}</div>
<div class="row" style="align-items:center;margin-bottom:14px"><div><div class="muted" style="font-size:12.5px;margin-bottom:4px">Fill price (mid + $0.10, editable)</div><div class="input" style="width:110px">{price:.2f}</div></div>
<div style="margin-left:18px"><div class="muted" style="font-size:12.5px;margin-bottom:4px">Size by</div><div class="row" style="gap:8px;align-items:center"><div class="seg"><span class="on">Margin</span><span>Contracts</span></div><div class="input" style="width:110px">{money(MARGIN)}</div></div></div>
<div style="margin-left:18px"><div class="muted" style="font-size:12.5px;margin-bottom:4px">Contracts · total cost</div><div style="font-size:22px;font-weight:600">{n} · {money(cost)}</div></div></div>
<table class="kv"><tr><td>SPX</td><td>{S_NOW:,.2f}</td><td>Skew</td><td>{sgn(c.skew)} vol pts</td></tr>
<tr><td>Target +10%</td><td>{price*1.10:.2f}</td><td>Flag −10%</td><td>{price*0.90:.2f}</td></tr>
<tr><td>Break-evens (short expiry)</td><td>{lo:,.0f} – {hi:,.0f}</td><td>Θ / margin</td><td>{c.theta_margin*100:.2f}% a day</td></tr></table>
{note_box("", 'Why this one, e.g. "best skew of the week, VIX calm"', "Notes (optional; grows as you type)")}
<div style="margin-top:14px"><div class="muted" style="font-size:12.5px;margin-bottom:4px">thinkorswim order</div><div class="code">{tos_order("BUY", n, SEL['strike'], F['short_exp'], F['long_exp'], price)}</div></div>
<div style="margin-top:16px;display:flex;gap:10px;justify-content:space-between;align-items:flex-end">
<div style="display:flex;flex-direction:column;gap:8px;align-items:flex-start"><span class="btn">⧉ Copy to TOS</span><span class="btn">⇩ Paste from TOS</span>
<span class="muted" style="font-size:12px">Placed it in TOS? Paste the filled order to record your real price and contracts.</span></div>
<span><span class="btn">Cancel</span> <span class="btn primary">Confirm</span></span></div></div>"""

# ---------------------------------------------------------------- Holdings
PREV = dict(S=6838.0, atm_s=0.1412, atm_l=0.1381)  # Mon Jan 11, 4:15 PM ET close
NOW_V = (ATM_S, ATM_L)

def value_trade(d0, S0, v0, d1, S1, v1, width=7):
    f0 = finder(S0, datetime.combine(d0, datetime.min.time()), *v0, width=width)
    r0 = f0["near"]; K, se, le = r0["strike"], f0["short_exp"], f0["long_exp"]
    fill = round((r0["bid"] + r0["ask"]) / 2 + FILL, 2); n = contracts_for(fill)
    s = leg_quote(S1, K, d1, se, v1[0]); l = leg_quote(S1, K, d1, le, v1[1])
    mid = l["mark"] - s["mark"]; cost = fill * 100 * n; value = (mid - FILL) * 100 * n
    return dict(K=K, se=se, le=le, n=n, fill=fill, cost=cost, value=value, pl=value - cost,
                plp=(value - cost) / cost * 100, s=s, l=l, d0=d0, S0=S0)

def solve(target, fn, grid):
    return min(grid, key=lambda x: abs(fn(x)["plp"] - target))

# open trades: entry date, entry ATM vols, target P/L % now  -> entry SPX solved on a 1-pt grid
OPEN = [(date(2027, 1, 6), (0.141, 0.138), 11.0, 7), (date(2027, 1, 8), (0.1395, 0.1385), -10.6, 7), (date(2027, 1, 11), (0.141, 0.138), 0.7, 5)]

def holdings_rows():
    out = []; today = NOW.date()
    for d0, v0, tgt, w in OPEN:
        S0 = solve(tgt, lambda x: value_trade(d0, x, v0, today, S_NOW, NOW_V, w), range(6770, 6931))
        t = value_trade(d0, S0, v0, today, S_NOW, NOW_V, w)
        K, se, le, n = t["K"], t["se"], t["le"], t["n"]
        sp = leg_quote(PREV["S"], K, today, se, PREV["atm_s"]); lp = leg_quote(PREV["S"], K, today, le, PREV["atm_l"])
        s, l = t["s"], t["l"]
        volpl = ((s["iv"] - sp["iv"]) * 100 * s["vega"] * -1 + (l["iv"] - lp["iv"]) * 100 * l["vega"]) * 100 * n
        dpc = (l["delta"] - s["delta"]) * 100
        lo, hi = break_evens(K, se, le, l["iv"], t["fill"])
        tdays = sum(1 for i in range(1, (today - d0).days + 1) if (d0 + timedelta(days=i)).weekday() < 5)
        flags = []
        if t["plp"] <= -10: flags.append('<span class="pill red">LOSS &gt; 10%</span>')
        if t["plp"] >= 10: flags.append('<span class="pill green">+10% TARGET</span>')
        if abs(dpc) > 2: flags.append('<span class="pill amber">DELTA &gt; 2</span>')
        close_px = round(t["value"] / (100 * n), 2)
        e_s = leg_quote(S0, K, d0, se, v0[0]); e_l = leg_quote(S0, K, d0, le, v0[1])
        out.append(dict(t, skew0=(e_s['iv'] - e_l['iv']) * 100, close_px=close_px, tos=tos_order("SELL", n, K, se, le, close_px), days=(today - d0).days, tdays=tdays, lo=lo, hi=hi, volpl=volpl, dpc=dpc, flags=" ".join(flags)))
    return out

# Holdings columns: key, label, shown by default, group. "Trade" is always shown and pinned on the left.
HCOLS = [("entered", "Entered", False, "Position"), ("days", "Days", True, "Position"), ("cost", "Cost", False, "Position"),
         ("value", "Value now", False, "Position"), ("account", "Account", False, "Position"),
         ("pl", "P/L", True, "P/L"), ("volpl", "Vol P&L today", True, "P/L"),
         ("be", "Break-evens", True, "Risk"), ("tobe", "To nearest BE", True, "Risk"), ("dpc", "Δ / contract", True, "Risk"),
         ("theta", "Theta / day", False, "Risk"), ("vega", "Vega", False, "Risk"),
         ("siv", "Short IV", False, "Volatility"), ("liv", "Long IV", False, "Volatility"), ("skew", "Skew now", False, "Volatility"),
         ("skew0", "Skew at entry", True, "Volatility"), ("flag", "Flag", True, "Flags & notes"), ("notes", "Notes", True, "Flags & notes")]

NOTE = {6730: "Entered after skew turned positive (+0.38); VIX 15.8. Sized to $10k.\nJan 11: up 7%. Holding for the +10% target; CPI Wednesday morning, decide before then.",
        6740: "Took this one a day early; SPX was near the 20-day average."}   # one note per trade (by strike in the mockup)

def note_box(text, placeholder, label):
    """A note box that grows with its text: one line when empty, as many lines as the note needs."""
    body = text.replace("\n", "<br>") if text else f'<span style="color:#A3A8B8">{placeholder}</span>'
    return (f'<div style="margin-top:12px"><div class="muted" style="font-size:12.5px;margin-bottom:4px">{label}</div>'
            f'<div class="input" style="width:100%;box-sizing:border-box;line-height:1.45;white-space:normal">{body}</div></div>')

def notes_body():
    h = holdings_rows()[0]
    return f"""<div class="modal">
<div style="font-size:20px;font-weight:700;margin-bottom:4px">Notes</div>
<div class="muted" style="font-size:13.5px;margin-bottom:4px">SPX {h['K']:,} put calendar · {dstr(h['se'])} / {dstr(h['le'])} · {h['n']} contracts · opened {h['d0']:%b %-d}</div>
{note_box(NOTE[h['K']], "", "One Notes box per trade · last saved Jan 11, 2:15 PM")}
<div style="margin-top:14px;display:flex;gap:10px;justify-content:flex-end"><span class="btn">Cancel</span><span class="btn primary">Save</span></div>
<div class="muted" style="margin-top:10px;font-size:12px">The box grows as you type. The same notes show in the Open trade and Close trade dialogs, in Performance → Trades and in the CSV export.</div></div>"""

def hcell(k, h):
    sd = lambda x: ('−' if x < 0 else '+') + money(abs(x))
    dist = min(abs(S_NOW - h["lo"]), abs(S_NOW - h["hi"])); n = h["n"]
    return {"entered": f"<td class=l>{h['d0']:%b %-d} @ {h['S0']:,.0f}</td>", "days": f"<td>{h['days']} ({h['tdays']})</td>",
            "cost": f"<td>{money(h['cost'])}</td>", "value": f"<td>{money(h['value'])}</td>", "account": "<td class=l>Paper</td>",
            "pl": f"<td class='{cls(h['pl'])}'>{sd(h['pl'])} ({sgn(h['plp'],1,'%')})</td>", "volpl": f"<td class='{cls(h['volpl'])}'>{sd(h['volpl'])}</td>",
            "be": f"<td>{h['lo']:,.0f} – {h['hi']:,.0f}</td>", "tobe": f"<td>{dist:,.0f} pts</td>",
            "dpc": f"<td>{h['dpc']:+.2f}</td>", "theta": f"<td>{(h['l']['theta'] - h['s']['theta']) * 100 * n:+,.0f}</td>",
            "vega": f"<td>{(h['l']['vega'] - h['s']['vega']) * 100 * n:+,.0f}</td>",
            "siv": f"<td>{h['s']['iv']*100:.2f}%</td>", "liv": f"<td>{h['l']['iv']*100:.2f}%</td>",
            "skew": f"<td class='{cls(round((h['s']['iv']-h['l']['iv'])*100,2))}'>{sgn((h['s']['iv']-h['l']['iv'])*100)}</td>",
            "skew0": f"<td class='{cls(round(h['skew0'],2))}'>{sgn(h['skew0'])}</td>",
            "flag": f"<td class=l>{h['flags'] or '<span class=muted>—</span>'}</td>",
            "notes": (f"<td class=l><span class='btn' style='padding:1px 9px;font-size:12px'>✎ View</span></td>" if h['K'] in NOTE
                      else "<td class=l><span class='btn' style='padding:1px 9px;font-size:12px;color:#A3A8B8'>✎ Add</span></td>")}[k]

def holdings_body(columns_open=False, on=None):
    H = holdings_rows()
    on = on or [k for k, _, d, _ in HCOLS if d]
    cols = [c for c in HCOLS if c[0] in on]
    hdr = "<th class=l style='position:sticky;left:0;background:#1A1C24;box-shadow:2px 0 0 #31333F'>Trade</th>" + "".join(
        f"<th{' class=l' if k in ('entered','flag','account','notes') else ''}>{lab}</th>" for k, lab, _, _ in cols)
    trs = ""
    for h in H:
        sel = h is H[0]
        bg = "#132A40" if sel else "#0E1117"
        first = (f"<td class=l style='position:sticky;left:0;background:{bg};box-shadow:2px 0 0 #31333F{';border-left:3px solid #1C83E1' if sel else ''}'>"
                 f"{h['K']:,} P · {dstr(h['se'])}/{dstr(h['le'])} · {(h['le'] - h['se']).days}d · {h['n']}×</td>")
        trs += f"<tr{' style=background:#132A40' if sel else ''}>{first}{''.join(hcell(k, h) for k, *_ in cols)}</tr>"
    tot_pl = sum(h["pl"] for h in H); tot_cost = sum(h["cost"] for h in H); tot_vol = sum(h["volpl"] for h in H)
    metrics = "".join(f'<div class="card metric" style="min-width:190px;padding:10px 14px"><div class="lab">{a}</div><div class="val {c}" style="font-size:22px">{b}</div></div>' for a, b, c in [
        ("SPX now", f"{S_NOW:,.2f} <span style='font-size:14px' class='{cls(S_NOW - PREV['S'])}'>{S_NOW - PREV['S']:+,.2f} ({(S_NOW / PREV['S'] - 1) * 100:+.2f}%)</span>", ""),
        ("Open trades", str(len(H)), ""), ("Capital in trades", money(tot_cost), ""),
        ("Open P/L", ('−' if tot_pl < 0 else '+') + money(abs(tot_pl)), cls(tot_pl)),
        ("Vol P&L today", ('−' if tot_vol < 0 else '+') + money(abs(tot_vol)), cls(tot_vol))])
    toolbar = (f'<div class="row" style="gap:8px;align-items:center"><span class="btn primary">＋ Open trade</span>'
               f'<span class="btn">Close selected</span><span class="btn" style="{"border-color:#1C83E1" if columns_open else ""}">▦ Columns ({len(cols) + 1} of {len(HCOLS) + 1}) ▾</span>'
               f'<span class="btn">↻ Refresh</span></div>')
    pop = ""
    if columns_open:
        groups = ""
        for g in dict.fromkeys(c[3] for c in HCOLS):
            items = "".join(f'<div style="margin:4px 0;font-size:13.5px"><span style="display:inline-block;width:15px;height:15px;border-radius:4px;vertical-align:-3px;margin-right:7px;'
                            f'{"background:#1C83E1;border:1px solid #1C83E1" if k in on else "border:1px solid #4A4D5A"};color:#fff;font-size:11px;text-align:center;line-height:15px">{"✓" if k in on else ""}</span>{lab}</div>'
                            for k, lab, _, gg in HCOLS if gg == g)
            groups += f'<div><div class="muted" style="font-size:12px;font-weight:600;margin-bottom:2px">{g}</div>{items}</div>'
        pop = (f'<div style="position:absolute;left:0;top:44px;z-index:5;width:520px;background:#1A1C24;border:1px solid #31333F;border-radius:10px;padding:14px 16px;box-shadow:0 10px 30px rgba(0,0,0,.5)">'
               f'<div class="row" style="justify-content:space-between;margin-bottom:8px"><b>Columns</b><span class="muted" style="font-size:12px">Trade is always shown · saved for next time</span></div>'
               f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px 18px">{groups}</div>'
               f'<div class="row" style="gap:8px;margin-top:12px"><span class="btn" style="padding:4px 10px;font-size:13px">Show all</span><span class="btn" style="padding:4px 10px;font-size:13px">Reset to default</span></div></div>')
    H0 = H[0]
    table = (f'<div style="width:1330px;overflow:hidden;border:1px solid #31333F;border-radius:8px"><div style="width:max-content">'
             f'<table style="border:none"><tr>{hdr}</tr>{trs}</table></div></div>'
             + ('<div style="width:1330px;height:8px;background:#1A1C24;border-radius:4px;margin-top:4px;position:relative"><div style="position:absolute;left:0;width:72%;height:8px;background:#4A4D5A;border-radius:4px"></div></div>'
                if len(cols) > 11 else ""))       # a scrollbar only when the columns don't fit
    shown = sum(1 for c in CLOSED if c[2] >= NOW.date() - timedelta(days=7))
    closed = f"""<div class="row" style="align-items:center;gap:14px;margin:26px 0 8px"><h3 style="margin:0">Closed</h3>
<span class="select" style="min-width:150px;padding:4px 12px">Last 7 days ▾</span>
<span class="muted" style="font-size:12.5px">{shown} of {len(CLOSED)} closed trades · other choices: 14, 30, 90 days, All · full history in Performance → Trades</span></div>
<table><tr><th class=l>Trade</th><th class=l>Entered</th><th class=l>Exited</th><th>Days</th><th>P/L</th><th class=l>Exit reason</th><th class=l>Price source</th></tr>""" + closed_rows(7) + "</table>"
    spx = spx_section(spx_history(), 63, H0["K"], (H0["lo"], H0["hi"]), H0["se"], H0["le"], H0["s"]["iv"])
    return f"""{spx}
<div class="muted" style="margin:6px 0 16px;font-size:12px">Same chart as the Finder. Drawn on: the selected trade's strike, break-evens and expiries.</div>
<div class="row" style="gap:10px">{metrics}</div>
<div class="row" style="justify-content:flex-start;align-items:center;gap:20px;margin:20px 0 8px"><h3 style="margin:0">Open</h3><div style="position:relative">{toolbar}{pop}</div></div>
{table}
<div class="muted" style="margin-top:6px;font-size:12px">Click a row to select it; Close selected opens its close dialog, and its risk profile shows below. Trade stays pinned on the left while the other columns scroll. ＋ Open trade opens an empty Open trade dialog, filled by ⇩ Paste from TOS.</div>
<h3>Risk profile <span class="muted" style="font-weight:400;font-size:13px">· selected trade (row 1)</span></h3>
<div class="card" style="width:fit-content">{risk_profile(H0['K'], H0['se'], H0['le'], NOW.date(), H0['fill'], H0['n'], H0['s']['iv'], H0['l']['iv'], S_NOW, f"{H0['K']:,} put calendar · {H0['se']:%b %-d} / {H0['le']:%b %-d} · {H0['n']}× at {H0['fill']:.2f}", now_pl=H0['pl'])}</div>
<div class="muted" style="margin-top:6px;font-size:12px">Blue dot: P/L now.</div>{closed}"""
def close_dialog_body():
    h = holdings_rows()[0]                                         # row 1: the trade at its +10% target
    mid = round(h["close_px"] + FILL, 2); px = h["close_px"]; n = h["n"]
    proceeds = px * 100 * n; pl = proceeds - h["cost"]; plp = pl / h["cost"] * 100
    b_s, b_l = h["s"], h["l"]
    bid = round(mid - 0.10, 2); ask = round(mid + 0.10, 2)
    return f"""<div class="modal">
<div style="font-size:20px;font-weight:700;margin-bottom:12px">Close trade</div>
<div style="font-size:14.5px;margin-bottom:14px">SPX {h['K']:,} put calendar, short {dstr(h['se'])} / long {dstr(h['le'])}, <b>{n} contracts</b>, opened {h['d0']:%b %-d} at {h['fill']:.2f}</div>
<div class="status ok" style="margin-bottom:14px">✓ Stable price: 5 quotes in a row within $0.10 · spread bid {bid:.2f} / ask {ask:.2f} · mid {mid:.2f}</div>
<div class="row" style="align-items:center;margin-bottom:14px"><div><div class="muted" style="font-size:12.5px;margin-bottom:4px">Exit price (mid − $0.10, editable)</div><div class="input" style="width:110px">{px:.2f}</div></div>
<div style="margin-left:28px"><div class="muted" style="font-size:12.5px;margin-bottom:4px">P/L</div><div style="font-size:22px;font-weight:600" class="{cls(pl)}">{'−' if pl<0 else '+'}{money(abs(pl))} ({sgn(plp,1,'%')})</div></div>
<div style="margin-left:28px"><div class="muted" style="font-size:12.5px;margin-bottom:4px">Days held</div><div style="font-size:22px;font-weight:600">{h['days']} <span class="muted" style="font-size:14px">({h['tdays']} trading)</span></div></div></div>
<table class="kv"><tr><td>SPX now</td><td>{S_NOW:,.2f} <span class="muted">(entry {h['S0']:,.0f})</span></td><td>Exit reason</td><td><span class="select" style="min-width:0;padding:3px 10px">+10% target ▾</span> <span class="muted">(suggested)</span></td></tr>
<tr><td>Cost</td><td>{money(h['cost'])}</td><td>Proceeds</td><td>{money(proceeds)}</td></tr>
<tr><td>Short / long IV now</td><td>{b_s['iv']*100:.2f}% / {b_l['iv']*100:.2f}%</td><td>Vol P&L today</td><td class="{cls(h['volpl'])}">{'−' if h['volpl']<0 else '+'}{money(abs(h['volpl']))}</td></tr></table>
{note_box(NOTE[h['K']], "", "Notes (the trade's notes; edit or add to them)")}
<div style="margin-top:14px"><div class="muted" style="font-size:12.5px;margin-bottom:4px">thinkorswim order</div><div class="code">{h['tos']}</div></div>
<div style="margin-top:16px;display:flex;gap:10px;justify-content:space-between;align-items:flex-end">
<div style="display:flex;flex-direction:column;gap:8px;align-items:flex-start"><span class="btn">⧉ Copy to TOS</span><span class="btn">⇩ Paste from TOS</span>
<span class="muted" style="font-size:12px">Placed it in TOS? Paste the filled order to record your real price and contracts.</span></div>
<span><span class="btn">Cancel</span> <span class="btn primary">Confirm</span></span></div>
<div class="muted" style="margin-top:10px;font-size:12px">Confirm saves the exit snapshot (time, SPX, VIX, both IVs, price and its source) and moves the trade to Closed.</div></div>"""

import re as _re
TOS_RE = _re.compile(r"^(BUY|SELL) ([+-]\d+) CALENDAR SPX 100 \(Weeklys\) (\d{1,2} [A-Z]{3} \d{2})/(\d{1,2} [A-Z]{3} \d{2}) (\d+) (PUT|CALL) @(\d+\.\d{2}) (LMT|MKT)$")

def parse_tos(line):
    """Read a thinkorswim calendar order line (the same format Copy to TOS writes). Returns the fields, or None."""
    m = TOS_RE.match(line.strip())
    if not m: return None
    side, qty, back, front, K, right, px, _ = m.groups()
    d1, d2 = (datetime.strptime(x.title(), "%d %b %y").date() for x in (back, front))
    return dict(side=side, n=abs(int(qty)), K=int(K), right=right, price=float(px), se=min(d1, d2), le=max(d1, d2))

PASTED = "BUY +10 CALENDAR SPX 100 (Weeklys) 12 FEB 27/5 FEB 27 6780 PUT @9.20 LMT"

def paste_dialog_body():
    o = parse_tos(PASTED); K, se, le, n, px = o["K"], o["se"], o["le"], o["n"], o["price"]
    today = NOW.date(); filled = datetime(2027, 1, 11, 15, 58)
    s0 = leg_quote(PREV["S"], K, filled.date(), se, PREV["atm_s"]); l0 = leg_quote(PREV["S"], K, filled.date(), le, PREV["atm_l"])
    s1 = leg_quote(S_NOW, K, today, se, ATM_S); l1 = leg_quote(S_NOW, K, today, le, ATM_L)
    mid_now = l1["mark"] - s1["mark"]; cost = px * 100 * n; value = (mid_now - FILL) * 100 * n; pl = value - cost
    lo, hi = break_evens(K, se, le, l1["iv"], px); skew0 = (s0["iv"] - l0["iv"]) * 100
    ok = lambda t: f'<div style="color:#3DD56D;font-size:13.5px;margin:3px 0">✓ {t}</div>'
    checks = "".join([ok(f"SPXW expiries {dstr(se)} and {dstr(le)} exist; long leg {(le - se).days} days after the short"),
                      ok(f"Short leg {abs(s0['delta'])*100:.1f}Δ at entry, inside the 35–45Δ band"),
                      ok("Not already in Holdings")])
    kv = lambda a, b: f"<td>{a}</td><td>{b}</td>"
    return f"""<div class="modal">
<div style="font-size:20px;font-weight:700;margin-bottom:6px">Open trade <span class="muted" style="font-size:14px;font-weight:400">· filled in from TOS</span></div>
<div class="muted" style="font-size:13px;margin-bottom:12px">After ⇩ Paste from TOS: the pasted order replaces what the dialog showed, so a trade placed straight in thinkorswim can be entered from any row. In the Close trade dialog, a pasted SELL line sets the exit price the same way.</div>
<div class="muted" style="font-size:12.5px;margin-bottom:4px">Pasted order line (from TOS: right-click the order → Copy, or the Copy to TOS format)</div>
<div class="code" style="border:1px solid #3DD56D">{PASTED}</div>
<div style="margin:12px 0 4px;font-weight:600">Read as</div>
<table class="kv"><tr>{kv("Action", "Open (BUY)")}{kv("Contracts", n)}</tr>
<tr>{kv("Trade", f"SPX {K:,} put calendar")}{kv("Width", f"{(le - se).days} days")}</tr>
<tr>{kv("Short leg", f"Fri {dstr(se)} ({(se - today).days} DTE)")}{kv("Long leg", f"Fri {dstr(le)} ({(le - today).days} DTE)")}</tr></table>
<div style="margin:10px 0">{checks}</div>
<div class="row" style="align-items:flex-end;gap:22px;margin-bottom:12px">
<div><div class="muted" style="font-size:12.5px;margin-bottom:4px">Fill price (from the line, editable)</div><div class="input" style="width:110px">{px:.2f}</div></div>
<div><div class="muted" style="font-size:12.5px;margin-bottom:4px">Filled at (ET, editable)</div><div class="input" style="width:190px">{filled:%b %-d, %Y %-I:%M %p}</div></div>
<div><div class="muted" style="font-size:12.5px;margin-bottom:4px">Account</div><div class="select" style="min-width:120px">Paper ▾</div></div></div>
<table class="kv"><tr>{kv("Cost", money(cost))}{kv("Mid now", f"{mid_now:.2f}")}</tr>
<tr>{kv("P/L now", f"<span class='{cls(pl)}'>{'−' if pl<0 else '+'}{money(abs(pl))} ({sgn(pl/cost*100,1,'%')})</span>")}{kv("Break-evens (short expiry)", f"{lo:,.0f} – {hi:,.0f}")}</tr>
<tr>{kv("Entry snapshot", f"SPX {PREV['S']:,.0f} · skew {sgn(skew0)}")}{kv("Snapshot source", "<span class=muted>nearest saved refresh, Jan 11 4:15 PM</span>")}</tr></table>
{note_box("", 'Why this one, e.g. "placed in TOS during the CPI dip"', "Notes (optional; grows as you type)")}
<div style="margin-top:16px;display:flex;gap:10px;justify-content:space-between"><span class="btn">⇩ Paste again</span><span><span class="btn">Cancel</span> <span class="btn primary">Confirm</span></span></div>
<div class="muted" style="margin-top:10px;font-size:12px">Saved with price source "pasted". Green border: the line was read. If it can't be read, the border turns red and says which part is wrong (e.g. a call calendar, or an expiry that isn't an SPXW Friday).</div></div>"""

# ---------------------------------------------------------------- Performance (simulated closed trades)
random.seed(7)
def simulate(n=36):
    trades, d = [], date(2027, 1, 4)
    while len(trades) < n:
        for wd in random.sample(range(5), random.choice([2, 3])):
            e = d + timedelta(days=wd)
            if e in HOLIDAYS or len(trades) >= n: continue
            skew = round(random.gauss(0.25, 0.7), 2)
            vix = round(random.uniform(13, 23), 1)
            siv = round(vix + random.gauss(-1.0, 1.5), 1)
            vol_against = random.random() < 0.45
            win = random.random() < 0.40
            mfe = random.uniform(10, 16) if win else random.choice([random.uniform(0, 3), random.uniform(3, 9)])
            pl = random.uniform(10, 12) if win else random.uniform(-12, -10) if random.random() < 0.6 else random.uniform(-6, 4)
            days = random.randint(1, 4) if win else random.randint(3, 7)
            while (e + timedelta(days=days)).weekday() >= 5 or (e + timedelta(days=days)) in HOLIDAYS: days += 1
            cost = round(random.uniform(9_800, 11_200)); width = random.choice(WIDTHS); sdte = random.choice([10, 17, 24, 31, 38, 45, 52])
            t3 = random.randint(1, max(1, days - 1)) if mfe >= 3 else None
            trades.append(dict(entry=e, width=width, sdte=sdte, skew=skew, vix=vix, siv=siv, vol_against=vol_against, pl_pct=pl,
                               pl=pl / 100 * cost, days=days, mfe=mfe, flag="target" if pl >= 10 else "loss" if pl <= -10 else None,
                               t3=t3, t5=(t3 + random.randint(0, 1)) if mfe >= 5 else None, t10=days if mfe >= 10 else None))
        d += timedelta(days=7)
    return trades

def risk_profile(K, se, le, today, price, n, v_s, v_l, s_now, title, now_pl=None, extra_days=(), size=(9.6, 3.0)):
    """P/L across SPX: today (both legs at their current IV) and at the short expiry (long leg priced with Black-Scholes)."""
    xs = list(range(int(K) - 320, int(K) + 321, 4))
    ds, dl, w = (se - today).days, (le - today).days, (le - se).days
    pl_now = [((bs_put(x, K, dl / 365, v_l)[0] - bs_put(x, K, ds / 365, v_s)[0]) - price) * 100 * n for x in xs]
    pl_exp = [(value_at_short_expiry(x, K, w, v_l) - price) * 100 * n for x in xs]
    lo, hi = break_evens(K, se, le, v_l, price)
    fig, ax = plt.subplots(figsize=size)
    ax.plot(xs, pl_exp, color="#FF4B4B", lw=2, label=f"At short expiry ({se:%b %-d})")
    for d, col in zip(extra_days, ("#C792EA", "#4FD1C5")):
        pl_d = [((bs_put(x, K, (dl - d) / 365, v_l)[0] - bs_put(x, K, (ds - d) / 365, v_s)[0]) - price) * 100 * n for x in xs]
        ax.plot(xs, pl_d, color=col, lw=1.4, ls="-.", label=f"+{d} days ({today + timedelta(days=d):%b %-d})")
    ax.plot(xs, pl_now, color="#6CA0FF", lw=1.6, ls="--", label="Today")
    ax.axhline(0, color="#4A4D5A", lw=.8); ax.axvline(s_now, color="#A3A8B8", lw=.8, ls=":")
    ax.text(s_now, ax.get_ylim()[1], f" SPX {s_now:,.0f}", color="#A3A8B8", fontsize=8, va="top")
    for be in (lo, hi):
        ax.plot([be], [0], marker="o", color="#FFC94D", ms=5); ax.text(be, 0, f"  {be:,.0f}", color="#FFC94D", fontsize=8, va="bottom")
    if now_pl is not None:
        ax.plot([s_now], [now_pl], marker="o", color="#6CA0FF", ms=6)
    ax.set_title(title, loc="left", fontsize=10, color="#FAFAFA"); ax.set_xlabel("SPX"); ax.set_ylabel("P/L ($)")
    ax.grid(color="#262730"); lg = ax.legend(frameon=False, loc="lower center", ncol=3, fontsize=8)
    for t in lg.get_texts(): t.set_color("#A3A8B8")
    return svg(fig)

def svg(fig):
    b = io.StringIO(); fig.savefig(b, format="svg", bbox_inches="tight"); plt.close(fig)
    return b.getvalue()[b.getvalue().index("<svg"):]

def performance_body(tab="Summary", cond="Width (days)"):
    random.seed(7)
    T = simulate()
    wins = [t for t in T if t["pl"] > 0]; losses = [t for t in T if t["pl"] <= 0]
    total = sum(t["pl"] for t in T)
    summ = [("Closed trades", f"{len(T)}"), ("Win rate", f"{len(wins)/len(T)*100:.0f}%"),
            ("Avg win", money(statistics.mean(t['pl'] for t in wins))), ("Avg loss", "−" + money(abs(statistics.mean(t['pl'] for t in losses)))),
            ("Expectancy / trade", ('−' if total < 0 else '+') + money(abs(total / len(T)))), ("Total P/L", ('−' if total < 0 else '+') + money(abs(total))),
            ("Avg days held", f"{statistics.mean(t['days'] for t in T):.1f}"),
            ("+10% / −10% hits", f"{sum(t['flag']=='target' for t in T)} / {sum(t['flag']=='loss' for t in T)}")]
    metrics = "".join(f'<div class="card metric" style="padding:10px 12px"><div class="lab">{a}</div><div class="val" style="font-size:21px">{b}</div></div>' for a, b in summ)

    GROUPS = {}
    def group(title, keyf, order):
        GROUPS[title] = (keyf, order)
        rows = ""
        for k in order:
            g = [t for t in T if keyf(t) == k]
            if not g: continue
            wr = sum(t["pl"] > 0 for t in g) / len(g) * 100; avg = statistics.mean(t["pl"] for t in g)
            rows += f"<tr><td class=l>{k}</td><td>{len(g)}</td><td>{wr:.0f}%</td><td class='{cls(avg)}'>{'−' if avg<0 else '+'}{money(abs(avg))}</td><td>{statistics.mean(t['days'] for t in g):.1f}</td></tr>"
        return f"<div><div style='font-weight:600;margin-bottom:5px'>{title}</div><table><tr><th class=l>Bucket</th><th>Trades</th><th>Win rate</th><th>Avg P/L</th><th>Avg days</th></tr>{rows}</table></div>"
    groups = "".join([
        group("Skew at entry", lambda t: "Below 0" if t["skew"] < 0 else "0 to +1" if t["skew"] <= 1 else "Above +1", ["Below 0", "0 to +1", "Above +1"]),
        group("VIX at entry", lambda t: "Under 15" if t["vix"] < 15 else "15–20" if t["vix"] <= 20 else "Over 20", ["Under 15", "15–20", "Over 20"]),
        group("Vol at entry", lambda t: "Moved against spread" if t["vol_against"] else "Not against", ["Moved against spread", "Not against"]),
        group("Entry day", lambda t: t["entry"].strftime("%a"), ["Mon", "Tue", "Wed", "Thu", "Fri"]),
        group("Short DTE at entry", lambda t: "7–14" if t["sdte"] <= 14 else "15–28" if t["sdte"] <= 28 else "29–42" if t["sdte"] <= 42 else "43–56", ["7–14", "15–28", "29–42", "43–56"]),
        group("Days in trade", lambda t: f"{t['days']} day{'s' if t['days'] != 1 else ''}", [f"{d} day{'s' if d != 1 else ''}" for d in range(1, 10)]),
        group("Width (days)", lambda t: f"{t['width']} days", [f"{w} days" for w in WIDTHS]),
    ])
    ex = ""
    for lab, key in (("+3%", "t3"), ("+5%", "t5"), ("+10%", "t10")):
        hit = [t for t in T if t[key]]
        ex += f"<tr><td class=l>{lab}</td><td>{len(hit)} of {len(T)} ({len(hit)/len(T)*100:.0f}%)</td><td>{statistics.mean(t[key] for t in hit):.1f}</td></tr>"
    extab = f"<div><div style='font-weight:600;margin-bottom:5px'>Exit-target comparison</div><table><tr><th class=l>First reached</th><th>Trades</th><th>Avg days to reach</th></tr>{ex}</table></div>"

    def period_table(title, keyf, label):
        keys = sorted({keyf(t) for t in T})
        rows = ""
        for k in keys:
            g = [t for t in T if keyf(t) == k]
            w = sum(t["pl"] > 0 for t in g); pl = sum(t["pl"] for t in g)
            rows += (f"<tr><td class=l>{label(k)}</td><td>{len(g)}</td><td class=pos>{w}</td><td class=neg>{len(g)-w}</td>"
                     f"<td>{w/len(g)*100:.0f}%</td><td class='{cls(pl)}'>{'−' if pl<0 else '+'}{money(abs(pl))}</td><td>{statistics.mean(t['days'] for t in g):.1f}</td></tr>")
        return (f"<div><div style='font-weight:600;margin-bottom:5px'>{title}</div><table><tr><th class=l>Period</th><th>Trades</th><th>Wins</th>"
                f"<th>Losses</th><th>Win rate</th><th>P/L</th><th>Avg days</th></tr>{rows}</table></div>")
    month_key = lambda t: (t["entry"].year, t["entry"].month)
    week_key = lambda t: t["entry"] - timedelta(days=t["entry"].weekday())
    monthly = period_table("Monthly performance", month_key, lambda k: date(k[0], k[1], 1).strftime("%b %Y"))
    weekly = period_table("Weekly performance", week_key, lambda k: "Week of " + k.strftime("%b %-d"))
    filters = (f'<div class="row" style="align-items:center;gap:18px;margin-bottom:14px">'
               f'<div><div class="muted" style="font-size:12.5px;margin-bottom:4px">Period</div><div class="select">All closed trades ▾</div></div>'
               f'<div><div class="muted" style="font-size:12.5px;margin-bottom:4px">Group by</div><div class="seg"><span>Month</span><span class="on">Week</span></div></div>'
               f'<div class="muted" style="font-size:12.5px;padding-top:18px">{min(t["entry"] for t in T):%b %-d} – {max(t["entry"] for t in T):%b %-d, %Y} · '
               f'other periods: This month, Last 4 weeks, Custom range</div></div>')

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#4A4D5A", "axes.labelcolor": "#A3A8B8", "xtick.color": "#A3A8B8", "ytick.color": "#A3A8B8", "figure.facecolor": "#0E1117", "axes.facecolor": "#0E1117", "savefig.facecolor": "#0E1117"})
    Ts = sorted(T, key=lambda t: t["entry"]); cum, s = [], 0
    for t in Ts: s += t["pl"]; cum.append(s)
    f1, a1 = plt.subplots(figsize=(6.2, 2.7)); a1.plot([t["entry"] for t in Ts], cum, color="#FF4B4B", lw=2)
    a1.axhline(0, color="#4A4D5A", lw=.8); a1.set_title("Cumulative P/L ($)", loc="left", fontsize=10, color="#FAFAFA")
    a1.grid(axis="y", color="#262730"); f1.autofmt_xdate()
    f2, a2 = plt.subplots(figsize=(6.2, 2.7))
    a2.scatter([t["skew"] for t in T], [t["pl_pct"] for t in T], s=22, color=["#3DD56D" if t["pl"] > 0 else "#FF6C6C" for t in T])
    a2.axhline(0, color="#4A4D5A", lw=.8); a2.axvline(0, color="#4A4D5A", lw=.8)
    a2.set_xlabel("Skew at entry (vol pts)"); a2.set_ylabel("P/L %"); a2.set_title("P/L % vs entry skew", loc="left", fontsize=10, color="#FAFAFA")
    a2.grid(color="#262730")
    wk = sorted({week_key(t) for t in T})
    wins_w = [sum(1 for t in T if week_key(t) == k and t["pl"] > 0) for k in wk]
    loss_w = [sum(1 for t in T if week_key(t) == k and t["pl"] <= 0) for k in wk]
    f3, a3 = plt.subplots(figsize=(12.6, 2.6)); xs = range(len(wk))
    a3.bar([x - 0.2 for x in xs], wins_w, width=0.4, color="#3DD56D", label="Wins")
    a3.bar([x + 0.2 for x in xs], loss_w, width=0.4, color="#FF6C6C", label="Losses")
    a3.set_xticks(list(xs)); a3.set_xticklabels([k.strftime("%b %-d") for k in wk], fontsize=8)
    a3.set_yticks(range(0, max(wins_w + loss_w) + 1)); a3.grid(axis="y", color="#262730")
    a3.set_title("Wins and losses by week", loc="left", fontsize=10, color="#FAFAFA")
    lg = a3.legend(frameon=False, loc="upper right", ncol=2)
    for txt in lg.get_texts(): txt.set_color("#A3A8B8")
    subtabs = "".join(f'<div class="tab{" on" if t == tab else ""}" style="font-size:14px">{t}</div>' for t in ("Summary", "By period", "By condition", "Exits", "Trades"))
    head = filters + f'<div class="tabs" style="gap:22px;margin-bottom:16px">{subtabs}</div>'
    if tab == "Summary":
        f1.set_size_inches(9.6, 2.6)
        f3.set_size_inches(9.6, 2.6)
        return f"""{head}<div style="display:grid;grid-template-columns:repeat(4, 200px);gap:10px">{metrics}</div>
<div class="card" style="margin-top:16px;width:fit-content">{svg(f3)}</div>
<div class="card" style="margin-top:12px;width:fit-content">{svg(f1)}</div>
<div class="muted" style="margin-top:8px;font-size:12px">By period: monthly and weekly tables · By condition: one grouping at a time, with a chart · Exits: exit-target comparison · Trades: closed-trade list and CSV export.</div>"""
    if tab == "By period":
        mk = sorted({month_key(t) for t in T})
        mpl = [sum(t["pl"] for t in T if month_key(t) == k) for k in mk]
        wpl = [sum(t["pl"] for t in T if week_key(t) == k) for k in wk]
        f5, a5 = plt.subplots(figsize=(9.6, 2.5))
        a5.bar(range(len(wk)), wpl, color=["#3DD56D" if v > 0 else "#FF6C6C" for v in wpl], width=0.6)
        a5.set_xticks(range(len(wk))); a5.set_xticklabels([k.strftime("%b %-d") for k in wk], fontsize=8)
        a5.axhline(0, color="#4A4D5A", lw=.8); a5.grid(axis="y", color="#262730")
        a5.set_title("P/L by week ($)", loc="left", fontsize=10, color="#FAFAFA")
        best = max(zip(wpl, wk)); worst = min(zip(wpl, wk))
        note = (f"Best week: {best[1]:%b %-d} ({'+' if best[0]>=0 else '−'}{money(abs(best[0]))}) · Worst week: {worst[1]:%b %-d} "
                f"({'−' if worst[0]<0 else '+'}{money(abs(worst[0]))}) · Weeks with a profit: {sum(v > 0 for v in wpl)} of {len(wpl)}")
        return f"""{head}<div class="card" style="width:fit-content">{svg(f5)}</div>
<div class="muted" style="margin:8px 0 16px;font-size:12.5px">{note}</div>
<div style="display:flex;flex-direction:column;gap:18px;width:fit-content">{monthly}{weekly}</div>
<div class="muted" style="margin-top:8px;font-size:12px">The Group by switch sets the chart (Month or Week). Trades count in the period they were opened.</div>"""
    if tab == "Exits":
        hits = [(lab, [t for t in T if t[key]]) for lab, key in (("+3%", "t3"), ("+5%", "t5"), ("+10%", "t10"))]
        f6, a6 = plt.subplots(figsize=(4.6, 2.6))
        a6.bar([h[0] for h in hits], [len(h[1]) / len(T) * 100 for h in hits], color="#6CA0FF", width=0.55)
        a6.set_ylabel("% of trades"); a6.set_ylim(0, 100); a6.grid(axis="y", color="#262730")
        a6.set_title("How often each target was reached", loc="left", fontsize=10, color="#FAFAFA")
        f7, a7 = plt.subplots(figsize=(4.6, 2.6))
        bins = list(range(0, 18, 2))
        a7.hist([[t["mfe"] for t in T if t["pl"] > 0], [t["mfe"] for t in T if t["pl"] <= 0]], bins=bins, stacked=True,
                 color=["#3DD56D", "#FF6C6C"], label=["Winners", "Losers"], edgecolor="#0E1117")
        a7.set_xlabel("Best P/L % reached while open"); a7.set_ylabel("Trades"); a7.grid(axis="y", color="#262730")
        a7.set_title("Best P/L % reached during the trade", loc="left", fontsize=10, color="#FAFAFA")
        lg = a7.legend(frameon=False, fontsize=8)
        for txt in lg.get_texts(): txt.set_color("#A3A8B8")
        gave_back = [t for t in T if t["mfe"] >= 5 and t["pl"] <= 0]
        ex2 = ""
        for lab, h in hits:
            ex2 += (f"<tr><td class=l>{lab}</td><td>{len(h)} of {len(T)} ({len(h)/len(T)*100:.0f}%)</td><td>{statistics.mean(t[{'+3%':'t3','+5%':'t5','+10%':'t10'}[lab]] for t in h):.1f}</td>"
                    f"<td>{sum(t['pl'] <= 0 for t in h)}</td></tr>")
        extab2 = (f"<table><tr><th class=l>Target (first reached)</th><th>Trades</th><th>Avg days to reach</th><th>Later closed at a loss</th></tr>{ex2}</table>")
        return f"""{head}<div style="font-weight:600;margin-bottom:6px">Exit-target comparison</div>{extab2}
<div class="muted" style="margin:8px 0 16px;font-size:12.5px">{len(gave_back)} losing trades were up 5% or more at some point. A lower target would have closed them as winners; the trade-off is smaller wins on the rest.</div>
<div class="row" style="gap:16px;align-items:flex-start"><div class="card">{svg(f6)}</div><div class="card">{svg(f7)}</div></div>
<div class="muted" style="margin-top:8px;font-size:12px">Based on the P/L recorded at each refresh while the trade was open, so a move between refreshes can be missed.</div>"""
    if tab == "Trades":
        rows = ""
        for i, t in enumerate(sorted(T, key=lambda t: t["entry"], reverse=True)[:14]):
            why = "+10% target" if t["flag"] == "target" else "−10% flag" if t["flag"] == "loss" else "Other"
            rows += (f"<tr><td class=l>{t['entry']:%b %-d}</td><td class=l>{(t['entry'] + timedelta(days=t['days'])):%b %-d}</td><td>{t['days']}</td>"
                     f"<td>{t['width']}d</td><td>{t['sdte']}</td><td>{sgn(t['skew'],2)}</td><td>{t['vix']:.1f}</td>"
                     f"<td class='{cls(t['pl'])}'>{'−' if t['pl']<0 else '+'}{money(abs(t['pl']))}</td><td class='{cls(t['pl_pct'])}'>{sgn(t['pl_pct'],1,'%')}</td><td class=l>{why}</td></tr>")
        tbl = ("<table><tr><th class=l>Opened</th><th class=l>Closed</th><th>Days</th><th>Width</th><th>Short DTE</th><th>Skew</th><th>VIX</th>"
               f"<th>P/L</th><th>P/L %</th><th class=l>Exit</th></tr>{rows}</table>")
        return f"""{head}<div style="width:fit-content"><div class="row" style="justify-content:space-between;align-items:center;margin-bottom:10px;gap:24px">
<div class="row" style="gap:10px;align-items:center"><div class="select" style="min-width:180px">Exit: All ▾</div><div class="select" style="min-width:180px">Width: All ▾</div><span class="muted" style="font-size:12.5px">Showing 14 of {len(T)} · newest first · click a column to sort</span></div>
<span class="btn">⬇ Download CSV</span></div>
{tbl}</div>
<div class="muted" style="margin-top:8px;font-size:12px">Click a row to see the trade's legs, fills and its risk profile at entry. The CSV has every column, including entry IVs, Vol P&L and the TOS order lines.</div>"""
    # By condition: one grouping, chosen with chips, shown as a table plus a bar chart of average P/L
    keyf, order = GROUPS[cond]
    buckets = [k for k in order if any(keyf(t) == k for t in T)]
    avgs = [statistics.mean(t["pl"] for t in T if keyf(t) == k) for k in buckets]
    pcts = [statistics.mean(t["pl_pct"] for t in T if keyf(t) == k) for k in buckets]
    rows = ""
    for k, avg, pct in zip(buckets, avgs, pcts):
        g = [t for t in T if keyf(t) == k]; wr = sum(t["pl"] > 0 for t in g) / len(g) * 100
        rows += (f"<tr><td class=l>{k}</td><td>{len(g)}</td><td>{wr:.0f}%</td><td class='{cls(avg)}'>{'−' if avg<0 else '+'}{money(abs(avg))}</td>"
                 f"<td class='{cls(pct)}'>{sgn(pct,1,'%')}</td><td>{statistics.mean(t['days'] for t in g):.1f}</td></tr>")
    table = f"<table><tr><th class=l>{cond}</th><th>Trades</th><th>Win rate</th><th>Avg P/L</th><th>Avg P/L %</th><th>Avg days</th></tr>{rows}</table>"
    f4, a4 = plt.subplots(figsize=(5.6, 2.8))
    a4.bar(range(len(buckets)), avgs, color=["#3DD56D" if v > 0 else "#FF6C6C" for v in avgs], width=0.6)
    a4.set_xticks(range(len(buckets))); a4.set_xticklabels(buckets, fontsize=8); a4.axhline(0, color="#4A4D5A", lw=.8)
    a4.grid(axis="y", color="#262730"); a4.set_title(f"Average P/L by {cond.lower()}", loc="left", fontsize=10, color="#FAFAFA")
    scatter = f'<div class="card" style="margin-top:14px;width:fit-content">{svg(f2)}</div>' if cond == "Skew at entry" else ""
    chips = "".join(f'<span class="chip {"on" if g == cond else "off"}">{"✓ " if g == cond else ""}{g}</span>' for g in GROUPS)
    return f"""{head}<div class="muted" style="font-size:12.5px;margin-bottom:6px">Group by (one at a time)</div><div class="row" style="gap:8px;flex-wrap:wrap;margin-bottom:16px">{chips}</div>
<div class="row" style="gap:24px;align-items:flex-start">{table}<div class="card">{svg(f4)}</div></div>{scatter}
<div class="muted" style="margin-top:8px;font-size:12px">Average P/L % compares trades fairly when they were sized differently. The P/L-vs-skew scatter appears when Skew at entry is selected.</div>"""

# closed trades: entry date, entry SPX, exit date, target P/L %, price source -> exit SPX solved on a 1-pt grid
CLOSED = [(date(2026, 12, 22), 6790.0, date(2026, 12, 31), 10.6, "auto", 7),   # older than 7 days: hidden by the default filter
          (date(2026, 12, 30), 6868.0, date(2027, 1, 5), 10.4, "auto", 7),
          (date(2026, 12, 31), 6801.0, date(2027, 1, 7), 3.2, "manual", 6),
          (date(2027, 1, 4), 6846.0, date(2027, 1, 8), -10.3, "auto", 4)]

def closed_rows(days=None):
    out = ""; v = (0.141, 0.138)
    for d0, S0, d1, tgt, src, w in CLOSED:
        if days and d1 < NOW.date() - timedelta(days=days): continue
        S1 = solve(tgt, lambda x: value_trade(d0, S0, v, d1, x, v, w), range(int(S0) - 300, int(S0) + 301))
        t = value_trade(d0, S0, v, d1, S1, v, w)
        why = "+10% target" if t["plp"] >= 10 else "−10% flag" if t["plp"] <= -10 else "Other"
        out += (f"<tr><td class=l>{t['K']:,} P · {dstr(t['se'])}/{dstr(t['le'])} · {(t['le'] - t['se']).days}d · {t['n']}×</td><td class=l>{d0:%b %-d} @ {S0:,.0f}</td><td class=l>{d1:%b %-d} @ {S1:,.0f}</td>"
                f"<td>{(d1-d0).days}</td><td class='{cls(t['pl'])}'>{'−' if t['pl']<0 else '+'}{money(abs(t['pl']))} ({sgn(t['plp'],1,'%')})</td><td class=l>{why}</td><td class=l>{src}</td></tr>")
    return out

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True); BUILD.mkdir(exist_ok=True)
    pages = {
        "finder": page("Finder", finder_body(), "simulated SPX chain priced with Black-Scholes; not real quotes.", finder_sidebar()),
        "finder-collapsed": page("Finder", finder_body(collapsed=True), "simulated SPX chain priced with Black-Scholes; not real quotes."),
        "open-trade": dialog_page(dialog_body(), "simulated SPX chain priced with Black-Scholes; not real quotes."),
        "paste-trade": dialog_page(paste_dialog_body(), "simulated quotes; not a real trade."),
        "notes": dialog_page(notes_body(), "simulated paper trade; example notes."),
        "close-trade": dialog_page(close_dialog_body(), "simulated paper trade; not real quotes or results."),
        "holdings": page("Holdings", holdings_body(), "simulated paper trades; not real quotes or results."),
        "holdings-columns": page("Holdings", holdings_body(columns_open=True, on=[k for k, *_ in HCOLS if k not in ("account", "vega")]), "simulated paper trades; not real quotes or results."),
        "performance": page("Performance", performance_body("Summary"), "36 randomly simulated trades to show the layout; not real results and not evidence of an edge."),
        "performance-conditions": page("Performance", performance_body("By condition", "Width (days)"), "36 randomly simulated trades to show the layout; not real results and not evidence of an edge."),
        "performance-skew": page("Performance", performance_body("By condition", "Skew at entry"), "36 randomly simulated trades to show the layout; not real results and not evidence of an edge."),
        "performance-period": page("Performance", performance_body("By period"), "36 randomly simulated trades to show the layout; not real results and not evidence of an edge."),
        "performance-exits": page("Performance", performance_body("Exits"), "36 randomly simulated trades to show the layout; not real results and not evidence of an edge."),
        "performance-trades": page("Performance", performance_body("Trades"), "36 randomly simulated trades to show the layout; not real results and not evidence of an edge."),
    }
    with sync_playwright() as p:
        chrome = os.environ.get("CHROME_PATH")  # optional: use an installed Chrome instead of Playwright's Chromium
        b = p.chromium.launch(executable_path=chrome) if chrome else p.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=1.5)
        for name, html in pages.items():
            (BUILD / f"{name}.html").write_text(html, encoding="utf-8")
            pg.set_content(html); pg.wait_for_timeout(300)
            if 'class="shot"' in html: pg.locator(".shot").screenshot(path=str(OUT / f"{name}.png"))   # dialogs: just the dialog
            else: pg.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            print(f"wrote docs/images/{name}.png")
        b.close()
