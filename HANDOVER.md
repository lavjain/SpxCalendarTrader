# Handover

Updated at the end of every work session (≤ 20 lines). Newest first.

## 2026-11-23 — week 3 steps 1–7 built (needs your first run of the dialog)
- Done and committed (one commit per plan step): leg symbols + stability check, `trades` table (schema v3), `quote_spread`/`open_trade` services, `/api/quote-spread` + `/api/trades`, Open Trade dialog, Copy to TOS, Paste from TOS. 241 py tests + 37 js tests pass in a sandbox; the route tests (FastAPI) and the dialog have NOT run in a browser yet.
- Decided Nov 23: stability wait switched off (`config.REQUIRE_STABLE = False`); bid-ask limit is per leg; Finder lists 40–50Δ with 45Δ target (`near_target_delta`, `is_near_target_delta` column); T/D = theta / |delta|; Size By to Contracts starts at 10; DTE sliders push each other; holiday note under Days Between.
- Not done: risk profile tab and ⓘ popovers (steps 8–9), the "Still not stable" Keep Waiting prompt, Paste for a different calendar / fill time, entry snapshot from `finder_log`, the wrap-up run of three real trades.
- Yours: add `tests/fixtures/tos_order_samples.txt` (Copy/Paste format is from docs/PLAN.md, unchecked against real lines); re-run `uv run --group mockups python docs/mockups/render.py` and commit the new PNGs; check the holiday names in `config.HOLIDAY_NAMES`; push the local commits.
- First run: `uv run pytest` (route tests run for the first time), then Finder → Refresh → Open Trade…, then `sqlite3 data/paper_trades.db "select * from trades;"`.

## 2026-11-23 — week 2 built (needs your first run)
- Done and tested in a sandbox (166 py tests + 29 js tests): td dash near zero delta, IVs implied from mids, per-row break-evens, `get_spot`, `get_expirations`; `app/` FastAPI factory (`create_app`), `/api` health, spot, expirations, finder refresh/get, settings; SQLite `Store` (settings, `finder_log`, one row per strike); snapshots in memory (5, 10 min) and saved to data/snapshots.json (one file, newest 20); shared Python/JS formatters; Finder page (filters, status strip, Calendars table with strike rows, calendar panel with tiles and legs).
- NOT run yet: the FastAPI layer (no FastAPI in the sandbox). First run: `uv sync` (commit `uv.lock`), `uv run pytest` (tests/test_routes.py runs for the first time), `node --test tests/js/*.test.mjs`, `uv run serve`, open http://127.0.0.1:8000.
- Deviations from WEEK2.md: break-evens per row in `get_finder()` (no `get_calendar_detail`); Refresh = JS fetch POST then `htmx.ajax` GET of partials; `create_app` factory; node glob form.
- Sizing now rounds margin to the NEAREST whole contract (`config.SIZE_ROUNDING`; `Calendar(rounding=...)` keeps `ceil` as its default so the spreadsheet self-test still matches). CLI has full `--help` with defaults.
- Decided Nov 23: position delta, gamma and T/D come from the model at mid-implied IVs (`config.MODEL_GREEKS = True`), because Schwab rounds greeks to 3 decimals. The model's delta differs from Schwab's by about 0.01 per leg (7140 calendar: -1.5 vs -3.2 position delta); thinkorswim also differs slightly from Schwab and Lav accepts that, so no thinkorswim delta check is planned.
- Open decisions: snapshots now also on disk; T/D shown to 2 decimals, dash threshold 2.0; "Open trade" disabled until week 3; NYSE holiday list for 2026-27 still unverified.
- Step 10 (yours): paste a real thinkorswim order into `tests/fixtures/tos_order_samples.txt`.

## 2026-11-23 — week 1 implemented in `app/core/`; live and thinkorswim checks done
- Done and committed step by step: `app/core/` layout (self-test now `uv run pytest tests/test_calendar_math.py`, 16 rows), `config.py` + `models.py`, `expiries.py` (NYSE holidays 2026–27, Thursday rule), `schwab_api.py` items 1–5 and item 6 (separate commit), `pricing.py`, `services.get_finder()` + `cli.py`, 93 tests green on fixtures.
- Live checks done Nov 23: Schwab login, live pull and `cli candidates` work. thinkorswim check PASSED (-3.1% / -0.7%) once pricing used IVs implied from mids: Schwab's `volatility` field doesn't reproduce its own marks (see `tests/fixtures/tos_check.md`). Still to do: `uv sync` / `uv run pytest` on Python 3.12 (tests ran on 3.13 in a cloud sandbox).
- Check on the first live pull: the contract field `optionRoot` (code falls back to the `symbol` prefix if absent); the call request (`contractType=CALL&strikeCount=6`, `config.CALL_STRIKE_COUNT`) and its payload size; the quotes response keys in `get_quotes()` (`bidPrice`, `askPrice`, `mark`, `lastPrice`).
- Changes beyond WEEK1.md: `calendar_math.py` repo-root path fixed for its new folder; `OptionQuote.right` ("P"/"C"); `PairSummary.break_evens` (of the ~40Δ row); `config.CALL_STRIKE_COUNT`; `schwab_api.parse_parity_quotes()` (puts + calls at common strikes for the forward); `chain` command without `--demo` is now a live pull with default Finder filters (old CSV output only with `--demo`); token refresh lock is a `threading.Lock` (calls run in threads), not `asyncio.Lock`; old token files with `obtained_at` still read.
- Open: holiday list is hard-coded 2026–27 (verify against NYSE); r = 4% and carry implied from parity (no q input); break-evens priced on `mark` mids; day count = calendar days / 365.
- Open decision: the Finder's displayed IV/skew columns still use Schwab's IV (matches Lane's sheet logic, but is ~1.3 vol points below tos); `short_iv_implied`/`long_iv_implied` on `CalendarRow` hold the mid-implied IVs used for P/L. `cli diagnose --tos LOWER UPPER` shows the inputs.
- Next: week 2 (FastAPI shell + Finder page).

## 2026-11-19 — stack changed to FastAPI + HTMX + vanilla JS (docs and mockups only, no code yet)
- Decided: no Streamlit. FastAPI + Jinja templates + HTMX + vanilla JS ES modules, Tailwind from CDN (dark default, theme toggle), canvas risk profile, Lightweight Charts for SPX candles, Chart.js for Performance. All trading logic in `app/core/` (no web imports); `app/core/config.py` replaces `settings.py` for trading numbers; `app/settings.py` is pydantic-settings for env vars. Start with `uv run serve`.
- Decided: every saved setting (Finder settings, Holdings columns, Closed window, chart chips) lives in SQLite per account; only the theme is in localStorage. Marks saved every Refresh, at most every 5 min while polling, and at the 4:15 PM close. Forward from put-call parity, so the chain pull adds calls near the money.
- Decided: Application Phase 2 (after Release 2) = interactive Analyzer (browser-side math with a Python parity test, models saved in the DB) + optional Railway hosting. Release 1 risk profile is read-only canvas.
- Schwab budget: batched quotes, 15–30 s cache, ≤4 in flight, ≤100/min limiter; ~35 req/min at the busiest.
- Found in review of `schwab_api.py` (fix in week 1, step 4 item 6, as a separate commit): `obtained_at` reset on every refresh so the 7-day warning never fires; `sys.exit` on errors; `date.today()` not ET; missing mark/bid/ask become 0; `--flow schwabpy` token breaks `access_token()`; puts-only pull can't give a parity forward.
- Updated: CLAUDE.md, docs/PLAN.md (architecture, screens, weeks 1–2, Application Phase 2), docs/WEEK1.md (move to `app/core/`, step 4 items 5–6), README, CONTRIBUTING, mockups (new header, ⓘ popovers, Tailwind slate palette) and docs/images/.
- Not yet changed (they change with the code): `pyproject.toml` (week 2: add fastapi/uvicorn/jinja2/pydantic-settings, drop streamlit, add the `serve` script), `.vscode/launch.json` (week 1–2).
- Redesigned the Finder and Holdings layouts (no more Streamlit shapes): Finder = filter bar + status strip + Calendars table (strike rows open under the selected pair) + a selected-calendar panel (Risk profile / SPX chart tabs, tiles, legs with skew and IV ratio); Holdings = cards + Open table and Closed list + a selected-trade panel (Close trade…, Notes, Copy closing order). Risk graph: sky expiry line, pink T+0, profit/loss shading, ±1 SD band. `finder-collapsed.png` replaced by `finder-spx.png`.
- Schedule review (Nov 19): dates and weekdays check out (weeks run Tue–Mon; Thanksgiving Nov 26, Christmas Dec 25, New Year Jan 1, MLK Jan 18). Weeks 2 and 4 were overloaded, so: the risk-profile tab/canvas and ⓘ popovers moved week 2 → week 3; both SPX charts moved week 4 → week 5; paper trading starts mid-week 4 and runs through week 6; Holdings History tab added to week 7. Week 1 (Thanksgiving, includes the Schwab hardening) is still the tightest; if it slips, the hardening can finish early in week 2.
- Rule made explicit (Nov 19): if a Friday is a market holiday, the short AND the long both move to the Thursday before; widths are counted from the nominal Friday. Added test cases to WEEK1 step 3.
- Next: week 1, step 0.

## 2026-11-18 (later) — risk profile, SPX chart, Performance tabs, two releases
- Added to the plan and mockups: risk profile (Black-Scholes repricing on an SPX grid, Plotly at the time, now a canvas; in Finder and Holdings), SPX daily chart on the Finder (3 months default, strike and break-evens drawn on, bars cached in `spx_daily`), collapsible settings sidebar with a settings bar (superseded by the filter bar layout), Performance sub-tabs (Summary, By period, By condition, Exits, Trades) with a mockup for each.
- Decided: keep 6 weeks for Release 1 (core loop); extras and anything that slips go to Release 2, Jan 5–18, 2027. SPX chart moved from week 2 to week 4 (basic version).
- New service functions: `get_risk_profile()`, `get_spx_history()`; new files planned: `charts.py`. (Plotly was dropped; the risk profile is a canvas.)

## 2026-11-18 — repo set up
- Done: starting code (`schwab_api.py`, `calendar_math.py`, self-test 16/16); README, CONTRIBUTING, LICENSE, VS Code config; docs/PLAN.md, docs/WEEK1.md; dark-theme mockups in docs/images/ generated by docs/mockups/.
- Decided: break-evens at the short expiry (thinkorswim default); Python 3.12; Schwab keys in `.env`, loaded with `uv run --env-file .env`; app starts with `uv run app.py`; dialogs say "Open trade" / "Close trade"; Copy to TOS buttons copy order lines only (no orders sent).
- Added to the plan from Tom Conley's session: Vol P&L, delta-per-contract flag, full strike ladder in `finder_log`, vol-at-entry grouping, exit-target comparison; Performance gets period filter, Month/Week grouping, wins/losses chart.
- Finder filters added: short-leg DTE range 7–56 (default 25–35), widths 3–7 days as on/off chips (default 7), strikes 10s + 25/75 or 25s; Size by margin (default $10,000) or contracts. Finder = Overview (one row per short/long pair at ~40Δ, sortable) + Detail (all strikes of the selected pair). Default trade unchanged.
- Next: docs/WEEK1.md Step 0 (`uv sync`, commit `uv.lock`, create `.env`), then Step 2.
- Schedule: Release 1 in 6 weeks, Nov 24, 2026 – Jan 4, 2027; Release 2 Jan 5–18 (docs/PLAN.md). Finder in week 2, opening trades week 3, Holdings week 4, Performance weeks 5–6.
- During week 2: copy a real calendar order from TOS to confirm the Copy to TOS line format (used from week 3).
- Open: questions at the end of docs/PLAN.md.
