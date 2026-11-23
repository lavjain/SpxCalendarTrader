# SPX Calendar Trader

Web app for finding and paper-trading ~40Δ SPX put calendars. No real orders are sent; prices come from the Schwab API.
Built with **FastAPI + Jinja2 templates + HTMX + vanilla JavaScript** (no frontend framework, no build step).
Source of truth for scope: `docs/PLAN.md`. Anything it lists under "Later" or "Application Phase 2" stays out unless Lav asks for it. If code and plan disagree, ask before changing either.

## Stack
- **Backend:** FastAPI. Pages are `Jinja2Templates` responses; templates in `app/templates/`, one page per screen, `base.html` with `{% extends %}` and shared partials (`_header.html`, `_footer.html`) via `{% include %}`. One helper, `page_context(request, active_tab)` in `app/pages.py`, builds the common context (feature flags, active tab, app version, account); every page route uses it, so flags decide at render time which tabs and sections are shown.
- **HTML fragments (HTMX):** tables, cards and lists are Jinja partials under `app/templates/partials/`, served by routes in `app/partials.py` under `/partials/...` and swapped in with `hx-get` / `hx-target`. Timed refreshes use `hx-trigger="every 30s"`. HTMX loads from its CDN.
- **JSON API:** `APIRouter`s under `/api/...` in `app/api/`, every endpoint with a Pydantic `response_model`, so `/docs` documents the whole API. Used by charts, the dialogs' live numbers (stability check, Paste from TOS) and, in Phase 2, the Analyzer.
- **Async:** endpoints are `async`. Blocking Schwab calls go through `asyncio.to_thread` (or `run_in_threadpool`). Several chains at once (Phase 2 term structure) use `asyncio.gather`, limited as below.
- **Static files:** `StaticFiles` mounted at `/static`.
- **Frontend:** vanilla JS ES modules in `app/static/js/`, one controller per page (`finder.js`, `holdings.js`, `performance.js`). State lives in plain objects. No React, no bundler, no npm install for the app.
- **Styling:** Tailwind CSS from the CDN (config inline in `base.html`), dark/light theme toggled by the `dark` class on `<html>`, remembered in `localStorage`; dark is the default. `app/static/css/style.css` holds small overrides only.
- **Charts:** risk profile hand-painted on an HTML5 `<canvas>` (`static/js/charts/riskgraph.js`); SPX daily candles with TradingView Lightweight Charts (`static/js/charts/spxchart.js`); Performance bars, lines, scatter and histogram with Chart.js 4 (zoom/annotation plugins only where needed). All from CDNs.
- **Database:** SQLite at `data/paper_trades.db` (`app/core/store.py`).
- **Config:** secrets and paths from environment variables via pydantic-settings (`app/settings.py`); never committed.

## Repo layout
```
app/
  main.py            # FastAPI app: mounts /static, includes routers, sets up Jinja2Templates
  settings.py        # pydantic-settings: SCHWAB_APP_KEY, SCHWAB_APP_SECRET, SCHWAB_CALLBACK_URL, SCHWAB_TOKEN_PATH, DB_PATH, feature flags
  pages.py           # HTML page routes (TemplateResponse) + page_context() helper
  partials.py        # HTMX fragment routes (/partials/...) rendering templates/partials/ from service output
  schemas.py         # API request/response models (reuse core/models.py; add request validation)
  api/               # APIRouters: health, market (spot, expirations, spx-history), finder, quotes, trades, holdings, performance, settings
  core/              # all trading logic; NO FastAPI, Jinja or HTMX imports
    config.py        # every tunable trading number (was settings.py in the old plan)
    models.py        # Pydantic models for service inputs and outputs
    services.py      # one plain function per endpoint (see rule 2)
    schwab_api.py    # Schwab OAuth, weekly token, chain + quote + price-history pulls, cache, rate limiter
    calendar_math.py # calendar sizing/greeks/skew columns (+ 16-row self-test)
    expiries.py      # short Fridays, long dates by width, holidays
    pricing.py       # Black-Scholes (numpy/scipy), forward from put-call parity, P/L curves, break-evens
    store.py         # SQLite: trades, marks, finder_log, spx_daily, settings
  templates/
    base.html, _header.html, _footer.html
    finder.html, holdings.html, performance.html
    partials/        # _status_strip.html, _calendars_table.html, _strike_rows.html, _calendar_panel.html, _legs_table.html, _holdings_table.html, _trade_panel.html, _closed_table.html, _summary_cards.html, _perf_*.html, dialogs
  static/
    js/finder.js, js/holdings.js, js/performance.js
    js/lib/          # api.js (fetch helpers), format.js, theme.js, info.js (ⓘ popovers), poll.js
    js/charts/       # riskgraph.js (canvas), spxchart.js (Lightweight Charts)
    css/style.css
tests/               # pytest (+ FastAPI TestClient); tests/js/ for node --test (DOM-free modules only)
data/                # gitignored
docs/                # PLAN.md (scope), WEEK1.md, images/ (mockup screenshots), mockups/ (code that draws them)
.vscode/             # shared editor config
```
Phase 2 adds `app/templates/analyzer.html`, `app/static/js/analyzer.js` and `app/static/js/modeler/` (see Application Phase 2 below).

Run: `uv run serve` → http://localhost:8000 (API docs at `/docs`). `serve` is a `[project.scripts]` entry pointing at `app.main:serve`, which calls `uvicorn.run("app.main:create_app", factory=True, reload=True, env_file=".env")` (the app is built by the `create_app()` factory; importing `app.main` touches no files); docs never tell people to type the uvicorn command. Schwab login once a week: `uv run --env-file .env python -m app.core.schwab_api auth`. Test: `uv run pytest`; `node --test tests/js/*.test.mjs` (Node 18+, for tests only). Add Python deps with `uv add`, never pip.

## Screens (one template + one JS controller each)
- **Finder** (`finder.html`, `finder.js`): a **filter bar** across the top on one line (Short DTE range slider, width chips 3–7d, strike chips 10s/25s, Size by Margin/Contracts with the amount, ↻ Refresh with the last-pull time), saved per account; a **status strip** (time ET, SPX, short expiries with DTEs, widths, sizing); then two columns. **Left: the Calendars table**: one row per short/long pair at its ~40Δ strike (first cell "Fri Feb 12 → Fri Feb 19" with DTEs and strike count under it; ~40Δ strike, contracts, price, theta, vega, skew, Θ/Mgn, best skew and its strike), split into one segment per width, sortable within segments. Clicking a pair opens **its strike rows underneath** (every 35–45Δ strike with the Excel sheet's columns; ★ nearest 40Δ; one pair open at a time). **Right: the selected calendar panel**, which stays in view while the table scrolls: title with contracts × price, **Open trade…**, tabs **Risk profile** (chart with Today / +3 / +5 / At short expiry chips, ±1 SD toggle, range selector, then tiles: cost, max profit, max loss, P/L if closed now, break-evens, delta, theta/day, vega/pt) and **SPX chart** (daily candles, 3 months by default, 1M–2Y chips, 20/50-day averages, the selected strike, break-evens band and expiries; bars from Schwab price history cached in `spx_daily`; tiles for distance from the 3-month high, 5-day change, 20-day realized vol, short IV), and **Legs** (both puts with mark, bid/ask, delta, vega, IV, plus skew and IV ratio short/long). Open trade… → confirmation ("Open trade", with Size by override, Copy to TOS and Paste from TOS) → Confirm saves.
- **Holdings** (`holdings.html`, `holdings.js`): five summary cards (SPX now with today's change, open trades, capital in trades, open P/L, Vol P&L today), then two columns. **Left:** the Open table, re-priced on each Refresh and every 30 s, with its toolbar on the heading line (＋ Open trade for Paste from TOS, ▦ Columns, Refresh); no per-row buttons. Columns (Trade always shown, pinned; the rest chosen in the Columns popover, saved per account in the `settings` table): entered, days in trade, cost, value now, account, P/L $/%, Vol P&L today, break-evens, distance to nearest BE, delta per contract, theta, vega, short/long IV, skew now and at entry, flags (LOSS > 10% / +10% TARGET / DELTA > 2), notes. The table scrolls sideways instead of squeezing. Under it, the Closed list (last 7 days by default; 14 / 30 / 90 days / All, saved per account). **Right: the selected trade panel**: title with flag badges, **Close trade…**, **✎ Notes**, **⧉ Copy closing order**, tabs Risk profile (at the fill price, with the P/L-now dot) / SPX chart / History (Release 2: saved marks over time), tiles (cost, P/L, Vol P&L today, days, break-evens, to nearest BE, Δ/contract, skew entry → now) and the trade's notes. The Open and Close trade dialogs have **Paste from TOS** below Copy to TOS: a pasted TOS order line sets the trade, price and contracts (BUY in the open dialog, a matching SELL in the close dialog; editable price and fill time; `price_source = "pasted"`). Close trade… → confirmation ("Close trade", with Copy to TOS for the closing order; exit reason dropdown pre-selected with the app's suggestion, both saved; the trade's notes pre-filled) → moves the trade to the Closed list. Each trade has one Notes box (`notes` on `trades`), a text box that grows with the text, shown in the open, close and Notes dialogs and in the panel, and carried into Performance and the CSV.
- **Performance** (`performance.html`, `performance.js`): closed trades only. Period filter and Month/Week grouping on top, then sub-tabs Summary / By period / By condition (one grouping at a time, table + bar chart, Avg P/L %) / Exits / Trades; wins/losses bar chart, monthly and weekly tables, summary row, win rate and P/L grouped by entry condition (skew, VIX, short IV vs VIX, entry day, short DTE at entry, width, days in trade, vol at entry; every table shows average days in trade), exit-target comparison (+3/+5/+10%), two charts, trade list, CSV export.
- **Header** (`_header.html`): app name and version, tabs (Finder, Holdings, Performance; Analyzer only when its feature flag is on), the account (Paper), and the theme toggle. **Footer** (`_footer.html`): version, "paper trading only", last refresh time.
- **Dialogs:** native `<dialog>` elements, contents rendered as partials.
- **Tables:** thin row separators, no vertical gridlines, right-aligned tabular numbers, sticky header row. Highest skew = amber left edge; selected = blue tint + blue left edge (no fully filled rows).
- **Colors:** buttons grey (the one main action in a panel, e.g. Open trade… / Close trade…, is solid blue); selections blue (`#1C83E1`, set as Tailwind's `primary` color: chips, tabs, slider, checkboxes, selected row); red only for warnings and losses, green for gains and the TARGET flag, amber for DELTA > 2. Tailwind slate for surfaces and text.

## The trade
- Short: SPX put, a Friday inside the short-leg DTE filter (7–56 days; default 25–35 = the Friday nearest 30 DTE); If that Friday is a market holiday, the Thursday before. ~40Δ (35–45Δ band). Strikes: multiples of 10 and/or multiples of 25 (on/off chips; default both).
- Long: same strike, 3/4/5/6/7 days after the short's Friday (default 7), for each width switched on. Widths are counted from the nominal Friday. If its day is a market holiday it also moves to the day before (previous trading day), the same rule as the short; if that's on or before the short, skip that width that week.
- Default trade (unchanged): Friday nearest 30 DTE, 7 days wide, ~40Δ. Trades store width and short DTE.
- Size: by Margin (default $10,000, user-editable): contracts = ceil(margin / (debit × 100)); or by a fixed number of Contracts: margin = debit × 100 × contracts. A calendar's margin is its debit. Set in the Finder filter panel, overridable per trade in the open dialog; trades store mode and value.
- Skew = short IV − long IV, in vol points.
- Vol P&L (Tom Conley) = [(Δ short IV) × short vega × (−1) + (Δ long IV) × long vega] × 100 × contracts, with Δ in vol points since the previous close and vega per share. Previous close = last refresh after 4:15 PM ET on the previous trading day, otherwise that day's last refresh (labeled); Holdings reads it from the trade's `marks`, the Finder from `finder_log`. Holdings flags DELTA > 2 per contract. Details: `docs/PLAN.md` → Vol P&L.
- Break-evens: SPX levels where P/L = $0 on the short expiry (long leg priced with Black-Scholes at its IV), the way thinkorswim shows them.
- Risk profile: reprice both legs with Black-Scholes on an SPX grid (each leg's IV held fixed, forward from put-call parity using the calls and puts nearest the money, so the chain pull includes a few calls per expiry), never from greeks. In Release 1 the server computes it (`get_risk_profile()`) and `riskgraph.js` only paints it: expiry line sky blue (solid), T+0 pink (dashed), +3/+5 days violet/teal (dash-dot), green/red shading above/below $0, a grey ±1 SD band (SPX × short IV × √(days to short expiry ÷ 365)), break-evens in yellow, legend under the chart. Red is never a line colour. Details in docs/PLAN.md, "How the risk profile is computed".

## Fill rules
- Open at calendar mid + $0.10; close at mid − $0.10. Calendar mid = (bid + ask)/2 of the spread, built from both legs' quotes.
- Stability check first: re-quote the two legs every 2 s; stable after 5 quotes in a row stay within a $0.10 high-to-low range AND spread bid-ask ≤ 10% of mid. While waiting, return a `waiting_reason`; after 60 s, ask whether to keep waiting or cancel.
- The price box is editable at any time (even while waiting). Outside bid–ask → warning, still allowed. Save as `price_source = "manual"`.
- Store market quote and fill in **separate columns**, never overwrite one with the other. Market: bid, ask, mid at confirm, high–low range seen. Price: suggested price, confirmed fill, price source (auto/manual/pasted). Same set for open and close.
- P/L includes the $0.10 on both entry and exit.

## Architecture rules
1. **`app/core/` has no web imports.** No FastAPI, Starlette, Jinja2 or HTMX code in it; `grep -rn "fastapi\|starlette\|jinja2" app/core` prints nothing. Routes and partials are thin wrappers around core services.
2. **One service per endpoint.** `app/core/services.py` holds `get_finder()`, `get_holdings()`, `get_performance()`, `get_risk_profile()`, `get_spx_history()`, `quote_spread()`, `parse_tos_order()`, `open_trade()`, `close_trade()` (plus small helpers such as `get_spot()` and `get_expirations()`). The `/api` route and the `/partials` route for the same data call the same service; partials never compute anything of their own.
3. **Pydantic in, Pydantic out.** Services take and return Pydantic models (numbers, strings, ISO dates, lists), never DataFrames or NumPy types. Every `/api` endpoint declares a `response_model`. Inputs (symbols, expiries, strikes, widths, DTE ranges, sizes) are validated in `app/schemas.py`; bad input gets a 422, not a stack trace.
4. **The UI only displays.** Decisions come back as fields: `is_best_skew`, `is_near_40_delta`, `flag: "loss" | "target" | "delta" | None`, `suggested_price`, `is_stable`, `waiting_reason`, `tos_order` (thinkorswim order line for the Copy to TOS buttons; the app never sends orders).
5. **Raw numbers out, formatting at the edge.** Services return 12.85, not "$12.85". Jinja filters (`money`, `pct`, `signed`, `pts`) and `static/js/lib/format.js` format them with the same rules.
6. **Where state lives.** The database is the source of truth: trades, quotes, marks, and every saved setting, per account, in the `settings` table (Finder settings, Holdings columns, Closed-list window, chart range and overlay chips), read and written through `GET/PUT /api/settings/{key}`. `localStorage` holds only the theme, so the page can set dark or light before it draws. JS objects hold screen state (selected row, open dialog).
7. **Polling.** Holdings refreshes every 30 s (`hx-trigger="every 30s"` on its partials, plus JSON for the charts). The stability check is a JS timer calling `POST /api/quote-spread` every 2 s while a dialog is open. Polls don't write on every tick: a `marks` row per open trade is saved at most every 5 minutes (`MARKS_EVERY_S = 300`), on every explicit Refresh, and by the close snapshot after 4:15 PM ET (an `asyncio` task started in the app's lifespan). `finder_log` rows are written only on a Finder Refresh and by the close snapshot.
8. **Schwab calls.** Blocking calls run in `asyncio.to_thread`. Batch quotes (all legs plus `$SPX`, `$VIX`, `$VIX9D` in one call). A 15–30 s TTL cache sits in front of chain and quote pulls, shared by all tabs; `quote_spread()` bypasses it. At most 4 Schwab requests in flight, a global limiter at 100 requests/minute, exponential backoff on 429. One `asyncio.Lock` around token refresh. Errors raise exceptions (never `sys.exit`), which the API turns into a 502/503 with a message the page shows (e.g. "Schwab login expired: run the weekly auth").
9. **One uvicorn worker.** Stability-check windows and the cache live in memory. Finder snapshots live in memory and are also written to `data/snapshots.json` (one file, newest 20), so a restart reopens on the last refresh; they are a display cache, never the source of truth (SQLite is).
10. **Market time.** Dates, DTE, expiries and the close snapshot use America/New_York, never the server's local date.
11. **Two kinds of settings.** `app/settings.py` (pydantic-settings) reads environment variables: keys, callback URL, token path, DB path, feature flags. `app/core/config.py` holds the trading numbers: default margin ($10,000) and size modes, fill offset ($0.10), margin-to-contracts rounding (`SIZE_ROUNDING`, default nearest, min 1), stability range and window, flag levels, delta band, short-DTE limits and default (7–56, 25–35), widths (3–7, default 7), strike sets (10s, 25s), holidays, close-snapshot time, polling intervals, marks interval (5 min), cache TTL and rate limits.
12. **Tests target services and pure modules,** plus each `/api` route through FastAPI's `TestClient`. DOM-free JS modules (`format.js` now; `math.js`, `model.js` in Phase 2) are tested with `node --test` and must import with no browser.
13. **Named like components:** templates and JS modules use the names `FinderFilters`, `StatusStrip`, `CalendarsTable` (with its `StrikeRows`), `CalendarPanel`, `SpxChart`, `RiskProfileChart`, `LegsTable`, `OpenTradeDialog`, `HoldingsTable`, `TradePanel`, `CloseTradeDialog`, `PerformancePanel` (e.g. `partials/_calendars_table.html`, `partials/_calendar_panel.html`, `charts/riskgraph.js`).
14. **Every tile and control has a small ⓘ popover** (`lib/info.js`) saying what it shows and, for a saved setting, where it is kept (the app database, or this browser for the theme).
15. **Desktop first.** Mobile may be view-only.
16. **Don't change trading logic or formulas while moving code.** If you find a bug, list it for Lav and fix it in a separate change.

## Application Phase 2 (after Release 2; not in the 6-week plan)
- **Analyzer:** `analyzer.html` + `static/js/modeler/`: `math.js` (Black-Scholes price and Greeks, P/L at expiry, T+0 curve; no DOM), `model.js` (positions/legs, add/remove/move legs, undo/redo; no DOM), `graph.js` (canvas painting, hit-testing, strike drag, Shift-drag the whole structure, right-click to add legs, hover crosshair, price slices; grows out of `charts/riskgraph.js`), `ui.js` (cards, tiles, sliders, modals), `main.js` (wiring). The T+0 / P&L math runs in the browser so the Time and IV sliders redraw with no server round trip. Parity test: Python exports test vectors to a JSON fixture; for a fixed set of legs, `math.js` prices and Greeks match `pricing.py` within 0.01. Saved models in the app database (a `models` table) plus .json export/import. Mobile view-only.
- **Live spot:** polling first. A FastAPI WebSocket (`/ws/spot`) with the browser's `WebSocket` only if Lav asks; not Socket.IO.
- **Railway:** `uvicorn` with `Procfile` `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`; env vars via pydantic-settings; a Railway volume for `paper_trades.db` and the Schwab token; a web version of the weekly Schwab login (`/auth/schwab/login` + callback, with the Railway URL registered as a second callback in the Schwab portal); a password on the app.

## Also
- Every trade row has an `account` (default "Paper") and services accept an optional `account` argument, so multiple accounts (e.g. IRA vs regular) can be added later without a data migration. No account switcher until the plan says so.
- Code computes every price, P/L, break-even and size. Never hand-type or estimate a number into the UI, a test expectation (except a cited external source such as the Lane sheet or thinkorswim), or a doc.
- Never commit `data/`, `*.db`, `.env`, or the Schwab token (`~/.schwab/`, set via `SCHWAB_TOKEN_PATH`). Keys come from `SCHWAB_APP_KEY` / `SCHWAB_APP_SECRET`.
- `uv run python -m app.core.calendar_math selftest` and `uv run pytest tests/test_calendar_math.py` must stay 16/16. Never edit its expected numbers.
- At the end of each session, update `HANDOVER.md` (≤ 20 lines): what changed, what's next, anything broken or undecided.
