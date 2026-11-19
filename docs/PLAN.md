# SPX Calendar Trader — Plan

> Source of truth for scope. Exported from Lav's working doc on Nov 18, 2026; edit this file directly from here on.

## What this is

One program, three screens: the core built in 6 weeks, extras in a 2-week second release. Run `uv run app.py` and it opens a calendar finder for ~40Δ SPX put calendars. You pick one, commit it as a paper trade, and then a holdings screen shows its days in trade, current profit and break-evens. Any trade down more than 10% is flagged. Every trade is logged with the market conditions at entry and exit, and a performance screen shows which conditions made money.

No real orders are sent; prices come from your Schwab API pull. Everything from earlier versions that isn't needed for this (quality lights, the eight-rule exit engine, journal statistics, notifications) has moved to Later.

## Repo setup

The repo holds only this app. It starts from three working pieces:

| File | What it gives you |
| --- | --- |
| `schwab_api.py` | Schwab login, weekly token refresh, chain pull (fixed in week 1) |
| `calendar_math.py` | The Excel sheet's columns: Price, Contracts, Margin, Greeks, Skew, T/D, Θ/Mgn, with a 16-row self-test against a reference sheet |
| `README.md` | Schwab developer-app and callback-URL setup steps |

```
SPXCalendarTrader/
  app.py              # Streamlit: Finder, Holdings, Performance
  schwab_api.py       # Schwab login + chain pull
  calendar_math.py    # sizing, greeks, skew columns
  pricing.py          # Black-Scholes (numpy/scipy), forward from put-call parity, P/L curves, break-evens
  charts.py           # Plotly figures built from service output (risk profile)
  services.py         # future API: one function per endpoint
  models.py           # Pydantic models for inputs and outputs
  settings.py         # margin, offsets, thresholds
  store.py            # SQLite: trades, marks, finder_log, spx_daily, settings
  cli.py              # week 1: prints today's candidates in the terminal
  tests/
  docs/               # PLAN.md, WEEK1.md, images/, mockups/
  data/               # paper_trades.db (not committed)
  .env.example        # Schwab keys template; copy to .env (not committed)
  pyproject.toml      # uv, Python 3.12: streamlit, pandas, numpy, scipy, pydantic, plotly from week 2 (+ uv.lock)
  CLAUDE.md, HANDOVER.md
```

### Built to move to React later

The plan is to replace the Streamlit screens with a React front end at some point. These rules keep that a front-end swap, not a rewrite:

1. **Only `app.py` imports Streamlit.** Everything else is plain Python.
2. **A service layer is the future API.** `services.py` holds one plain function per future endpoint: `get_finder()`, `get_holdings()`, `get_performance()`, `get_risk_profile()`, `get_spx_history()`, `quote_spread()`, `parse_tos_order()`, `open_trade()`, `close_trade()`. Streamlit calls only these; later, FastAPI wraps each one as a route with no changes inside.
3. **Typed, JSON-ready inputs and outputs.** Services take and return Pydantic models (numbers, strings, ISO dates, lists), never DataFrames or NumPy types. The same models become FastAPI schemas and TypeScript types.
4. **The UI only displays.** Decisions are made in services and returned as fields: `is_best_skew`, `is_near_40_delta`, `flag: "loss" | "target" | null`, `suggested_price`, `is_stable`, `waiting_reason`, `tos_order`. React then renders the same fields without re-implementing rules.
5. **Raw numbers out, formatting in the UI.** Services return 12.85, not "$12.85".
6. **The database is the source of truth.** Streamlit session state holds only screen state (selected row, dialog open), never trades or quotes.
7. **Polling is a service call.** The stability check is `quote_spread()` called every 2 seconds and returning `is_stable` and `waiting_reason`. A Streamlit fragment calls it now; a React timer calls the same route later.
8. **Settings in one file.** Default margin ($10,000) and size modes, fill offset ($0.10), stability range and window, flag levels, delta band, short-DTE limits and default, widths, strike sets, holidays and the close-snapshot time live in `settings.py`.
9. **Tests target services, not screens**, so they still pass after the switch.
10. **Screens named like future components:** `FinderFilters`, `SpxChart`, `OverviewTable`, `DetailTable`, `RiskProfileChart`, `LegsTable`, `OpenTradeDialog`, `HoldingsTable`, `CloseTradeDialog`, `PerformancePanel`.

Schwab setup is in `README.md`. The token lives in `~/.schwab/`, outside the repo, and needs one re-login each week.

## The trade

| Leg | Expiry | Strike |
| --- | --- | --- |
| Short | A Friday whose DTE is inside the **short-leg DTE filter** (7–56 days, i.e. 1–8 weeks out; default 25–35, the Friday nearest 30 DTE). Thursday if that Friday is a market holiday | Put, ~40Δ (35–45Δ band), on the strikes switched on: **10s** (multiples of 10) and/or **25s** (multiples of 25); both by default, which gives the 10s plus the 25s and 75s |
| Long | **3, 4, 5, 6 or 7 days after the short's Friday** (SPXW expires every weekday: Mon, Tue, Wed, Thu, next Fri), for each width switched on (default 7). If that day is a holiday, the previous trading day; if that lands on or before the short, the width isn't offered that week | Same strike as the short |

The default trade is unchanged: short the Friday nearest 30 DTE, long 7 days later, ~40Δ. The filters widen what the Finder shows. Each saved trade records its short DTE and width, so Performance can compare them.

**Sizing.** By default each trade is sized to **$10,000 of margin**: contracts = margin ÷ (debit × 100), rounded up, the same way `calendar_math.py` sizes the Excel sheet's rows. A calendar's margin is its debit. A **Size by** control lets you change this: **Margin** with any amount you type (default $10,000), or **Contracts** with a fixed number (margin then = debit × 100 × contracts). It applies to the Finder's Contracts and Margin columns and can be overridden per trade in the open dialog. Trades store the sizing mode and value used.

## Screen 1 — Calendar finder

It looks like the Excel sheet, fed by Schwab instead of the live Excel price feed.

**Colors.** Buttons are grey on every screen: Streamlit's default (secondary) buttons, with a few main actions (Confirm, Open trade, Refresh) a lighter grey. **Blue marks what is selected:** chips and toggles that are on, the active tab, the slider, checked boxes and the selected table row. Set it once with `primaryColor = "#1C83E1"` in `.streamlit/config.toml`, which colors all of these, and keep buttons as `type="secondary"`. **Red is only for warnings and losses** (the LOSS flag, negative P/L), with green for gains and the TARGET flag, so red always means something needs attention.

**Filters** live in a **sidebar on the left, one setting per line**, so the page stays narrow and the tables get the full width. **The sidebar can be collapsed** with the « button at its top (Streamlit's built-in toggle; » brings it back). It opens expanded on a wide screen and collapsed on a narrow one (`st.set_page_config(initial_sidebar_state="auto")`). While it is collapsed, a one-line **settings bar** above Inputs shows what is applied (short DTE, widths, strikes, Size by) with its own Refresh button and a » Settings button, so nothing needs the sidebar open. The three screens are Streamlit pages (`st.navigation`, shown at the top) rather than tabs, so the sidebar appears only on the Finder. Refresh, at the bottom of the sidebar, re-pulls with the current settings:
- **Short-leg DTE:** a range slider from 7 to 56 days (1–8 weeks out); every Friday expiry inside the range is used. Default 25–35.
- **Days between short and long:** on/off chips for 3, 4, 5, 6 and 7 days; any combination. Default 7 only. A chip is crossed out when no expiry exists for it that week.
- **Strikes:** on/off chips for **10s** (multiples of 10) and **25s** (multiples of 25); check one or both. Default both.
- **Size by:** Margin (amount, default $10,000) or Contracts (a fixed number).

Press Refresh and it pulls the chain and fills these, top to bottom:

1. **Inputs**: time, SPX mark, the short expiries in the DTE range, the widths switched on, and the sizing (margin amount or contract count).
2. **SPX chart**: daily SPX bars, so you can see where SPX is now against the recent past (see below).
3. **Overview**: **one row per short/long pair**, at that pair's ~40Δ strike: short and long expiry, Sht DTE, Lng DTE, width, the ~40Δ strike, Contracts, Price, Margin, Theta, Vega, Skew, Θ/Mgn, plus **Best skew** (the highest skew among the pair's strikes, and at which strike) and how many strikes the pair has. The table is **split into one segment per width** (a header row such as "7-day width · 2 pairs"), in increasing order of width (3, 4, 5, 6, 7 days), so each width's pairs are easy to compare. Click any column header to sort within each segment, for example by Best skew. The pair with the highest best skew overall is highlighted. Click a row to select that pair.
4. **Detail**: **every strike of the selected pair** from 35Δ to 45Δ, with the sheet's columns (Strike, Short Δ, Contracts, Price, Margin, Delta, Gamma, Theta, Vega, Skew, T/D, Θ/Mgn). The pair's dates, DTEs and width are in the title. The highest-skew strike is highlighted and the one nearest 40Δ is starred. T/D shows "—" when position delta is near zero, where it means nothing. Click a strike to open the trade panel.
5. **Risk profile**: a P/L chart for the selected strike, like thinkorswim Analyze (see below).
6. **Legs**: the selected strike's short and long puts, with mark, bid, ask, delta, gamma, theta, vega and IV.

When the Finder first loads, the pair holding the default trade (Friday nearest 30 DTE, 7 days wide) is selected, with its ~40Δ strike. Which pair and strike are selected is screen state only (session state), never stored. In Streamlit, both tables are `st.dataframe` with row selection (`on_select`), which also maps directly to React later.

**SPX chart.** Daily candles for SPX, **3 months by default**, with range chips 1M, 3M, 6M, 1Y and 2Y to zoom out.
- **Overlays** (on/off chips): the 20- and 50-day averages; the selected calendar's strike (red dashed) with its break-evens at the short expiry as a shaded band; and the short and long expiries as dashed lines to the right of today, so the tent is drawn against recent price swings.
- **Stats above the chart:** high and low over the range, distance from the high, 5-day change, distance from the 20-day average, and 20-day realized vol next to the short leg's IV (a calendar does best when SPX moves less than the short leg's IV implies).
- **Data:** Schwab's price history endpoint (`GET /marketdata/v1/pricehistory`, symbol `$SPX`, daily bars) through a new `schwab_api.get_daily_bars(symbol, years=2)`. Bars are stored in a `spx_daily` table and only the missing days are pulled, so it costs one small request a day. Today's bar uses the live SPX mark.
- **Service:** `get_spx_history(range)` returns the bars, the averages and the stats; the overlays come from the selected row, so the chart updates when another Detail row is selected. Drawn with Plotly candlesticks in `charts.spx_figure()` (hover shows open, high, low and close).

![Finder mockup](images/finder.png)

![Finder mockup with the settings sidebar collapsed](images/finder-collapsed.png)

**Risk profile.** A P/L chart for the selected calendar, like thinkorswim Analyze, shown under the Detail table for the selected strike (sized as it would open) and in Holdings for the selected trade (at its fill price, with a dot for P/L now).
- **Lines** (on/off chips): Today, +3 days, +5 days, and At short expiry (default: Today and At short expiry). Each line is P/L at that date across SPX, with both legs repriced by Black-Scholes at their current IVs, held constant; at the short expiry the short leg is worth its intrinsic value.
- **Marks:** break-evens at the short expiry, a line at SPX now, and the P/L-now point in Holdings.
- **SPX range:** ±150, ±300 (default) or ±500 points around the strike.
- **Stats above the chart:** cost, max profit at the short expiry, max loss (the debit), break-evens, P/L if closed now, theta per day, vega per vol point, delta.
- The service `get_risk_profile()` returns the SPX grid, one P/L series per line, the break-evens and the stats; the UI only draws them.

**How the risk profile is computed.** Not from the greeks: they only describe small moves, and a calendar's shape changes a lot across a ±300-point range (the tent at the short expiry is the clearest case). Instead both legs are repriced on a grid, the way thinkorswim Analyze does it. All of this lives in `pricing.py`, in plain numpy and `scipy.stats.norm`, with no pricing library:
1. **Grid:** SPX from strike − range to strike + range, every 2 points (301 points at ±300).
2. **Dates:** for each line, the days left on each leg: today, today + 3, today + 5 (trading days, holidays skipped) and the short expiry. Time is in years: calendar days / 365, plus the fraction of today left until 4:00 PM ET.
3. **Price each put with Black-Scholes:** SPX options are European and cash-settled, so Black-Scholes is the right model. Use the forward form, `put = e^(−rT)·[K·N(−d2) − F·N(−d1)]`, with each leg's own forward F. Each leg keeps the IV it has now (sticky IV, the thinkorswim default). At the short expiry the short put is worth its intrinsic value, `max(K − S, 0)`.
4. **P/L:** `(long value − short value − debit) × 100 × contracts`, where the debit is the mid (Finder) or the fill price (Holdings).
5. **Break-evens:** where the At-short-expiry line crosses $0, found with `scipy.optimize.brentq` on each side of the strike (the same function the Holdings break-evens use).
6. **Stats:** max profit = the highest point of the At-short-expiry line; max loss = the debit; P/L now = today's line at SPX now; delta, theta and vega are the sum of the two legs' greeks from the chain × 100 × contracts.

**Rates and dividends.** Rather than hard-code them, each expiry's forward comes from the chain by put-call parity at the strike nearest the money: `F = K + e^(rT)·(call − put)`, with r from settings (default 4.0%; it matters little for a 5-week option). This absorbs the dividend yield, so there is no separate dividend input. For dates in the grid, the forward is moved with SPX: `F = S·(F_now / S_now)`.

**Checks (tests/test_pricing.py):**
- The put price matches a known reference value to the cent (e.g. from py_vollib or a textbook example).
- Today's line at SPX now equals the spread's current mid, so P/L now ≈ $0 at entry, and equals the Holdings P/L for an open trade.
- Break-evens are within about 5% of thinkorswim Analyze for the same calendar (the week-1 target).
- Put-call parity on the pulled chain gives a forward within a few points of SPX for near expiries.

**Drawing it: Plotly.** `st.plotly_chart` with one line per curve (solid red At short expiry, dashed blue Today, dash-dot for +3/+5 days), a $0 line, a dotted vertical line and label at SPX now, yellow markers with labels at the break-evens, and the P/L-now dot in Holdings. Plotly gives what thinkorswim users expect: hover shows SPX and the P/L of every line at that point, plus zoom and pan. Clicking the legend hides a line, and the line chips set which lines the service returns. The chart is built in a small `charts.py` (`risk_profile_figure(profile)`) from the service output; when the UI moves to React, the same spec draws with react-plotly.js, so `get_risk_profile()` doesn't change. Add it with `uv add plotly` in week 2 (this also updates `uv.lock`).

**Later:** reprice with each strike's IV from the chain's skew as SPX moves (sticky strike) instead of holding IVs fixed; and add a vol shift (e.g. ±2 points on both legs) to see Vol P&L on the chart.

The Finder and Holdings mockups both show it.

**Trade panel.** Click a Detail row and a panel opens with the strike, expiries, contracts, fill price (mid + $0.10, set once the mid is stable; see Fill rules), total cost, and the break-evens. Press **Commit** to see a confirmation; nothing is saved until you press Confirm.

**Open confirmation** shows the details with the fill price in an editable box and the **Size by** control (Margin amount or Contracts) pre-filled from the Finder, so one trade can be sized differently; for example: "Open trade: SPX 6,750 put calendar, short Dec 18 / long Dec 24, 8 contracts at $12.85 = $10,280. SPX 6,812.40, skew +1.1. Target +10% at $14.14, flag −10% at $11.57." **Confirm** saves the trade and its entry snapshot; **Cancel** saves nothing. A short "Trade opened" message follows. The dialog also has a **Copy to TOS order** button (see below).

![Open trade mockup](images/open-trade.png)

**Fill rules:**

- **Price.** Opening fills at the spread's mid + $0.10; closing fills at mid − $0.10. The mid is (bid + ask) ÷ 2 of the calendar, built from both legs' quotes.
- **Stable mid first.** When the confirmation opens, the app re-quotes the two legs every 2 seconds. It fills only after 5 quotes in a row (about 10 seconds) stay within a $0.10 high-to-low range and the spread's bid-ask is no wider than 10% of the mid.
- **While it waits**, the confirmation says why, for example "Waiting for a stable price: mid moved $0.25 in the last 10 seconds." After 60 seconds without a stable mid, it asks whether to keep waiting or cancel.
- **What gets saved:** the market quote and your fill in separate columns, so editing the price never overwrites the quote. Market columns: bid, ask, mid at the moment you confirm, and the high-to-low range seen during the check. Price columns: the suggested price (mid ± $0.10), the fill price you confirmed, and the price source (auto or manual). The same set is saved for the open and for the close.
- Re-quoting uses Schwab's quotes call for just the two legs, about 30 requests a minute, well inside Schwab's per-minute limit.
- **Edit the price.** The confirmation shows the fill price in an editable box, pre-filled with mid ± $0.10 once the mid is stable. You can type your own price at any time, including while it is still waiting; P/L, contracts, target and flag prices update as you type. A typed price outside the calendar's bid–ask gets a warning ("$13.60 is above the ask of $13.40; a real order wouldn't fill there") but can still be confirmed. The trade is saved with a "manual price" tag, so the Performance screen can show manual and automatic fills separately.

## Screen 2 — Holdings

One row per open paper trade, re-priced from Schwab on each Refresh.

**Layout.** At the top, the same **SPX chart** as the Finder (daily candles, 3 months by default), with the selected trade's strike, break-evens and expiries drawn on. Below it, five summary cards: **SPX now** (with today's change), open trades, capital in trades, open P/L and Vol P&L today. Then the Open table, with its toolbar on the same line as the "Open" heading, directly after it (not pushed to the far right):
- **＋ Open trade:** opens an empty Open trade dialog, filled in with **⇩ Paste from TOS**, for a trade placed straight in thinkorswim. (Trades found in the Finder still open from its Detail table.)
- **Close selected:** opens the Close trade dialog for the selected row. Click a row to select it; its risk profile shows below the table. There are no per-row buttons: the closing order is copied from the close dialog's Copy to TOS.
- **▦ Columns:** a popover with a checkbox per column, grouped (Position, P/L, Risk, Volatility, Flags), with Show all and Reset to default. **Trade** is always shown. The choice is saved (in a `settings` table, per account) and comes back next time.
- **↻ Refresh.**

**Scrolling.** The table never squeezes columns: when the chosen columns are wider than the screen, it scrolls sideways, with **Trade pinned on the left** so you always know which row you are reading. In Streamlit this is `st.dataframe` with `column_order` from the Columns choice and the Trade column pinned (`st.column_config.Column(pinned=True)`, in recent Streamlit releases; if the installed version lacks it, Trade simply comes first). Row selection uses `on_select`, as on the Finder.

![Holdings mockup](images/holdings.png)

![Holdings mockup with the Columns popover open and the table scrolling](images/holdings-columns.png)

| Column | What it shows | Shown by default |
| --- | --- | --- |
| Trade | Strike, short/long expiry, width (days), contracts | always |
| Entered | Date and SPX at commit | |
| Days | Calendar days since commit (trading days in brackets) | ✓ |
| Cost | Fill price × 100 × contracts | |
| Value now | (Current mid − $0.10) × 100 × contracts, what closing now would get | |
| Account | Which account the trade is in (Paper for now) | |
| P/L | Value now − cost, in $ and as % of cost | ✓ |
| Vol P&L today | The dollar effect of today's IV changes on the two legs since the previous close (see Vol P&L below); shows whether a day's P/L came from volatility or from SPX moving | ✓ |
| Break-evens | Lower and upper SPX levels where the trade is at $0 P/L on the short expiry, the way thinkorswim shows them | ✓ |
| To nearest BE | Distance from SPX now to the nearer break-even, in points (SPX itself is in the summary cards) | ✓ |
| Δ / contract | Position delta ÷ contracts | ✓ |
| Theta / day | Position theta in $ per day | |
| Vega | Position vega in $ per vol point | |
| Short IV, Long IV | Each leg's IV now | |
| Skew now | Short IV − long IV now, in vol points | |
| Skew at entry | The same at entry, from the entry snapshot | ✓ |
| Flag | See below | ✓ |
| Notes | A **✎ View** button that opens the trade's notes (**✎ Add** when there are none); the text itself isn't shown in the row | ✓ |

**Notes.** Each trade has **one Notes box**, free text that grows with its length (one line when empty, as many as it needs). Use it for why you entered, what you're watching and why you closed. The Notes column has only a button: **✎ View** opens the trade's notes, **✎ Add** when there are none; the text isn't shown in the row. The same notes show, and can be edited, in the Open trade dialog (empty, optional), the Close trade dialog (pre-filled) and the Notes dialog. They stay with the trade after it closes and appear in Performance → Trades and in the CSV export. Stored as `notes` and `notes_updated_at` on the `trades` row.

![Notes mockup](images/notes.png)

**Flags:**

- Red **LOSS > 10%** when P/L is −10% of cost or worse
- Green **+10% TARGET** when P/L is +10% or better
- Amber **DELTA > 2** when position delta is more than 2 per contract either way (Tom Conley's comfort limit)

**Close selected** closes the selected paper trade at mid − $0.10 (after the same stability check as opening) and moves it to the **Closed** list below the Open table (trade, entered, exited, days held, P/L, exit reason, price source). The Closed list shows **the last 7 days by default**, with a dropdown for 14, 30 or 90 days, or All; the choice is saved with the other Holdings settings. The heading shows how many are listed out of the total (e.g. "3 of 4 closed trades"). The full history, with filters and CSV, is in Performance → Trades.

**Close confirmation** shows the exit price in an editable box (mid − $0.10 after the same stability check, or your own price), P/L in $ and %, days held and SPX now, for example: "Close trade: SPX 6,750 put calendar, 8 contracts at $14.20. P/L +$1,080 (+10.5%), 4 days." The **exit reason** is a dropdown, pre-selected with the app's suggestion: **+10% target** or **−10% flag** if the trade was flagged when closed, otherwise **Other**. The choices are +10% target, −10% flag, Time exit, Before an event, Delta / adjustment, and Other. Both the suggestion and your choice are saved (`exit_reason_suggested`, `exit_reason`); Performance groups and filters by your choice. The **Notes** box shows the trade's notes, pre-filled, to add the why. **Confirm** saves the exit snapshot and moves it to Closed; **Cancel** leaves it open.

![Close trade mockup](images/close-trade.png)

**Copy to TOS.** The Open trade and Close trade dialogs have a **Copy to TOS** button that copies the trade as a thinkorswim order line, ready to paste into TOS order entry: the open dialog copies the opening order, and the close dialog copies the closing order (Holdings rows have no button of their own). It uses the price in the box at that moment (mid ± $0.10 or your own). For example:

```
BUY +13 CALENDAR SPX 100 (Weeklys) 19 FEB 27/12 FEB 27 6800 PUT @7.70 LMT
SELL -13 CALENDAR SPX 100 (Weeklys) 12 FEB 27/5 FEB 27 6735 PUT @8.70 LMT
```

**Paste from TOS.** The Open trade and Close trade dialogs have a **⇩ Paste from TOS** button directly below Copy to TOS. Paste an order line copied from thinkorswim, in the same format Copy to TOS writes (for example `BUY +10 CALENDAR SPX 100 (Weeklys) 12 FEB 27/5 FEB 27 6780 PUT @9.20 LMT`), and the dialog takes its trade, price and contracts from it. Two uses: recording the price you actually got in TOS, and entering a trade placed straight in thinkorswim from any row, without building it in the Finder.
- **What it reads:** BUY or SELL, contracts, the two expiries (in either order; the earlier one is the short), strike, PUT, and the limit price. The service `parse_tos_order(text)` returns these fields or says which part it couldn't read; the parsing has its own tests.
- **Open trade dialog (BUY line):** the pasted order replaces what the dialog showed. Checks: both expiries are SPXW dates, the width is 3–7 days, it is a put calendar (calls are refused for now), and the trade isn't already in Holdings; the short leg's delta is shown, with a warning (not a block) outside 35–45Δ. The fill price comes from the line and the fill time defaults to now; both are editable, for a trade filled earlier. Contracts come from the line, not from Size by. The entry snapshot (SPX, VIX, IVs, skew, break-evens) is taken from the nearest saved Finder refresh to the fill time, or from a fresh quote if there is none, and the dialog says which. Saved with `price_source = "pasted"`.
- **Close trade dialog (SELL line):** the line must match the trade being closed (strike, expiries, contracts); it sets the exit price and, if edited, the exit time. A partial close (fewer contracts) is refused for now.
- A SELL line in the open dialog, or a BUY line in the close dialog, is refused with a message saying which dialog it belongs in.

![Open trade dialog after Paste from TOS](images/paste-trade.png)

The service builds the line and returns it as a `tos_order` field; the UI only copies it. The app still sends no orders. Before building, copy a real calendar order from TOS and match its exact format (leg order, the `(Weeklys)` tag for SPXW, date style).

**Two things to know about the numbers.** P/L includes the $0.10 cost on both the way in and the way out, so a +10% flag is +10% after fills, not before. And if you use the −10% flag as your exit, a +10% / −10% pair needs you to win just over half your trades before costs, a much lower bar than the +10% / −20% pair in earlier versions.

### Vol P&L (from Tom Conley)

Volatility, not SPX price, drives most of a calendar's day-to-day P/L. Vol P&L isolates that part:

Vol P&L = [(short IV now − short IV at previous close) × short-leg vega × (−1) + (long IV now − long IV at previous close) × long-leg vega] × 100 × contracts

IVs are in vol points and vegas per share, so a short-leg IV drop helps the trade and a long-leg IV drop hurts it. It ignores delta and theta on purpose. The **previous close** is the last refresh after 4:15 PM ET (when SPX options stop trading) on the previous trading day. If there was none, the last refresh of that day stands in, and the screen says so. Holdings takes it from each trade's own `marks` rows; the Finder (entry snapshot, and later the Finder columns) takes it from `finder_log`.

## Where trades are stored

All trades live in one SQLite file, `data/paper_trades.db`. It is kept out of git (`*.db` in `.gitignore`), it is a single file you can copy to back up, and the Performance screen exports it to CSV for Excel.

Three tables:

| Table | One row per | What it holds |
| --- | --- | --- |
| `trades` | Paper trade | The account it belongs to, the trade (strike, expiries, width, short DTE at entry, sizing mode and value, contracts, fill, cost) plus a market snapshot at entry and at exit (below), exit reason, P/L, days held |
| `marks` | Trade per refresh | Time, SPX, spread mid, short and long IV, short and long vega, P/L %, Vol P&L; gives you each trade's path, its worst point and its best point |
| `finder_log` | Strike × expiry pair per finder refresh | Time, SPX, VIX, short and long expiries, width, strike, calendar mark, delta, short and long IV, short and long vega, skew, whether it was the best-skew row, and whether you traded; the whole ladder, so you can see what the market offered on days you passed and compute Vol P&L against the previous close |
| `spx_daily` | One row per trading day | Date, SPX open, high, low, close; topped up from Schwab price history (only missing days are pulled) |
| `settings` | One row per account and setting | Screen preferences that should survive a restart, such as which Holdings columns are shown |

**Snapshot saved at entry, and again at exit:**

| Field | Source |
| --- | --- |
| Date and time | Clock at commit |
| SPX | Schwab quote |
| VIX and VIX9D | Schwab quotes (`$VIX`, `$VIX9D`) |
| Short-leg IV, long-leg IV | The two legs' IVs from the chain |
| Skew | Short IV − long IV, in vol points |
| Break-evens | Lower and upper SPX at $0 P/L on the short expiry |
| Vol P&L at entry | The chosen strike's Vol P&L that day, from `finder_log` (entry only) |
| Time of day | Clock at commit (entry only), for the time-of-day grouping |

## Screen 3 — Performance

It answers one question: which entry conditions made money for you? It reads only closed trades.

A tab-by-tab walkthrough with screenshots is in [PERFORMANCE.md](PERFORMANCE.md).

**Layout.** So it stays readable on a normal screen, the Period filter and Month/Week switch sit at the top, and the rest is split into **five sub-tabs**:
- **Summary:** the summary row (two rows of four), the wins/losses chart and the cumulative P/L chart.
- **By period:** a P/L bar chart per week or month (follows the Month/Week switch), best and worst week, then the monthly and weekly tables, stacked.
- **By condition:** chips to pick **one** grouping at a time (skew, VIX, short IV vs VIX, vol at entry, entry day, short DTE, days in trade, width), shown as a table with trades, win rate, Avg P/L, **Avg P/L %** and Avg days, plus a bar chart of average P/L per bucket. For example, Width compares 3-, 4-, 5-, 6- and 7-day spreads side by side. The P/L-vs-skew scatter appears with the skew grouping.
- **Exits:** the exit-target comparison (how often +3%, +5% and +10% were first reached, average days to reach, and how many of those later closed at a loss), a bar chart of hit rates, and a histogram of the best P/L % each trade reached while open, split into winners and losers.
- **Trades:** the closed-trade list (opened, closed, days, width, short DTE, skew, VIX, P/L, P/L %, exit reason), newest first, sortable, with Exit and Width filters and CSV export (notes included). Clicking a row shows its legs, fills and risk profile at entry.

![Performance mockup, Summary tab (36 randomly simulated trades)](images/performance.png)

![Performance mockup, By condition tab set to Width](images/performance-conditions.png)

![Performance mockup, By condition tab set to Skew at entry, with the scatter](images/performance-skew.png)

![Performance mockup, By period tab](images/performance-period.png)

![Performance mockup, Exits tab](images/performance-exits.png)

![Performance mockup, Trades tab](images/performance-trades.png)

**Filters (top of the screen):** a **Period** picker (all closed trades, this month, last 4 weeks, or a custom date range) and a **Group by** switch (Month or Week). Everything on the screen (summary row, tables, charts) uses only trades in the chosen period, grouped by entry date.

**Wins and losses chart:** a bar chart with a green bar for wins and a red bar for losses in each month or week, following the Group by switch.

**By period:** two tables, monthly performance and weekly performance, each with trades, wins, losses, win rate, P/L and average days in trade for that month or week.


**Summary row:** number of trades, win rate, average win, average loss, expectancy per trade, total P/L, average days held, and how many hit +10% versus the −10% flag.

**By entry condition** (the By condition tab): trades, win rate, average P/L, average P/L % and average days in trade, grouped by each of these, so you can see which conditions helped:

| Group by | Buckets (defaults) |
| --- | --- |
| Skew at entry | Below 0, 0 to +1, above +1 vol point |
| VIX at entry | Under 15, 15–20, over 20 |
| Short-leg IV vs VIX | Short IV above VIX, or below |
| Entry day | Mon to Fri |
| Short DTE at entry | 7–14, 15–28, 29–42, 43–56 days |
| Width | 3, 4, 5, 6, 7 days (compares average profit of 3-, 5- and 7-day spreads) |
| Days in trade | 1 to 7 days held (compares average profit of trades held 3, 5 or 7 days) |
| Vol at entry (Tom Conley's entry rule) | Volatility had moved against the spread that day (Vol P&L < 0), or not |

**Exit-target comparison:** from each trade's `marks` path, how often trades first reached +3%, +5% and +10%, how many days each took, and the average final P/L. This compares quick exits like Tom's (often 1–5% in about 2 days) with the +10% target on the same trades, without changing the rules you trade by.

**Two charts:** cumulative P/L over time, and P/L % against entry skew (one dot per trade).

**Trade list:** every closed trade with its entry and exit snapshot side by side, sortable, with a CSV export button.

Groups need about 10 trades each before they mean much, so expect 30–40 closed paper trades before drawing conclusions. At 2–3 trades a week, that is roughly 3–4 months.

## 6-week build plan

Six weeks at about 6–8 hours a week, Nov 24, 2026 to Jan 4, 2027, with Claude Code writing most of the code. The app is Streamlit, so it is all Python and starts with one command. Weeks 1, 5 and 6 contain holidays (Thanksgiving, Christmas, New Year), so they carry less work.

**Two releases.** Release 1 (weeks 1–6) is the core loop: find a calendar, open a paper trade, track it in Holdings, close it, and see results. **The 6 weeks are fixed:** if a week runs over, its unfinished items move to [Release 2](#release-2-jan-518-2027) rather than pushing the date. Release 2 (two weeks, Jan 5–18, 2027) adds the extras listed there; the screen descriptions above cover both releases. The second half of week 6 is kept as buffer.

### Week 1 — Schwab data and calendar pricing (Nov 24–30, Thanksgiving week)

Step-by-step version: [WEEK1.md](WEEK1.md).

- [x] Starting files in place; `calendar_math.py` self-test passes 16/16
- [ ] Fix the pull: use one strike for both legs, return the 35–45Δ puts for the chosen expiries on the strikes switched on (10s and/or 25s), keep SPXW contracts on the third-Friday expiry, and limit the pull to 63 DTE
- [ ] Expiry picker: every Friday in the short-leg DTE range (default 25–35), each paired with longs 3–7 days later for the widths switched on (default 7); holidays handled
- [ ] Calendar pricer in `pricing.py`: Black-Scholes put (forward form), forward per expiry from put-call parity, value at mid now, P/L across SPX levels on the short expiry and on any date before it, break-evens with `brentq`; `tests/test_pricing.py` (see How the risk profile is computed)
- [ ] Services skeleton; `get_finder()` with filters and Size by (margin or contracts); `cli.py candidates`

Done when one command prints today's candidates and a calendar's break-evens are within about 5% of thinkorswim Analyze.

### Week 2 — Finder screen (Dec 1–7)

- [ ] Screens as Streamlit pages (`st.navigation`, top); Finder settings in the sidebar, one per line: short-leg DTE range (7–56, default 25–35), width chips (3–7 days, default 7), Size by (Margin, default $10,000, or Contracts), strike chips (10s and/or 25s, default both)
- [ ] Streamlit page with Inputs, an Overview table (one row per short/long pair at ~40Δ, one segment per width, sortable within segments, click to select), a Detail table (every strike of the selected pair), Legs, and a Refresh button; `app.py` starts Streamlit itself, so `uv run app.py` is the only command (see below)
- [ ] Save every Finder row (the whole strike ladder) to `finder_log` on each refresh, so daily closes start collecting for Vol P&L
- [ ] Risk profile under the Detail table: `get_risk_profile()` (Today and At-short-expiry lines, break-evens, stats) drawn with Plotly by `charts.risk_profile_figure()` (`uv add plotly`)
- [ ] Collapsible settings sidebar (`initial_sidebar_state="auto"`) and the settings bar with Refresh shown while it is collapsed
- [ ] Copy a real calendar order from TOS to confirm the Copy to TOS line format (needed in week 3)

Done when a refresh shows the Overview and Detail tables for the chosen filters, and the default pair's numbers match the CLI.

`app.py` begins with this, before any screen code, so it starts Streamlit when run as a plain script and does nothing when Streamlit is already running it (Streamlit also runs the file as `__main__`):

```python
if __name__ == "__main__":
    import sys
    from streamlit import runtime
    from streamlit.web import cli as stcli

    if not runtime.exists():
        sys.argv = ["streamlit", "run", __file__, *sys.argv[1:]]
        sys.exit(stcli.main())
```

### Week 3 — Opening paper trades (Dec 8–14)

- [ ] `trades` rows carry an `account` column (default "Paper"), ready for multiple accounts later
- [ ] Click a Detail row to open the trade panel; Commit opens a confirmation ("Open trade"), and Confirm saves the trade and its entry snapshot (time, SPX, VIX, VIX9D, short and long IV, skew, break-evens, Vol P&L at entry, width, short DTE, sizing) to the `trades` table
- [ ] Stability check (5 quotes in 10 seconds within $0.10, spread ≤ 10% of mid) with a waiting reason and a 60-second keep-waiting prompt; fill at mid + $0.10 in an editable box, with a bid–ask warning and the manual-price tag
- [ ] Size by override in the open dialog
- [ ] Copy to TOS button in the open dialog (`tos_order` from the service)
- [ ] Paste from TOS in the open dialog, below Copy to TOS: `parse_tos_order()` with tests (good lines and each kind of bad one), the checks, editable fill price and time, entry snapshot from the nearest saved refresh, `price_source = "pasted"`

Done when you can refresh, pick a 40Δ calendar and commit it in under a minute.

### Week 4 — Holdings screen (Dec 15–21)

- [ ] Holdings table: days in trade, cost, value now, P/L $ and %, break-evens, SPX distance
- [ ] LOSS > 10%, +10% TARGET and DELTA > 2 flags; Delta / contract column
- [ ] Vol P&L today column, using the previous close from the trade's `marks` rows; marks rows store both vegas and Vol P&L
- [ ] Close selected with a confirmation ("Close trade"; exit reason dropdown pre-selected with the suggestion; the trade's notes) that saves the exit snapshot, and a Closed list (last 7 days by default; 14 / 30 / 90 days / All); write a marks row for each open trade on every refresh
- [ ] Copy to TOS in the close dialog (closing order)
- [ ] Toolbar: ＋ Open trade (empty dialog for Paste from TOS), Close selected, Refresh
- [ ] SPX chart above the summary cards (the Finder's chart, with the selected trade drawn on) and an SPX now card with today's change
- [ ] Notes: one Notes box per trade (`notes`, `notes_updated_at` on `trades`), a growing text box in the open, close and Notes dialogs, Notes column with a ✎ View / ✎ Add button only
- [ ] Columns popover (grouped checkboxes, Show all, Reset to default), saved per account in a `settings` table; table scrolls sideways with Trade pinned
- [ ] Paste from TOS in the close dialog, below Copy to TOS: a SELL line matching the trade sets the exit price
- [ ] Risk profile for the selected Holdings row, at its fill price, with P/L now marked
- [ ] SPX chart on the Finder, basic version: `schwab_api.get_daily_bars()`, `spx_daily` table with daily top-up, `get_spx_history()`, Plotly candles for 3 months with the selected strike, break-evens band and expiries (moved from week 2, which was the fullest week)
- [ ] Handle a missing quote and the 7-day Schwab re-login without crashing
- [ ] Paper trade with it for 5 trading days

Done when a week of paper trades was found, entered and tracked only in the app.

### Week 5 — Performance screen, core (Dec 22–28, Christmas week)

- [ ] Sub-tabs: Summary, By period, By condition, Exits, Trades
- [ ] Period filter (all / this month / last 4 weeks / custom range) and Month / Week grouping, applied to everything on the screen
- [ ] Summary row: trades, win rate, average win and loss, expectancy, total P/L, average days held
- [ ] Wins / losses bar chart by month or week; monthly and weekly performance tables (with average days in trade)
- [ ] Closed-trade list with entry and exit snapshots, and CSV export

Done when these show correct numbers for a handful of test trades you checked by hand (use test trades: real closed trades will still be few).

### Week 6 — Performance analysis and wrap-up (Dec 29 – Jan 4, New Year week)

- [ ] By condition tab with the first three groupings: width, skew at entry, days in trade (table with Avg P/L, Avg P/L % and Avg days, plus a bar chart of average P/L); the other groupings come in Release 2
- [ ] Exits tab: the exit-target comparison table (+3% / +5% / +10%, average days to reach) from the marks paths
- [ ] Cumulative P/L chart on Summary
- [ ] Second half of the week: buffer. Bug fixes from three weeks of paper trading; swap the README mockups for real screenshots; update HANDOVER; move anything unfinished to Release 2

Done when the screen checks out against hand-checked test trades, and the app has run a full week of paper trading without errors.

## Release 2 (Jan 5–18, 2027)

Two weeks after Release 1, for the extras and anything that slipped. By now there are a few weeks of real paper trades, `finder_log` closes and SPX history to test against.

### Week 7 — Finder and risk profile extras (Jan 5–11)

- [ ] Anything left over from Release 1, first
- [ ] Risk profile: +3 and +5-day lines (on/off chips) and the SPX range switch (±150 / ±300 / ±500)
- [ ] SPX chart: range chips 1M / 3M / 6M / 1Y / 2Y, 20- and 50-day averages, the overlay on/off chips, and the stats above it (high and low, distance from high, 5-day change, vs 20-day average, realized vol vs short IV)
- [ ] Holdings: risk profile for a closed trade at entry (opened from the Trades tab)

### Week 8 — Performance extras (Jan 12–18)

- [ ] By condition: the remaining groupings (VIX, short IV vs VIX, vol at entry, entry day, short DTE at entry) and the P/L-vs-skew scatter with the skew grouping
- [ ] Exits tab: the "later closed at a loss" column, the hit-rate chart and the best-P/L-reached histogram
- [ ] By period: P/L-by-week (or month) bar chart with best and worst week
- [ ] Trades tab: Exit and Width filters, sorting, and clicking a row to see its legs, fills and risk profile at entry
- [ ] Review the open questions below with three to four weeks of paper trades in hand

Done when every screen matches its mockup in docs/images/.

## Later, and open questions

Left out on purpose, to add once the paper trades show the setup works: the items below, a 1-week expected range logged with each trade (matched to thinkorswim's ± figure), quality lights and skew history, the full exit-signal rules (breakeven exits, time exit), journal statistics, alerts, call and double calendars, and a FastAPI page if Streamlit's layout gets limiting.

### Worth considering (changes the trade)

From Tom Conley's practice. Each one would be paper-tested side by side with the current rules rather than replacing them.

- **Tom's short-leg window.** He sells the short leg at about 21–25 DTE and closes before about 14 DTE. The DTE filter (21–25) now shows his trades next to the default ~30 DTE; Performance's "Short DTE at entry" grouping compares them. What remains to decide is whether to *trade* that window, not whether to build it.
- **Tom's 25-point strikes and "calendar price slope".** Checking only the 25s strike chip gives his ladder; the row-to-row price change then shows how little the price moves across 50 points further from expiry.
- **Time-of-day grouping.** The same calendar is often about $0.25 cheaper later in the day. The entry snapshot already saves the time; Performance would group by morning, midday and afternoon.

### Leave for later

- **Multiple accounts.** Switch between accounts, for example an IRA and a regular brokerage account, with each account's trades, Holdings and Performance kept separate. To make this a small addition later, every trade stores an `account` from day one (default `"Paper"`), and services take an optional `account` argument that defaults to it. Adding accounts later is then an account picker in the UI plus a filter in the services, with no change to existing data.
- **Adjustments.** On the way up, Tom rolls to a higher strike as one 4-leg order, bidding about $0.20 under and letting a small dip fill it. On the way down, he adds put diagonals on the same expiries, about 10 points wide and about 1.5 short deltas per contract, when the short leg's IV has risen more than the long's. These need Vol P&L history first, and each should be paper-tested on its own before it becomes a rule: the roll moves the position, while the diagonal adds to it.
- **Vol P&L on the Finder.** Once `finder_log` has a few weeks of closes, show each row's Vol P&L since the previous close and its price change, so you can screen for spreads that volatility has just made cheap, as Tom does.
- **A caveat on Tom's results.** He showed one month (13 trades, 12 winners, about 2 days each) and stressed judgment. The groupings and the exit-target comparison above test his ideas on your own paper trades before any of them become rules.

Open questions:

- [ ] Is the −10% flag an exit for paper trading, or only a warning?
- [ ] Stability test: is a $0.10 range over 10 seconds right, or should it loosen on fast days?
- [x] Break-evens at the short expiry (the thinkorswim default), or at your 7-day exit date? **Decided: short expiry.**
- [ ] Delta band: keep 35–45Δ around the 40Δ target, or tighten to 38–42Δ?
