# SPX Calendar Trader

Streamlit app for finding and paper-trading ~40Δ SPX put calendars. No real orders are sent; prices come from the Schwab API.
Source of truth for scope: `docs/PLAN.md`. Anything it lists under "Later" stays out unless Lav asks for it. If code and plan disagree, ask before changing either.

## Screens (all in `app.py`)
- **Finder**: settings in the sidebar, one per line (short-leg DTE range, width chips, strike chips 10s/25s, Size by, Refresh); the three screens are `st.navigation` pages, so the sidebar shows only on the Finder. The sidebar collapses with « (opens collapsed on narrow screens); while collapsed, a settings bar above Inputs shows the applied settings with Refresh. Refresh pulls the chain and shows Inputs; an SPX daily chart (3 months by default, 1M–2Y range chips, 20/50-day averages, the selected strike, break-evens band and expiries; bars from Schwab price history cached in `spx_daily`); an Overview table (one row per short/long pair at its ~40Δ strike, split into one segment per width, sortable within segments, with best skew; click to select a pair); a Detail table (every 35–45Δ strike of the selected pair, with the Excel sheet's columns); a Risk profile chart for the selected strike (P/L today and at the short expiry, optional +3/+5 days, break-evens, stats; like TOS Analyze); and Legs. Highlight the best-skew row and mark the strike nearest 40Δ. Clicking a Detail row opens the trade panel → Commit → confirmation ("Open trade", with Size by override and Copy to TOS) → Confirm saves.
- **Holdings**: the Finder's SPX chart on top (selected trade drawn on), then summary cards starting with SPX now (and today's change); one row per open trade, re-priced on each Refresh. Toolbar: ＋ Open trade (empty dialog for Paste from TOS), Close selected, ▦ Columns, Refresh; no per-row buttons. Columns (Trade always shown, pinned; the rest chosen in the Columns popover, saved per account): entered, days in trade, cost, value now, account, P/L $/%, Vol P&L today, break-evens, distance to nearest BE, delta per contract, theta, vega, short/long IV, skew now and at entry, flags (LOSS > 10% / +10% TARGET / DELTA > 2). The table scrolls sideways instead of squeezing. The selected row shows its risk profile (with P/L now). The Open and Close trade dialogs have **Paste from TOS** below Copy to TOS: a pasted TOS order line sets the trade, price and contracts (BUY in the open dialog, a matching SELL in the close dialog; editable price and fill time; `price_source = "pasted"`). Close selected → confirmation ("Close trade", with Copy to TOS for the closing order; exit reason dropdown pre-selected with the app's suggestion, both saved; the trade's notes pre-filled) → moves the trade to the Closed list (last 7 days by default; 14 / 30 / 90 days / All). Each trade has one Notes box (`notes` on `trades`), a text box that grows with the text, shown in the open, close and Notes dialogs, opened from the Notes column's ✎ View / ✎ Add button (no text in the row), and carried into Performance and the CSV.
- **Performance**: closed trades only. Period filter and Month/Week grouping on top, then sub-tabs Summary / By period / By condition (one grouping at a time, table + bar chart, Avg P/L %) / Exits / Trades; wins/losses bar chart, monthly and weekly tables, summary row, win rate and P/L grouped by entry condition (skew, VIX, short IV vs VIX, entry day, short DTE at entry, width, days in trade, vol at entry; every table shows average days in trade), exit-target comparison (+3/+5/+10%), two charts, trade list, CSV export.
- Colors: buttons grey (`type="secondary"`); selections blue (`primaryColor = "#1C83E1"` in `.streamlit/config.toml`: chips, tabs, slider, checkboxes, selected row); red only for warnings and losses.

## Repo layout
```
app.py            # Streamlit UI — the ONLY file that imports streamlit
services.py       # future API: get_finder, get_holdings, get_performance, get_risk_profile, get_spx_history, quote_spread, parse_tos_order, open_trade, close_trade
models.py         # Pydantic input/output models
settings.py       # every tunable number
schwab_api.py     # Schwab OAuth, weekly token, chain + quote pulls
calendar_math.py  # calendar sizing/greeks/skew columns (+ 16-row self-test)
pricing.py        # Black-Scholes (numpy/scipy), forward from put-call parity, P/L curves, break-evens
charts.py         # Plotly figures from service output (risk profile)
store.py          # SQLite: trades, marks, finder_log → data/paper_trades.db
tests/            # pytest, against services and pure modules
data/             # gitignored
docs/             # PLAN.md (scope), WEEK1.md (current week's steps), images/ (mockup screenshots), mockups/ (code that draws them; extra deps in the `mockups` group)
.vscode/          # shared editor config (interpreter, tests, run configs)
```
Run: `uv run --env-file .env app.py` (app.py starts Streamlit itself; docs never tell people to call `streamlit run`). Commands that call Schwab need `--env-file .env` (or `UV_ENV_FILE=.env`) for the keys. Test: `uv run pytest`. Add deps with `uv add`, never pip.

## The trade
- Short: SPX put, a Friday inside the short-leg DTE filter (7–56 days; default 25–35 = the Friday nearest 30 DTE); Thursday if that Friday is a holiday. ~40Δ (35–45Δ band). Strikes: multiples of 10 and/or multiples of 25 (on/off chips; default both).
- Long: same strike, 3/4/5/6/7 days after the short's Friday (default 7), for each width switched on. A holiday moves it to the previous trading day; if that's on or before the short, skip that width that week.
- Default trade (unchanged): Friday nearest 30 DTE, 7 days wide, ~40Δ. Trades store width and short DTE.
- Size: by Margin (default $10,000, user-editable): contracts = ceil(margin / (debit × 100)); or by a fixed number of Contracts: margin = debit × 100 × contracts. A calendar's margin is its debit. Set in the Finder filter bar, overridable per trade in the open dialog; trades store mode and value.
- Skew = short IV − long IV, in vol points.
- Vol P&L (Tom Conley) = [(Δ short IV) × short vega × (−1) + (Δ long IV) × long vega] × 100 × contracts, with Δ in vol points since the previous close and vega per share. Previous close = last refresh after 4:15 PM ET on the previous trading day, otherwise that day's last refresh (labeled); Holdings reads it from the trade's `marks`, the Finder from `finder_log`. Holdings flags DELTA > 2 per contract. Details: `docs/PLAN.md` → Vol P&L.
- Break-evens: SPX levels where P/L = $0 on the short expiry (long leg priced with Black-Scholes at its IV), the way thinkorswim shows them.
- Risk profile: reprice both legs with Black-Scholes on an SPX grid (each leg's IV held fixed, forward from put-call parity), never from greeks; draw with Plotly in `charts.py`. Details in docs/PLAN.md, "How the risk profile is computed".

## Fill rules
- Open at calendar mid + $0.10; close at mid − $0.10. Calendar mid = (bid + ask)/2 of the spread, built from both legs' quotes.
- Stability check first: re-quote the two legs every 2 s; stable after 5 quotes in a row stay within a $0.10 high-to-low range AND spread bid-ask ≤ 10% of mid. While waiting, return a `waiting_reason`; after 60 s, ask whether to keep waiting or cancel.
- The price box is editable at any time (even while waiting). Outside bid–ask → warning, still allowed. Save as `price_source = "manual"`.
- Store market quote and fill in **separate columns**, never overwrite one with the other. Market: bid, ask, mid at confirm, high–low range seen. Price: suggested price, confirmed fill, price source (auto/manual/pasted). Same set for open and close.
- P/L includes the $0.10 on both entry and exit.

## Built to move to React later (hard rules)
1. Only `app.py` imports Streamlit. Everything else is plain Python.
2. `services.py` holds one plain function per future endpoint: `get_finder()`, `get_holdings()`, `get_performance()`, `get_risk_profile()`, `get_spx_history()`, `quote_spread()`, `parse_tos_order()`, `open_trade()`, `close_trade()`. Streamlit calls only these.
3. Services take and return Pydantic models (numbers, strings, ISO dates, lists) — never DataFrames or NumPy types.
4. The UI only displays. Decisions come back as fields: `is_best_skew`, `is_near_40_delta`, `flag: "loss" | "target" | None`, `suggested_price`, `is_stable`, `waiting_reason`, `tos_order` (thinkorswim order line for the Copy to TOS buttons; the app never sends orders).
5. Services return raw numbers (12.85, not "$12.85"); formatting happens in the UI.
6. The database is the source of truth. `st.session_state` holds only screen state (selected row, dialog open), never trades or quotes.
7. Polling is a service call: the stability check is `quote_spread()` called every 2 s, returning `is_stable` and `waiting_reason`.
8. Settings live in `settings.py`: default margin ($10,000) and size modes, fill offset ($0.10), stability range and window, flag levels, delta band, short-DTE limits and default (7–56, 25–35), widths (3–7, default 7), strike sets (10s, 25s), holidays, close-snapshot time.
9. Tests target services and pure modules, not screens.
10. UI pieces are named like future components: `FinderFilters`, `SpxChart`, `OverviewTable`, `DetailTable`, `RiskProfileChart`, `LegsTable`, `OpenTradeDialog`, `HoldingsTable`, `CloseTradeDialog`, `PerformancePanel`.

## Also
- Keep each screen's controls inside that screen's `@st.fragment` so an interaction reruns only that screen, not the whole page.
- Every trade row has an `account` (default "Paper") and services accept an optional `account` argument, so multiple accounts (e.g. IRA vs regular) can be added later without a data migration. No account switcher until the plan says so.
- Code computes every price, P/L, break-even and size. Never hand-type or estimate a number into the UI, a test expectation (except a cited external source such as the Lane sheet or thinkorswim), or a doc.
- Never commit `data/`, `*.db`, or the Schwab token (`~/.schwab/`, set via `SCHWAB_TOKEN_PATH`). Keys come from `SCHWAB_APP_KEY` / `SCHWAB_APP_SECRET`.
- `uv run python calendar_math.py selftest` must stay 16/16. Never edit its expected numbers.
- At the end of each session, update `HANDOVER.md` (≤ 20 lines): what changed, what's next, anything broken or undecided.
