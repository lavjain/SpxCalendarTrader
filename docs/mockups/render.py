"""Build mockup pages in the app's style (FastAPI + Jinja templates, Tailwind, dark theme) from data.py and screenshot them.

Run from the repo root:  uv run --group mockups python docs/mockups/render.py
Writes docs/images/*.png and, for quick browser previews, docs/mockups/build/*.html."""
import io, math, os, random, re, statistics
import matplotlib.ticker
from pathlib import Path
from datetime import date, datetime, timedelta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from playwright.sync_api import sync_playwright
from data import *

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "images"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#475569", "axes.labelcolor": "#94A3B8", "xtick.color": "#94A3B8", "ytick.color": "#94A3B8", "figure.facecolor": "#020617", "axes.facecolor": "#020617", "savefig.facecolor": "#020617"})
BUILD = HERE / "build"
NOW = datetime(2027, 1, 12, 11, 5)
S_NOW, ATM_S, ATM_L = 6850.0, 0.141, 0.138

CSS = """
*{box-sizing:border-box} body{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif;color:#F1F5F9;background:#020617;font-size:14px}
.wrap{width:1400px;padding:20px 28px 32px}
.banner{background:#3B3317;border:1px solid #7A6420;color:#F5D97A;padding:7px 12px;border-radius:6px;font-size:12.5px;margin-bottom:14px}
h1{font-size:30px;margin:0 0 4px;font-weight:700} .sub{color:#94A3B8;font-size:13px;margin-bottom:14px}
.tabs{display:flex;gap:28px;border-bottom:1px solid #1E293B;margin-bottom:18px}
.tab{padding:8px 0;color:#F1F5F9;font-size:15px} .tab.on{color:#1C83E1;border-bottom:2px solid #1C83E1;font-weight:600}
.row{display:flex;gap:16px;align-items:flex-start}
.btn{display:inline-block;white-space:nowrap;border:1px solid #475569;border-radius:8px;padding:7px 14px;background:#1E293B;color:#E2E8F0;font-size:14px}
.btn.primary{background:#334155;color:#FFFFFF;border-color:#64748B;font-weight:600}
h3{font-size:17px;margin:18px 0 8px;font-weight:600}
table{border-collapse:collapse;font-size:12.5px;font-variant-numeric:tabular-nums}
th{background:#0F172A;color:#94A3B8;font-weight:600;font-size:11.5px;text-align:right;padding:7px 10px;border:none;border-bottom:1px solid #334155;white-space:nowrap}
td{padding:6px 10px;border:none;border-bottom:1px solid #172033;text-align:right;white-space:nowrap}
th.l,td.l{text-align:left}
tr.best td{background:rgba(252,211,77,.07)} tr.best td:first-child{box-shadow:inset 3px 0 0 #FCD34D}
tr.sel td{background:rgba(28,131,225,.16)} tr.sel td:first-child{box-shadow:inset 3px 0 0 #1C83E1}
.pos{color:#4ADE80} .neg{color:#F87171} .muted{color:#94A3B8}
.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11.5px;font-weight:600}
.pill.red{background:#4A1D1F;color:#FCA5A5} .pill.green{background:#173D24;color:#86EFAC} .pill.amber{background:#45360F;color:#FCD34D}
.card{border:1px solid #1E293B;background:#020617;border-radius:10px;padding:14px 16px}
.card .muted{white-space:nowrap}
.filters{display:grid;grid-template-columns:minmax(320px,1fr) minmax(320px,1fr);gap:20px 48px;margin-bottom:6px;padding:16px 20px} .metric .lab{font-size:12.5px;color:#94A3B8} .metric .val{font-size:26px;font-weight:600;margin-top:2px}
.overlay{position:absolute;inset:0;background:rgba(0,0,0,.6)}
.modal{position:absolute;left:50%;top:120px;transform:translateX(-50%);width:760px;background:#0F172A;border:1px solid #1E293B;border-radius:12px;padding:22px 26px;box-shadow:0 12px 40px rgba(0,0,0,.5)}
.input{border:1px solid #475569;border-radius:8px;padding:7px 10px;width:140px;font-size:15px;background:#1E293B;color:#F1F5F9}
.status{padding:9px 12px;border-radius:8px;font-size:13px}
.status.ok{background:#173D24;color:#86EFAC}
.code{font-family:"DejaVu Sans Mono",monospace;font-size:12.5px;background:#1E293B;border:1px solid #1E293B;border-radius:8px;padding:8px 10px;color:#E2E8F0}
.seg{display:inline-flex;white-space:nowrap;border:1px solid #475569;border-radius:8px;overflow:hidden} .seg span{padding:6px 14px;font-size:13.5px} .seg span.on{background:#1C83E1;color:#fff}
.select{display:inline-block;border:1px solid #475569;border-radius:8px;padding:6px 12px;background:#1E293B;font-size:13.5px;min-width:230px}
.chip{display:inline-block;white-space:nowrap;border:1px solid #475569;border-radius:14px;padding:4px 12px;font-size:13px} .chip.on{background:#1C83E1;border-color:#1C83E1;color:#fff} .chip.off{color:#94A3B8}
.toast{display:inline-block;background:#0F172A;border:1px solid #1E293B;border-radius:8px;padding:8px 12px;font-size:13px}
.kv td{border:none;padding:3px 14px 3px 0;text-align:left;font-size:13.5px}
.kv td:first-child{color:#94A3B8}
.appbar{display:flex;align-items:center;gap:28px;height:56px;padding:0 28px;background:#0F172A;border-bottom:1px solid #1E293B}
.appbar .brand{font-size:17px;font-weight:700;letter-spacing:-.01em} .appbar .ver{font-size:11px;color:#94A3B8;border:1px solid #334155;border-radius:6px;padding:1px 6px;margin-left:8px;font-weight:500}
.appbar .nav{display:flex;gap:4px;height:100%} .appbar .nav div{display:flex;align-items:center;padding:0 14px;color:#94A3B8;font-size:14.5px;border-bottom:2px solid transparent}
.appbar .nav div.on{color:#F1F5F9;border-bottom-color:#1C83E1;font-weight:600}
.appbar .right{margin-left:auto;display:flex;align-items:center;gap:12px;font-size:12.5px;color:#94A3B8}
.appbar .acct{border:1px solid #334155;border-radius:999px;padding:3px 10px;color:#E2E8F0}
.appbar .theme{border:1px solid #334155;border-radius:8px;padding:4px 10px;color:#E2E8F0}
.info{display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;border:1px solid #475569;border-radius:50%;font-size:10px;font-weight:600;color:#94A3B8;margin-left:6px;vertical-align:1px;font-style:normal;font-family:Georgia,serif}
.pop{position:absolute;z-index:6;width:330px;background:#0F172A;border:1px solid #334155;border-radius:10px;padding:12px 14px;font-size:12.5px;line-height:1.45;color:#CBD5E1;box-shadow:0 10px 30px rgba(0,0,0,.55);white-space:normal;font-weight:400}
.pop b{color:#F1F5F9} .pop .store{margin-top:8px;padding-top:8px;border-top:1px solid #1E293B;color:#94A3B8}
.grid2{display:grid;grid-template-columns:808px 516px;gap:20px;align-items:start}
.box{background:#0B1222;border:1px solid #1E293B;border-radius:12px;padding:12px 14px}
.box h3{margin:0 0 10px} .box table{width:100%}
.panel{background:#0F172A;border:1px solid #1E293B;border-radius:12px;padding:14px 16px}
.panel svg{width:100%;height:auto;display:block}
.ptitle{font-size:16px;font-weight:700} .psub{font-size:12.5px;color:#94A3B8;margin-top:2px}
.ptabs{display:flex;gap:18px;border-bottom:1px solid #1E293B;margin:12px 0 10px}
.ptabs div{padding:7px 0;color:#94A3B8;font-size:13.5px;border-bottom:2px solid transparent} .ptabs div.on{color:#F1F5F9;border-bottom-color:#1C83E1;font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:10px}
.tile{min-width:0;overflow:hidden;border:1px solid #1E293B;border-radius:9px;padding:7px 10px;background:#0B1222} .tile .lab{font-size:11.5px;color:#94A3B8;white-space:nowrap} .tile .val{font-size:14.5px;font-weight:600;margin-top:2px;white-space:nowrap}
.fbar{display:flex;align-items:flex-start;gap:16px;padding:10px 16px;background:#0F172A;border:1px solid #1E293B;border-radius:12px;margin-bottom:8px}
.fbar .grp{display:flex;align-items:center;gap:7px} .fbar .gl{font-size:12px;color:#94A3B8;white-space:nowrap}
.fbar .chip{padding:3px 10px;font-size:12.5px}
.strip{display:flex;gap:20px;align-items:baseline;padding:4px 4px 12px;font-size:13px;color:#94A3B8;white-space:nowrap} .strip b{color:#F1F5F9;font-weight:600}
.ladder{margin:0 0 4px 10px;border-left:3px solid #1C83E1;padding:6px 0 2px 10px;background:rgba(28,131,225,.05);border-radius:0 8px 8px 0}
.ladder table th{background:transparent;font-size:11px;padding:5px 8px} .ladder table td{padding:5px 8px;font-size:12px}
tr.seghead td{background:#0F172A;color:#F1F5F9;font-weight:600;text-align:left;padding-top:9px;box-shadow:none}
.hint{font-size:11.5px;color:#64748B;margin-top:8px}
.tbtn{display:inline-block;border:1px solid #334155;border-radius:7px;padding:3px 9px;font-size:12px;color:#CBD5E1;white-space:nowrap}
.tbtn.on{border-color:#1C83E1;color:#fff;background:rgba(28,131,225,.25)}
.two{font-size:11px;color:#94A3B8;display:block;margin-top:1px}
.btnrow{display:flex;gap:8px;align-items:center}
.btn.blue{background:#1C83E1;border-color:#1C83E1;color:#fff;font-weight:600}
.footer{margin-top:30px;padding-top:12px;border-top:1px solid #1E293B;font-size:12px;color:#64748B}
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

INFO = '<i class="info">i</i>'

def add_info(html):
    """Every section heading and tile gets a small ⓘ that opens a popover explaining it (rule 5 in CLAUDE.md)."""
    html = re.sub(r'(<h3[^>]*>)([^<]+?)(\s*)(<span|</h3>)', lambda m: f"{m[1]}{m[2]}{INFO}{m[3]}{m[4]}", html)
    return re.sub(r'(<div class="lab">)([^<]+)(</div>)', lambda m: f"{m[1]}{m[2]}{INFO}{m[3]}", html)

def appbar(active):
    tabs = "".join(f'<div class="{"on" if t == active else ""}">{t}</div>' for t in ("Finder", "Holdings", "Performance"))
    return (f'<div class="appbar"><div><span class="brand">SPX Calendar Trader</span><span class="ver">v0.1.0</span></div>'
            f'<div class="nav">{tabs}</div><div class="right"><span>Paper trading · no orders sent · prices from Schwab</span>'
            f'<span class="acct">Account: Paper</span><span class="theme">☾ Dark</span></div></div>')

FOOTER = ('<div class="footer">SPX Calendar Trader v0.1.0 · paper trading only, no orders are sent · '
          'last refresh 11:05:12 AM ET · data: Schwab API · <span style="color:#94A3B8">ⓘ on any tile or heading explains it</span></div>')

def dialog_page(body, mock_note):
    """A dialog on its own, without the screen behind it; the screenshot is cropped to .shot."""
    return add_info(f"""<html><head><meta charset="utf-8"><style>{CSS} .shot .modal{{position:static;transform:none;box-shadow:none}}</style></head><body><div class="shot" style="display:inline-block;padding:24px 28px">"""
            f"""<div class="banner" style="width:760px;box-sizing:border-box;margin-bottom:16px"><b>Mockup</b> · {mock_note}</div>"""
            f"""<div style="position:relative">{body}</div></div></body></html>""")

def page(active, body, mock_note):
    """base.html: _header.html (brand, tabs, account, theme toggle), the page, _footer.html."""
    banner = f'<div class="banner"><b>Mockup</b> · {mock_note}</div>'
    return add_info(f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div style="width:1400px">{appbar(active)}<div class="wrap" style="position:relative;padding-top:18px">{banner}{body}{FOOTER}</div></div></body></html>""")

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


def chip(w):
    if all(F_ALL[(fr, w)]["long_exp"] is None for fr in FRIDAYS):
        return f'<span class="chip off" title="No expiry that day (market holiday)" style="text-decoration:line-through;opacity:.45">{w}d</span>'
    return f'<span class="chip {"on" if w in WIDTHS_ON else "off"}">{"✓ " if w in WIDTHS_ON else ""}{w}d</span>'



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

def spx_chart(bars, n=63, K=None, be=None, se=None, le=None, size=(12.6, 3.5)):
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
    fig, ax = plt.subplots(figsize=size)
    if K is not None:
        ax.axhspan(be[0], be[1], color="#FCD34D", alpha=.07, lw=0)
        for v in be: ax.axhline(v, color="#FCD34D", lw=.7, ls=(0, (2, 3)))
        ax.axhline(K, color="#EF4444", lw=1, ls="--")
        ax.text(len(dates) - .5, K, f" {K:,} strike", color="#EF4444", fontsize=8, va="center")
        ax.text(len(dates) - .5, be[0], f" {be[0]:,.0f} BE", color="#FCD34D", fontsize=8, va="center")
        ax.text(len(dates) - .5, be[1], f" {be[1]:,.0f} BE", color="#FCD34D", fontsize=8, va="center")
    for i, b in enumerate(B):
        col = "#4ADE80" if b["c"] >= b["o"] else "#F87171"
        ax.vlines(i, b["l"], b["h"], color=col, lw=.8)
        ax.bar(i, max(abs(b["c"] - b["o"]), .6), bottom=min(b["o"], b["c"]), color=col, width=.6)
    ax.plot(range(n), s20[off:], color="#6CA0FF", lw=1.2, label="20-day avg")
    ax.plot(range(n), s50[off:], color="#C792EA", lw=1.2, label="50-day avg")
    ax.axvline(n - 1, color="#94A3B8", lw=.8, ls=":")
    lo_y = min([b["l"] for b in B] + ([be[0]] if be else [])); hi_y = max([b["h"] for b in B] + ([be[1]] if be else []))
    pad = (hi_y - lo_y) * .08; ax.set_ylim(lo_y - pad, hi_y + pad * 2.5)     # fit the candles; averages may run off the edge
    for j, (e, lab) in enumerate(((se, "short"), (le, "long"))):
        if e in dates:
            x = dates.index(e); ax.axvline(x, color="#475569", lw=1, ls="--")
            ax.text(x, lo_y - pad * (.3 + .9 * j), f" {lab} {e:%b %-d}", color="#94A3B8", fontsize=8, va="bottom")
    ticks = [i for i, d in enumerate(dates) if d.weekday() == 0 and (d.day <= 7 or n <= 30)] or list(range(0, len(dates), 10))
    ax.set_xticks(ticks); ax.set_xticklabels([dates[i].strftime("%b %-d") for i in ticks], fontsize=8)
    ax.set_xlim(-1, len(dates) + 9); ax.grid(axis="y", color="#1E293B")
    ax.set_title(f"SPX daily · last 3 months · {B[-1]['c']:,.2f}", loc="left", fontsize=10, color="#F1F5F9")
    lg = ax.legend(frameon=False, loc="upper left", fontsize=8, ncol=2)
    for t in lg.get_texts(): t.set_color("#94A3B8")
    return svg(fig)




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
    for row, text in zip(out, NOTE_TEXTS):      # notes follow the trade order, so a change of delta target cannot orphan them
        NOTE[row["K"]] = text
    return out

# Holdings columns: key, label, shown by default, group. "Trade" is always shown and pinned on the left.
HCOLS = [("entered", "Entered", False, "Position"), ("days", "Days", True, "Position"), ("cost", "Cost", False, "Position"),
         ("value", "Value now", False, "Position"), ("account", "Account", False, "Position"),
         ("pl", "P/L", True, "P/L"), ("volpl", "Vol P&L today", True, "P/L"),
         ("be", "Break-evens", True, "Risk"), ("tobe", "To nearest BE", True, "Risk"), ("dpc", "Δ / contract", True, "Risk"),
         ("theta", "Theta / day", False, "Risk"), ("vega", "Vega", False, "Risk"),
         ("siv", "Short IV", False, "Volatility"), ("liv", "Long IV", False, "Volatility"), ("skew", "Skew now", False, "Volatility"),
         ("skew0", "Skew at entry", True, "Volatility"), ("flag", "Flag", True, "Flags & notes"), ("notes", "Notes", True, "Flags & notes")]

NOTE = {}   # strike -> note, filled in by holdings_rows(): the first trade and the second trade each get one
NOTE_TEXTS = ["Entered after skew turned positive (+0.38); VIX 15.8. Sized to $10k.\nJan 11: up 7%. Holding for the +10% target; CPI Wednesday morning, decide before then.",
              "Took this one a day early; SPX was near the 20-day average."]

def note_box(text, placeholder, label):
    """A note box that grows with its text: one line when empty, as many lines as the note needs."""
    body = text.replace("\n", "<br>") if text else f'<span style="color:#94A3B8">{placeholder}</span>'
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
                      else "<td class=l><span class='btn' style='padding:1px 9px;font-size:12px;color:#94A3B8'>✎ Add</span></td>")}[k]

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
    ok = lambda t: f'<div style="color:#4ADE80;font-size:13.5px;margin:3px 0">✓ {t}</div>'
    checks = "".join([ok(f"SPXW expiries {dstr(se)} and {dstr(le)} exist; long leg {(le - se).days} days after the short"),
                      ok(f"Short leg {abs(s0['delta'])*100:.1f}Δ at entry, inside the {config.DELTA_BAND_LABEL} band"),
                      ok("Not already in Holdings")])
    kv = lambda a, b: f"<td>{a}</td><td>{b}</td>"
    return f"""<div class="modal">
<div style="font-size:20px;font-weight:700;margin-bottom:6px">Open trade <span class="muted" style="font-size:14px;font-weight:400">· filled in from TOS</span></div>
<div class="muted" style="font-size:13px;margin-bottom:12px">After ⇩ Paste from TOS: the pasted order replaces what the dialog showed, so a trade placed straight in thinkorswim can be entered from any row. In the Close trade dialog, a pasted SELL line sets the exit price the same way.</div>
<div class="muted" style="font-size:12.5px;margin-bottom:4px">Pasted order line (from TOS: right-click the order → Copy, or the Copy to TOS format)</div>
<div class="code" style="border:1px solid #4ADE80">{PASTED}</div>
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
                         "axes.edgecolor": "#475569", "axes.labelcolor": "#94A3B8", "xtick.color": "#94A3B8", "ytick.color": "#94A3B8", "figure.facecolor": "#020617", "axes.facecolor": "#020617", "savefig.facecolor": "#020617"})
    Ts = sorted(T, key=lambda t: t["entry"]); cum, s = [], 0
    for t in Ts: s += t["pl"]; cum.append(s)
    f1, a1 = plt.subplots(figsize=(6.2, 2.7)); a1.plot([t["entry"] for t in Ts], cum, color="#EF4444", lw=2)
    a1.axhline(0, color="#475569", lw=.8); a1.set_title("Cumulative P/L ($)", loc="left", fontsize=10, color="#F1F5F9")
    a1.grid(axis="y", color="#1E293B"); f1.autofmt_xdate()
    f2, a2 = plt.subplots(figsize=(6.2, 2.7))
    a2.scatter([t["skew"] for t in T], [t["pl_pct"] for t in T], s=22, color=["#4ADE80" if t["pl"] > 0 else "#F87171" for t in T])
    a2.axhline(0, color="#475569", lw=.8); a2.axvline(0, color="#475569", lw=.8)
    a2.set_xlabel("Skew at entry (vol pts)"); a2.set_ylabel("P/L %"); a2.set_title("P/L % vs entry skew", loc="left", fontsize=10, color="#F1F5F9")
    a2.grid(color="#1E293B")
    wk = sorted({week_key(t) for t in T})
    wins_w = [sum(1 for t in T if week_key(t) == k and t["pl"] > 0) for k in wk]
    loss_w = [sum(1 for t in T if week_key(t) == k and t["pl"] <= 0) for k in wk]
    f3, a3 = plt.subplots(figsize=(12.6, 2.6)); xs = range(len(wk))
    a3.bar([x - 0.2 for x in xs], wins_w, width=0.4, color="#4ADE80", label="Wins")
    a3.bar([x + 0.2 for x in xs], loss_w, width=0.4, color="#F87171", label="Losses")
    a3.set_xticks(list(xs)); a3.set_xticklabels([k.strftime("%b %-d") for k in wk], fontsize=8)
    a3.set_yticks(range(0, max(wins_w + loss_w) + 1)); a3.grid(axis="y", color="#1E293B")
    a3.set_title("Wins and losses by week", loc="left", fontsize=10, color="#F1F5F9")
    lg = a3.legend(frameon=False, loc="upper right", ncol=2)
    for txt in lg.get_texts(): txt.set_color("#94A3B8")
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
        a5.bar(range(len(wk)), wpl, color=["#4ADE80" if v > 0 else "#F87171" for v in wpl], width=0.6)
        a5.set_xticks(range(len(wk))); a5.set_xticklabels([k.strftime("%b %-d") for k in wk], fontsize=8)
        a5.axhline(0, color="#475569", lw=.8); a5.grid(axis="y", color="#1E293B")
        a5.set_title("P/L by week ($)", loc="left", fontsize=10, color="#F1F5F9")
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
        a6.set_ylabel("% of trades"); a6.set_ylim(0, 100); a6.grid(axis="y", color="#1E293B")
        a6.set_title("How often each target was reached", loc="left", fontsize=10, color="#F1F5F9")
        f7, a7 = plt.subplots(figsize=(4.6, 2.6))
        bins = list(range(0, 18, 2))
        a7.hist([[t["mfe"] for t in T if t["pl"] > 0], [t["mfe"] for t in T if t["pl"] <= 0]], bins=bins, stacked=True,
                 color=["#4ADE80", "#F87171"], label=["Winners", "Losers"], edgecolor="#020617")
        a7.set_xlabel("Best P/L % reached while open"); a7.set_ylabel("Trades"); a7.grid(axis="y", color="#1E293B")
        a7.set_title("Best P/L % reached during the trade", loc="left", fontsize=10, color="#F1F5F9")
        lg = a7.legend(frameon=False, fontsize=8)
        for txt in lg.get_texts(): txt.set_color("#94A3B8")
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
    a4.bar(range(len(buckets)), avgs, color=["#4ADE80" if v > 0 else "#F87171" for v in avgs], width=0.6)
    a4.set_xticks(range(len(buckets))); a4.set_xticklabels(buckets, fontsize=8); a4.axhline(0, color="#475569", lw=.8)
    a4.grid(axis="y", color="#1E293B"); a4.set_title(f"Average P/L by {cond.lower()}", loc="left", fontsize=10, color="#F1F5F9")
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

# ---------------------------------------------------------------- Screen layouts: filter bar, two columns, side panel
EXP_C, NOW_C, D3_C, D5_C = "#38BDF8", "#F472B6", "#C4B5FD", "#5EEAD4"   # expiry, today (T+0), +3d, +5d: red stays reserved for losses

def risk_graph(K, se, le, today, price, n, v_s, v_l, s_now, now_pl=None, extra_days=(), sd_band=True, size=(6.3, 3.5)):
    """Risk profile as the canvas will paint it: expiry line with profit/loss shading, T+0 dashed, optional +3/+5 days,
    ±1 SD band (from the short leg's IV to its expiry), SPX now, break-evens. Returns (svg, stats)."""
    xs = list(range(int(K) - 300, int(K) + 301, 3))
    ds, dl, w = (se - today).days, (le - today).days, (le - se).days
    pl_now = [((bs_put(x, K, dl / 365, v_l)[0] - bs_put(x, K, ds / 365, v_s)[0]) - price) * 100 * n for x in xs]
    pl_exp = [(value_at_short_expiry(x, K, w, v_l) - price) * 100 * n for x in xs]
    lo, hi = break_evens(K, se, le, v_l, price)
    sd = s_now * v_s * math.sqrt(ds / 365)
    fig, ax = plt.subplots(figsize=size)
    if sd_band:
        ax.axvspan(s_now - sd, s_now + sd, color="#94A3B8", alpha=.08, lw=0)
        for v, lab in ((s_now - sd, "−1σ"), (s_now + sd, "+1σ")):
            ax.axvline(v, color="#64748B", lw=.7, ls=(0, (1, 3)))
    ax.fill_between(xs, pl_exp, 0, where=[v >= 0 for v in pl_exp], color="#4ADE80", alpha=.10, lw=0, interpolate=True)
    ax.fill_between(xs, pl_exp, 0, where=[v < 0 for v in pl_exp], color="#F87171", alpha=.10, lw=0, interpolate=True)
    ax.plot(xs, pl_exp, color=EXP_C, lw=2, label=f"At short expiry {se:%b %-d}")
    for d, col in zip(extra_days, (D3_C, D5_C)):
        pl_d = [((bs_put(x, K, (dl - d) / 365, v_l)[0] - bs_put(x, K, (ds - d) / 365, v_s)[0]) - price) * 100 * n for x in xs]
        ax.plot(xs, pl_d, color=col, lw=1.3, ls="-.", label=f"+{d} days")
    ax.plot(xs, pl_now, color=NOW_C, lw=1.6, ls="--", label="Today (T+0)")
    ax.axhline(0, color="#475569", lw=.8); ax.axvline(s_now, color="#E2E8F0", lw=.8, ls=":")
    top = max(pl_exp + pl_now); bot = min(pl_exp + pl_now)
    ax.set_ylim(bot - (top - bot) * .05, top + (top - bot) * .16)
    ax.text(s_now, ax.get_ylim()[1], f"SPX {s_now:,.0f}", color="#E2E8F0", fontsize=7.5, va="top", ha="center",
            bbox=dict(boxstyle="round,pad=.25", fc="#0F172A", ec="#334155", lw=.6))
    if sd_band:
        for v, lab in ((s_now - sd, f"−1σ {s_now - sd:,.0f}"), (s_now + sd, f"+1σ {s_now + sd:,.0f}")):
            ax.text(v, ax.get_ylim()[1] - (top - bot) * .07, lab, color="#94A3B8", fontsize=7, ha="center", va="top")
    for be in (lo, hi):
        ax.plot([be], [0], marker="o", color="#FCD34D", ms=4.5); ax.text(be, 0, f" {be:,.0f}", color="#FCD34D", fontsize=7.5, va="bottom")
    if now_pl is not None:
        ax.plot([s_now], [now_pl], marker="o", color=NOW_C, ms=6, mec="#0F172A", mew=1)
    ax.set_xlabel("SPX", fontsize=8); ax.tick_params(labelsize=7.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{'−' if v < 0 else ''}${abs(v)/1000:.1f}k" if abs(v) >= 1000 else f"{'−' if v < 0 else ''}${abs(v):.0f}"))
    ax.grid(color="#172033"); ax.set_facecolor("#0F172A"); fig.patch.set_facecolor("#0F172A")
    lg = ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=4, fontsize=7.5)
    for t in lg.get_texts(): t.set_color("#94A3B8")
    i_now = min(range(len(xs)), key=lambda i: abs(xs[i] - s_now))
    stats = dict(cost=price * 100 * n, max_profit=max(pl_exp), max_loss=-price * 100 * n, pl_now=pl_now[i_now], lo=lo, hi=hi, sd=sd)
    return svg(fig), stats

def holiday_note():
    """'Holiday Dec 25 (Christmas Day)' for each holiday near the Finder's DTE range, as the real Finder shows."""
    today = NOW.date(); lo, hi = DTE_RANGE
    near = sorted(h for h in HOLIDAYS if today + timedelta(days=lo) <= h <= today + timedelta(days=hi + 7))
    return "".join(f'<div class="muted" style="font-size:11.5px">Holiday {h:%b} {h.day} ({config.HOLIDAY_NAMES[h.isoformat()]})</div>' for h in near)

def filter_bar():
    lo, hi = DTE_RANGE; x = lambda d: (d - 7) / 49 * 150
    slider = (f'<div style="position:relative;width:150px;height:20px"><div style="position:absolute;top:8px;left:0;right:0;height:4px;background:#1E293B;border-radius:2px"></div>'
              f'<div style="position:absolute;top:8px;left:{x(lo):.0f}px;width:{x(hi)-x(lo):.0f}px;height:4px;background:#1C83E1"></div>'
              + "".join(f'<div style="position:absolute;top:2px;left:{x(v)-8:.0f}px;width:16px;height:16px;border-radius:8px;background:#1C83E1"></div>' for v in (lo, hi)) + '</div>')
    strike_chip = lambda k: f'<span class="chip {"on" if k in STRIKES_ON else "off"}">{"✓ " if k in STRIKES_ON else ""}{k}s</span>'
    grp = lambda label, body: f'<div class="grp"><span class="gl">{label}</span>{body}</div>'
    return (f'<div class="fbar">'
            + grp(f'Short DTE <b style="color:#F1F5F9">{lo}–{hi}</b>', slider)
            + (f'<div class="grp" style="flex-direction:column;align-items:flex-start;gap:4px"><div class="grp"><span class="gl">Days Between</span>'
               + "".join(chip(w) for w in WIDTHS) + f'</div>{holiday_note()}</div>')
            + grp("Strikes", strike_chip("10") + strike_chip("25"))
            + grp("Size by", f'<div class="seg"><span class="on" style="padding:4px 10px;font-size:12.5px">Margin</span><span style="padding:4px 10px;font-size:12.5px">Contracts</span></div>'
                  f'<div class="input" style="width:92px;padding:4px 8px;font-size:13px">{money(MARGIN)}</div>')
            + f'<div style="margin-left:32px;align-self:center" class="btnrow"><span class="btn primary" style="padding:6px 14px">↻ Refresh</span><span class="muted" style="font-size:12px;white-space:nowrap">Updated 8:05:12 AM PST</span></div></div>')

def status_strip(items):
    return '<div class="strip">' + "".join(f'<span>{a} <b>{b}</b></span>' for a, b in items) + '</div>'

def detail_ladder(P):
    hdr = "".join(f"<th>{h}</th>" for h in ["Strike", "Short Δ", "Ctr", "Price", "Margin", "Delta", "Gamma", "Theta", "Vega", "Short IV", "Long IV", "Skew", "T/D", "Θ/Mgn"])
    rows = ""
    for r in P["sec"]:
        c = r["cal"]; star = " ★" if r is P["near"] else ""
        klass = " ".join(k for k, on in (("best", r is P["best"]), ("sel", r["is_sel"])) if on)
        rows += (f"<tr class='{klass}'><td>{r['strike']}{star}</td><td>{abs(r['s']['delta'])*100:.1f}</td><td>{c.contracts}</td><td>{c.debit:.2f}</td>"
                 f"<td>{c.margin:,.0f}</td><td>{c.delta:.1f}</td><td>{c.gamma:.2f}</td><td>{c.theta:.0f}</td><td>{c.vega:.0f}</td>"
                 f"<td>{r['s']['iv']*100:.2f}%</td><td>{r['l']['iv']*100:.2f}%</td><td class='{cls(round(c.skew,2))}'>{sgn(c.skew)}</td><td>{'—' if abs(c.delta) < 0.5 else f'{c.td:.0f}'}</td><td>{c.theta_margin*100:.2f}%</td></tr>")
    return (f"<tr><td colspan=9 style='padding:0;border:none;text-align:left'><div class='ladder'>"
            f"<div style='font-size:12px;color:#94A3B8;margin-bottom:4px'>All {len(P['sec'])} strikes of this pair in the {config.DELTA_BAND_LABEL} band · ★ nearest {config.DELTA_LABEL} · amber edge: highest skew · click a strike to select it</div>"
            f"<table><tr>{hdr}</tr>{rows}</table></div></td></tr>")

def overview_box():
    pairs = {}
    for r in ROWS: pairs.setdefault((r["short_exp"], r["long_exp"]), []).append(r)
    ov = []
    for (se, le), sec in pairs.items():
        near = min([x for x in sec if x["strike"] % config.STAR_STRIKE_MULTIPLE == 0] or sec, key=lambda x: abs(abs(x["s"]["delta"]) - config.DELTA_TARGET)); best = max(sec, key=lambda x: x["cal"].skew)
        ov.append(dict(se=se, le=le, sec=sec, near=near, best=best, sel=any(x["is_sel"] for x in sec)))
    ov.sort(key=lambda p: p["best"]["cal"].skew, reverse=True); top = ov[0]
    hdr = "".join(f"<th{' class=l' if h == 'Short → Long' else ''}>{h}</th>" for h in
                  ["Short → Long", f"~{config.DELTA_LABEL}", "Ctr", "Price", "Theta", "Vega", "Skew", "Θ/Mgn", "Best skew ▼"])
    body = ""
    for w in sorted({p["near"]["width"] for p in ov}):
        seg = [p for p in ov if p["near"]["width"] == w]
        body += f"<tr class='seghead'><td colspan=9>{w}-day width <span style='font-weight:400;color:#94A3B8'>· {len(seg)} pair{'s' if len(seg) != 1 else ''}</span></td></tr>"
        for p in seg:
            c = p["near"]["cal"]; klass = " ".join(k for k, on in (("best", p is top), ("sel", p["sel"])) if on)
            caret = "▾" if p["sel"] else "▸"
            body += (f"<tr class='{klass}'><td class=l><span class=muted>{caret}</span> {p['se']:%a %b %-d} → {p['le']:%a %b %-d}<span class='two' style='padding-left:14px'>{c.s.dte} / {c.l.dte} DTE · {len(p['sec'])} strikes</span></td>"
                     f"<td>{p['near']['strike']}</td><td>{c.contracts}</td><td>{c.debit:.2f}</td><td>{c.theta:.0f}</td><td>{c.vega:.0f}</td>"
                     f"<td class='{cls(round(c.skew,2))}'>{sgn(c.skew)}</td><td>{c.theta_margin*100:.2f}%</td>"
                     f"<td class='{cls(round(p['best']['cal'].skew,2))}'>{sgn(p['best']['cal'].skew)} <span class=muted>@ {p['best']['strike']}</span></td></tr>")
            if p["sel"]: body += detail_ladder(p)
    return (f'<div class="box"><div class="row" style="justify-content:space-between;align-items:baseline"><h3>Calendars <span class="muted" style="font-weight:400;font-size:12.5px">· one row per short/long pair at its ~{config.DELTA_LABEL} strike · sized to {money(MARGIN)}</span></h3>'
            f'<span class="muted" style="font-size:12px">sorted by Best skew</span></div><table>{hdr and "<tr>" + hdr + "</tr>"}{body}</table>'
            f'<div class="hint">Click a pair to open its strikes underneath; click a strike to show it in the panel on the right. Amber edge: highest skew. Blue: selected. Headers sort within each width.</div></div>')

def legs_table(K, se, le, s, l):
    row = lambda name, q, e: (f"<tr><td class=l>{name} <span class=muted>{e:%b %-d} · {q['dte']}d</span></td><td>{q['mark']:.2f}</td>"
                              f"<td>{q['bid']:.2f} / {q['ask']:.2f}</td><td>{q['delta']:.3f}</td><td>{q['vega']:.2f}</td><td>{q['iv']*100:.2f}%</td></tr>")
    return (f"<table style='width:100%'><tr><th class=l>{K} put</th><th>Mark</th><th>Bid / Ask</th><th>Delta</th><th>Vega</th><th>IV</th></tr>"
            f"{row('Short', s, se)}{row('Long', l, le)}</table>"
            f"<div class='strip' style='padding:8px 0 0;gap:16px;font-size:12.5px'><span>Skew <b class='{cls(round((s['iv']-l['iv'])*100,2))}'>{sgn((s['iv']-l['iv'])*100)} pts</b></span>"
            f"<span>IV ratio short / long <b>{s['iv']/l['iv']:.3f}</b></span></div>")

def tiles(items):
    return '<div class="tiles">' + "".join(f'<div class="tile"><div class="lab">{a}</div><div class="val {c}">{b}</div></div>' for a, b, c in items) + '</div>'

def finder_panel(tab="Risk profile"):
    K, se, le = SEL["strike"], F["short_exp"], F["long_exp"]
    mid = round((SEL["bid"] + SEL["ask"]) / 2, 2); price = round(mid + FILL, 2); n = contracts_for(price)
    s, l = SEL["s"], SEL["l"]
    graph, st = risk_graph(K, se, le, NOW.date(), price, n, s["iv"], l["iv"], S_NOW)
    pd = (l["delta"] - s["delta"]) * 100 * n; pt = (l["theta"] - s["theta"]) * 100 * n; pv = (l["vega"] - s["vega"]) * 100 * n
    signed_money = lambda v: ("−" if v < 0 else "+") + money(abs(v))
    t = tiles([("Cost", money(st["cost"]), ""), ("Max profit", signed_money(st["max_profit"]), "pos"), ("Max loss", signed_money(st["max_loss"]), "neg"),
               ("P/L if closed now", signed_money(st["pl_now"]), cls(round(st["pl_now"]))),
               ("Break-evens", f"{st['lo']:,.0f} – {st['hi']:,.0f}", ""), ("Delta", f"{pd:+.1f}", ""), ("Theta / day", signed_money(pt), cls(pt)), ("Vega / pt", signed_money(pv), "")])
    tabs = "".join(f'<div class="{"on" if x == tab else ""}">{x}</div>' for x in ("Risk profile", "SPX chart"))
    if tab == "Risk profile":
        chips = (f'<div class="btnrow" style="flex-wrap:wrap;margin-bottom:8px"><span class="tbtn on">✓ Today</span><span class="tbtn">+3 days</span><span class="tbtn">+5 days</span>'
                 f'<span class="tbtn on">✓ At short expiry</span><span class="tbtn on">✓ ±1 SD</span>'
                 f'<span class="select" style="min-width:0;padding:3px 9px;font-size:12px;margin-left:auto">Range ±300 ▾</span></div>')
        body = chips + graph + t
    else:
        chips = (f'<div class="btnrow" style="flex-wrap:wrap;margin-bottom:8px">' + "".join(f'<span class="tbtn{" on" if x == "3M" else ""}">{x}</span>' for x in ("1M", "3M", "6M", "1Y", "2Y"))
                 + '<span style="width:6px"></span><span class="tbtn on">✓ 20/50-day</span><span class="tbtn on">✓ Strike & BEs</span><span class="tbtn on">✓ Expiries</span></div>')
        body = chips + spx_chart(spx_history(), 63, K, (st["lo"], st["hi"]), se, le, size=(6.3, 3.6))
        bars = spx_history(); c = [b["c"] for b in bars]
        rv = statistics.stdev([math.log(c[i] / c[i - 1]) for i in range(len(c) - 20, len(c))]) * math.sqrt(252) * 100
        hi63 = max(b["h"] for b in bars[-63:])
        body += tiles([("From 3-month high", f"{(c[-1]/hi63-1)*100:+.1f}%", ""), ("5-day change", f"{(c[-1]/c[-6]-1)*100:+.1f}%", ""),
                       ("Realized vol 20d", f"{rv:.1f}%", ""), ("Short IV", f"{s['iv']*100:.1f}%", "")])
    return (f'<div class="panel"><div class="row" style="justify-content:space-between;align-items:flex-start">'
            f'<div><div class="ptitle">SPX {K:,} put calendar</div><div class="psub">short {se:%a %b %-d} → long {le:%a %b %-d} · {(le-se).days}-day width · {n} × {price:.2f} (mid + $0.10)</div></div>'
            f'<span class="btn blue" style="padding:7px 14px">Open trade…</span></div>'
            f'<div class="ptabs">{tabs}</div>{body}'
            f'<h3 style="font-size:14px;margin:14px 0 6px">Legs</h3>{legs_table(K, se, le, s, l)}'
            f'<div class="hint">The panel stays in view while the tables scroll. Open trade… opens the confirmation with Copy to TOS and Paste from TOS.</div></div>')

COMPARE_DTES = (7, 14, 21, 28, 35, 42)   # same targets as config.COMPARE_DTES

def compare_box(open_=False):
    """Weekly Comparison: one strike (the starred row's, to the nearest 25) for the Friday nearest each target DTE, one contract."""
    K = int(round(SEL["strike"] / 25) * 25)
    today = NOW.date()
    fridays = [today + timedelta(days=d) for d in range(7, 57) if (today + timedelta(days=d)).weekday() == 4]
    used, body = set(), ""
    for t in COMPARE_DTES:
        free = [f for f in fridays if f not in used]
        fr = min(free, key=lambda f: (abs((f - today).days - t), (f - today).days)); used.add(fr)
        se, le = pick_expiries(today, 7, fr)
        s, l = leg_quote(S_NOW, K, today, se, ATM_S), leg_quote(S_NOW, K, today, le, ATM_L)
        g = lambda k: (l[k] - s[k]) * 100
        body += (f"<tr><td class=l style='white-space:nowrap'>{K:,} Put</td><td>{t // 7}</td>"
                 f"<td class=l style='white-space:nowrap'>{se:%a %b %-d} <span class=muted>· {s['dte']} DTE</span></td>"
                 f"<td class=l style='white-space:nowrap'>{le:%a %b %-d} <span class=muted>· {l['dte']} DTE</span></td>"
                 f"<td style='white-space:nowrap'>{l['bid'] - s['ask']:.2f} / {l['ask'] - s['bid']:.2f}</td><td>{g('delta'):+.2f}</td><td>{g('gamma'):.4f}</td><td>{g('theta'):.1f}</td><td>{g('vega'):.1f}</td>"
                 f"<td>{s['iv']*100:.1f}%</td><td>{l['iv']*100:.1f}%</td><td>{(s['iv'] - l['iv'])*100:+.1f}</td></tr>")
    hdr = "".join(f"<th style='text-align:center'>{h}</th>"
                  for h in ("Strike", "Week", "Short Expiry", "Long Expiry", "Bid / Ask", "Delta", "Gamma", "Theta", "Vega", "Short IV", "Long IV", "Skew"))
    if not open_:      # collapsed by default; the page remembers how the user leaves it
        return ('<div class="box" style="margin-bottom:14px;width:808px;box-sizing:border-box;padding:9px 14px"><b>▸ Weekly Comparison</b> '
                '<span class="muted" style="font-size:12.5px">· How the price and greeks change as the short expiry moves out</span></div>')
    return (f'<div class="box" style="margin-bottom:14px;width:808px;box-sizing:border-box"><h3>▾ Weekly Comparison <span class="muted" style="font-weight:400;font-size:12.5px">'
            f'· How the price and greeks change as the short expiry moves out</span></h3>'
            f'<div class="muted" style="font-size:12px;margin-bottom:6px">SPX {S_NOW:,.2f} · {NOW:%-I:%M %p} ET · 7-Day Width · One Contract Each</div>'
            f'<style>.cmp th,.cmp td{{text-align:center !important}}</style><table class="cmp"><tr>{hdr}</tr>{body}</table>'
            f'</div>')

def finder_body(tab="Risk profile", compare_open=False):
    strip = status_strip([("Tue Jan 12, 11:05 AM ET", ""), ("SPX", f"{S_NOW:,.2f}"),
                          ("Short expiries", " · ".join(f"{fr:%b %-d} ({(fr - NOW.date()).days}d)" for fr in FRIDAYS)),
                          ("Widths", ", ".join(f"{w}d" for w in WIDTHS_ON)), ("Sized by", f"margin {money(MARGIN)}")])
    return compare_box(compare_open) + filter_bar() + strip + f'<div class="grid2"><div>{overview_box()}</div><div style="position:sticky;top:12px">{finder_panel(tab)}</div></div>'

def holdings_body(columns_open=False, on=None):
    H = holdings_rows(); H0 = H[0]
    on = on or [k for k, _, d, _ in HCOLS if d]
    cols = [c for c in HCOLS if c[0] in on]
    hdr = "<th class=l style='position:sticky;left:0;z-index:1'>Trade</th>" + "".join(f"<th{' class=l' if k in ('entered','flag','account','notes') else ''}>{lab}</th>" for k, lab, _, _ in cols)
    trs = ""
    for h in H:
        sel = h is H0
        first = (f"<td class=l style='position:sticky;left:0;background:{'#0E2540' if sel else '#0B1222'};{'box-shadow:inset 3px 0 0 #1C83E1' if sel else ''}'>"
                 f"{h['K']:,} P<span class='two'>{dstr(h['se'])} → {dstr(h['le'])} · {(h['le'] - h['se']).days}d · {h['n']}×</span></td>")
        trs += f"<tr{' class=sel' if sel else ''}>{first}{''.join(hcell(k, h) for k, *_ in cols)}</tr>"
    tot_pl = sum(h["pl"] for h in H); tot_cost = sum(h["cost"] for h in H); tot_vol = sum(h["volpl"] for h in H)
    sm = lambda v: ("−" if v < 0 else "+") + money(abs(v))
    cards = '<div class="tiles" style="grid-template-columns:repeat(5,1fr);margin:0 0 14px">' + "".join(
        f'<div class="tile" style="padding:10px 14px"><div class="lab">{a}</div><div class="val {c}" style="font-size:20px">{b}</div></div>' for a, b, c in [
        ("SPX now", f"{S_NOW:,.2f} <span style='font-size:13px' class='{cls(S_NOW - PREV['S'])}'>{S_NOW - PREV['S']:+,.2f}</span>", ""),
        ("Open trades", str(len(H)), ""), ("Capital in trades", money(tot_cost), ""), ("Open P/L", sm(tot_pl), cls(tot_pl)), ("Vol P&L today", sm(tot_vol), cls(tot_vol))]) + '</div>'
    pop = ""
    if columns_open:
        groups = ""
        for g in dict.fromkeys(c[3] for c in HCOLS):
            items = "".join(f'<div style="margin:4px 0;font-size:13px"><span style="display:inline-block;width:15px;height:15px;border-radius:4px;vertical-align:-3px;margin-right:7px;'
                            f'{"background:#1C83E1;border:1px solid #1C83E1" if k in on else "border:1px solid #475569"};color:#fff;font-size:11px;text-align:center;line-height:15px">{"✓" if k in on else ""}</span>{lab}</div>'
                            for k, lab, _, gg in HCOLS if gg == g)
            groups += f'<div><div class="muted" style="font-size:12px;font-weight:600;margin-bottom:2px">{g}</div>{items}</div>'
        pop = (f'<div style="position:absolute;left:250px;top:34px;z-index:5;width:500px;background:#0F172A;border:1px solid #334155;border-radius:10px;padding:14px 16px;box-shadow:0 10px 30px rgba(0,0,0,.55)">'
               f'<div class="row" style="justify-content:space-between;margin-bottom:8px"><b>Columns</b><span class="muted" style="font-size:12px">Trade is always shown · saved per account</span></div>'
               f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px 18px">{groups}</div>'
               f'<div class="row" style="gap:8px;margin-top:12px"><span class="tbtn">Show all</span><span class="tbtn">Reset to default</span></div></div>')
    toolbar = (f'<div class="row" style="justify-content:space-between;align-items:center;margin-bottom:10px;position:relative"><h3 style="margin:0">Open <span class="muted" style="font-weight:400;font-size:12.5px">· {len(H)} trades · refreshes every 30 s</span></h3>'
               f'<div class="btnrow"><span class="tbtn">＋ Open trade</span><span class="tbtn{" on" if columns_open else ""}">▦ Columns ({len(cols) + 1}/{len(HCOLS) + 1}) ▾</span><span class="tbtn">↻ Refresh</span></div>{pop}</div>')
    table = f'<div style="overflow:hidden;border-radius:8px"><div style="width:max-content;min-width:100%"><table style="width:100%"><tr>{hdr}</tr>{trs}</table></div></div>'
    scroll = ('<div style="height:6px;background:#172033;border-radius:3px;margin-top:6px;position:relative"><div style="position:absolute;left:0;width:64%;height:6px;background:#475569;border-radius:3px"></div></div>'
              if len(cols) > 7 else "")
    shown = sum(1 for c in CLOSED if c[2] >= NOW.date() - timedelta(days=7))
    closed = (f'<div class="box" style="margin-top:14px"><div class="row" style="justify-content:space-between;align-items:center;margin-bottom:8px"><h3 style="margin:0">Closed <span class="muted" style="font-weight:400;font-size:12.5px">· {shown} of {len(CLOSED)}</span></h3>'
              f'<span class="select" style="min-width:130px;padding:3px 10px;font-size:12.5px">Last 7 days ▾</span></div>'
              f'<table><tr><th class=l>Trade</th><th class=l>Entered</th><th class=l>Exited</th><th>Days</th><th>P/L</th><th class=l>Exit reason</th><th class=l>Source</th></tr>{closed_rows(7)}</table></div>')
    left = f'<div><div class="box">{toolbar}{table}{scroll}<div class="hint">Click a row to show it in the panel. Trade stays pinned while the other columns scroll sideways.</div></div>{closed}</div>'
    # right panel: the selected trade
    graph, st = risk_graph(H0["K"], H0["se"], H0["le"], NOW.date(), H0["fill"], H0["n"], H0["s"]["iv"], H0["l"]["iv"], S_NOW, now_pl=H0["pl"])
    tobe = min(abs(S_NOW - H0["lo"]), abs(H0["hi"] - S_NOW))
    t = tiles([("Cost", money(H0["cost"]), ""), (f"P/L ({sgn(H0['plp'],1,'%')})", sm(H0['pl']), cls(H0["pl"])),
               ("Vol P&L today", sm(H0["volpl"]), cls(H0["volpl"])), ("Days (trading)", f"{H0['days']} ({H0['tdays']})", ""),
               ("Break-evens", f"{H0['lo']:,.0f} – {H0['hi']:,.0f}", ""), ("To nearest BE", f"{tobe:.0f} pts", ""), ("Δ / contract", f"{H0['dpc']:+.2f}", ""),
               ("Skew entry → now", f"{sgn(H0['skew0'])}→{sgn((H0['s']['iv']-H0['l']['iv'])*100)}", "")])
    note = NOTE.get(H0["K"], "").replace("\n", "<br>")
    panel = (f'<div class="panel"><div class="row" style="justify-content:space-between;align-items:flex-start">'
             f'<div><div class="ptitle">SPX {H0["K"]:,} put calendar {H0["flags"]}</div><div class="psub">{dstr(H0["se"])} → {dstr(H0["le"])} · {H0["n"]} × {H0["fill"]:.2f} · opened {H0["d0"]:%b %-d}</div></div></div>'
             f'<div class="btnrow" style="margin-top:10px"><span class="btn blue" style="padding:6px 14px">Close trade…</span><span class="btn" style="padding:6px 12px">✎ Notes</span><span class="btn" style="padding:6px 12px">⧉ Copy closing order</span></div>'
             f'<div class="ptabs"><div class="on">Risk profile</div><div>SPX chart</div><div>History</div></div>{graph}{t}'
             f'<h3 style="font-size:14px;margin:14px 0 6px">Notes</h3><div style="font-size:12.5px;color:#CBD5E1;line-height:1.5;background:#0B1222;border:1px solid #1E293B;border-radius:8px;padding:8px 10px">{note}</div>'
             f'<div class="hint">Pink dot: P/L now. History shows this trade\'s saved marks (P/L and both IVs over time).</div></div>')
    return cards + f'<div class="grid2"><div>{left}</div><div style="position:sticky;top:12px">{panel}</div></div>'


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True); BUILD.mkdir(exist_ok=True)
    pages = {
        "finder": page("Finder", finder_body(), "simulated SPX chain priced with Black-Scholes; not real quotes."),
        "finder-compare": page("Finder", finder_body(compare_open=True), "simulated SPX chain priced with Black-Scholes; not real quotes."),
        "finder-spx": page("Finder", finder_body("SPX chart"), "simulated SPX chain and daily bars; not real quotes."),
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
