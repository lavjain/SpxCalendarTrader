# Week 2 — App skeleton and Finder screen (Dec 1–7)

Give Claude Code one step at a time. Finish each step's check before moving on, and commit after each step.
Week 1 was all `app/core/` (plain Python). This week adds the web layer around it: FastAPI, Jinja templates, HTMX and a little vanilla JS. Layout and rules: `CLAUDE.md` (especially rules 1–5: no web imports in `app/core/`, one service per endpoint, Pydantic in and out, the UI only displays, raw numbers out and formatting at the edge). Screen design: `docs/PLAN.md` → Screen 1, and `docs/images/finder.png`.
**Week done when:** `uv run serve` serves the Finder, pressing Refresh fills the Calendars table and the selected-calendar panel for the chosen filters, the filters are still there after a reload, and the default pair's numbers (~40Δ strike, price, contracts, skew, break-evens) match `uv run --env-file .env python -m cli candidates`.

---

> **Status (Nov 23).** Steps 1–9 are written and committed; 168 Python and 29 JavaScript tests pass in the cloud sandbox. Not yet done: **the FastAPI layer has never run** (no FastAPI in the sandbox), so `tests/test_routes.py` and `uv run serve` are untested; **Step 10** (a real thinkorswim order into `tests/fixtures/tos_order_samples.txt`, yours); **Step 11** checks below. Deviations from this plan: break-evens per row (no `get_calendar_detail`); Refresh is a JS `fetch` POST then an `htmx.ajax` GET of `/partials/results`; `create_app` factory; snapshots also saved to disk; Step 9's error banner is in the page but has no browser test yet.
>
> **First run on your Mac:** `uv sync` (commit `uv.lock`), `uv run pytest`, `node --test tests/js/*.test.mjs`, `uv run serve`, open <http://localhost:8000>, press Refresh, compare the default pair with `uv run python cli.py candidates`, press Refresh twice and check `finder_log` row counts (`sqlite3 data/paper_trades.db "select count(*) from finder_log"`), then stop and restart the server.

## Step 0 — Baseline and push
- **Build:** nothing new. `uv run pytest` is green (97 tests), `git status` is clean. Push the week-1 commits to GitHub (`git push`) so there is a backup before the web layer goes in.
- **Check:** `git log origin/main..HEAD` is empty after the push; `git log --stat origin/main | grep -E "\.env|token|data/"` prints nothing.

## Step 1 — Two small core fixes the screens need
- **Build:** (1) `CalendarRow.td` becomes `float | None`: `None` when the position delta is near zero (`config.TD_MIN_DELTA = 2.0`, in position delta), since T/D means nothing there and `calendar_math` returns NaN at exactly 0 (NaN breaks the JSON round trip). The UI shows "—". (2) **IV shown and used for skew** (see Decisions, no. 1): pass the mid-implied IV (`short_iv_implied` / `long_iv_implied`, week 1) into the `Leg` handed to `calendar_math` when it exists, falling back to Schwab's `volatility` otherwise, so `skew`, `short_iv` and `long_iv` match thinkorswim. Add `iv_ratio` (short IV ÷ long IV) to `CalendarRow`. Do not touch `calendar_math.py` or its expected numbers; the change is in `services._leg()`.
- **Files:** app/core/config.py, app/core/models.py, app/core/services.py, tests/test_services.py, tests/test_models.py
- **Check:** a test gives a row with position delta 0 and round-trips it through JSON; a test shows `skew` equals `short_iv − long_iv` using the implied IVs; the 16-row self-test still passes; `uv run --env-file .env python -m cli candidates` skew values now sit close to thinkorswim's (about 0.7 on the Nov 23 example, not 0.85).

## Step 2 — Dependencies, project config and the app shell
- **Build:** `uv add fastapi "uvicorn[standard]" jinja2 pydantic-settings` and `uv remove streamlit`; commit `uv.lock`. In `pyproject.toml` add `[build-system]` (hatchling) with `[tool.hatch.build.targets.wheel] packages = ["app"]`, `[tool.uv] package = true` and `[project.scripts] serve = "app.main:serve"`. `app/settings.py` (pydantic-settings): `SCHWAB_APP_KEY`, `SCHWAB_APP_SECRET`, `SCHWAB_CALLBACK_URL`, `SCHWAB_TOKEN_PATH`, `DB_PATH`, feature flags. `schwab_api.py` keeps reading its keys from the environment for now (don't rewire it this week). `app/main.py`: the FastAPI app, `/static` mount, `Jinja2Templates`, a lifespan hook, `serve()` calling `uvicorn.run("app.main:app", reload=True, env_file=".env")`, and `GET /api/health` returning status and app version. `.vscode/launch.json`: an **App** configuration (uvicorn with reload) in place of the old Streamlit one.
- **Files:** pyproject.toml, uv.lock, app/settings.py, app/main.py, .vscode/launch.json, tests/test_api_health.py
- **Check:** `uv run serve` starts on http://localhost:8000; `/api/health` answers; `/docs` lists it; `uv run pytest` still green; `grep -n streamlit pyproject.toml uv.lock` prints nothing; `grep -rn "fastapi\|starlette\|jinja2" app/core` prints nothing.

## Step 3 — SQLite store: settings and finder_log
- **Build:** `app/core/store.py` (plain `sqlite3`, no web imports): opens `DB_PATH`, creates tables if missing (schema version in a `meta` table). **`settings`**(account, key, value JSON, updated_at) with `get_setting(account, key, default)` / `put_setting(...)`. **`finder_log`**: one row per strike of every pair on a Refresh: time (ET), trade date, `is_close_snapshot` (0 now; the 4:15 PM job comes later), SPX, VIX, VIX9D, the filters used, expiries, DTEs, width, strike, short Δ, short and long marks and bid/ask, both IVs, skew, price, margin, break-evens (of the ~40Δ row) and flags. Function `log_finder(result, vix, vix9d)`. `trades`, `marks` and `spx_daily` come in later weeks.
- **Files:** app/core/store.py, tests/test_store.py
- **Check:** tests on a temporary database: settings round-trip per account (two accounts don't mix); `log_finder()` on the fixture result writes one row per strike with the right flags; reopening the database keeps the data; `git status` shows no `data/` or `*.db`.

## Step 4 — API: validation, errors, spot, expirations, settings, finder
- **Build:** `app/schemas.py`: `FinderFilters` (DTE range inside `config.SHORT_DTE_LIMITS`, widths from `config.WIDTHS`, strike sets, size mode and a positive size, whole number for contracts), reused as the query/body model so bad input gets a 422. Exception handlers in `main.py`: `SchwabAuthError` → 503 and `SchwabHTTPError` → 502, each with a plain message the page can show (e.g. "Schwab login expired: run the weekly auth"). Routers under `app/api/`, every endpoint with a `response_model`, blocking Schwab calls through `asyncio.to_thread`:
  - `services.get_spot()` (one `get_quotes(["$SPX","$VIX","$VIX9D"])` call) → `GET /api/spot`
  - `services.get_expirations(filters)` (wraps `pick_expiries`, also says which widths have no pair this week) → `GET /api/expirations`
  - `GET /api/settings/{key}` and `PUT /api/settings/{key}` (account "Paper")
  - `POST /api/finder/refresh` → `get_finder()` once, writes `finder_log`, keeps the `FinderResult` in a small in-memory store under a `snapshot_id` (last 5 in memory, ten-minute life; also saved as JSON in the one file `data/snapshots.json`, newest 20, which never expire), returns it with the id; `GET /api/finder?snapshot_id=…` returns a stored snapshot (404 if gone)
- **Files:** app/schemas.py, app/api/__init__.py, app/api/market.py, app/api/finder.py, app/api/settings.py, app/main.py, app/core/services.py, tests/test_api_*.py
- **Check:** `TestClient` tests with Schwab mocked: each route returns its model; a bad filter gives 422; an expired-login error gives 503 with the message; settings round-trip; Refresh writes `finder_log` rows and returns a `snapshot_id` that `GET /api/finder` resolves. `/docs` documents all of it.

## Step 5 — Templates, theme and formatting
- **Build:** `app/pages.py`: the shared `Jinja2Templates`, the filters `money`, `pct`, `signed`, `pts` (the same rules as `static/js/lib/format.js`), `page_context(request, active_tab)` (feature flags, active tab, app version, account), and `GET /` → redirect to `/finder`. `templates/base.html`: Tailwind CDN with the colors from CLAUDE.md (`primary` = `#1C83E1`, slate surfaces, `dark` class on `<html>` set from `localStorage` before the page draws, dark by default), HTMX from its CDN, `{% extends %}` blocks; `_header.html` (name and version, tabs Finder / Holdings / Performance with the last two disabled, account "Paper", theme toggle), `_footer.html` (version, "paper trading only", last refresh time). `static/js/lib/theme.js`, `static/js/lib/format.js`, `static/css/style.css` (small overrides only). `finder.html` is an empty shell with the two columns.
- **Files:** app/pages.py, app/templates/base.html, _header.html, _footer.html, finder.html, app/static/js/lib/theme.js, format.js, static/css/style.css, tests/js/format.test.mjs
- **Check:** `/finder` renders in dark and light and the toggle sticks after a reload (and is the only thing in `localStorage`); `node --test tests/js/*.test.mjs` passes and `format.js` imports with no browser; a Python test checks the Jinja filters give the same strings as the JS cases (one shared list of examples).

## Step 6 — Filter bar and status strip
- **Build:** `partials/_finder_filters.html` + `static/js/finder.js`: Short DTE range slider (7–56, default 25–35), width chips 3–7 (default 7; a chip is crossed out when `get_expirations` says no pair exists that week), strike chips 10s / 25s (default both), Size by Margin (default $10,000) or Contracts, **↻ Refresh** and the time of the last pull. The page renders with the saved filters (read from the `settings` table on the server); each change is saved with `PUT /api/settings/finder_filters`. `partials/_status_strip.html`: time (ET), SPX, the short expiries in range with their DTEs, widths on, sizing. Components are named `FinderFilters` and `StatusStrip` (CLAUDE.md rule 13).
- **Files:** app/templates/partials/_finder_filters.html, _status_strip.html, app/partials.py, app/static/js/finder.js
- **Check:** change the filters, reload, and they are as you left them; a width with no expiry that week is crossed out; narrowing the DTE range to one week shows one short expiry in the strip; Refresh with Schwab logged out shows the "run the weekly auth" message instead of a stack trace.

## Step 7 — Calendars table
- **Build:** `partials/_calendars_table.html` (`CalendarsTable`) and `partials/_strike_rows.html` (`StrikeRows`), served from `/partials/calendars` and `/partials/strike-rows`, both reading the stored snapshot (they compute nothing). One row per short/long pair at its ~40Δ strike, split into one segment per width (header such as "7-day width · 2 pairs"), narrowest first; first cell "Thu Dec 24 → Thu Dec 31" with DTEs and strike count; columns ~40Δ strike, Contracts, Price, Theta, Vega, Skew, Θ/Mgn, Best skew (value and strike). Clicking a column header re-sorts within each segment (`?sort=`). Clicking a pair opens its strike rows underneath (one open at a time): Strike, Short Δ, Contracts, Price, Margin, Delta, Gamma, Theta, Vega, Skew, T/D to 2 decimals ("—" when `None`), Θ/Mgn; ★ on `is_near_target_delta`. Markers per CLAUDE.md: amber left edge on the best-skew pair and strike, blue tint and edge on the selected ones, thin separators, no vertical gridlines, right-aligned tabular digits, sticky header. On first load the pair holding the default trade (short nearest 30 DTE, 7 days wide) is open with its ~40Δ strike selected; selection lives in `finder.js`, never stored.
- **Files:** app/templates/partials/_calendars_table.html, _strike_rows.html, app/partials.py, app/static/js/finder.js, tests/test_partials.py
- **Check:** partial tests on the fixture snapshot: segments in width order, exactly one ★ and one amber edge per open pair, "—" for a `None` T/D, sort order within a segment, no number formatted in the service output; in the browser, Refresh fills the table, clicking pairs and headers behaves as described.

## Step 8 — Selected calendar panel
- **Build:** `partials/_calendar_panel.html` (`CalendarPanel`) and `partials/_legs_table.html` (`LegsTable`) from `/partials/calendar-panel?snapshot_id=&short=&long=&strike=`, which stays in view while the tables scroll. Title (strike, expiries, width, contracts × price, with the +$0.10 fill shown), **Open trade…** (present but disabled with a tooltip "opens in week 3"), tiles for Cost, Break-evens, Delta, Theta / day, Vega / pt (done differently from the first draft: `get_finder()` now computes `break_evens` for every `CalendarRow`, so there is no `get_calendar_detail` and nothing to re-pull), and the Legs table (both puts: expiry and DTE, mark, bid/ask, delta, vega, IV, then Skew and IV ratio). No Risk profile or SPX chart tab yet (weeks 3 and 5). Clicking a strike swaps the panel with HTMX.
- **Files:** app/core/services.py, app/api/finder.py, app/templates/partials/_calendar_panel.html, _legs_table.html, app/partials.py, tests/test_services.py, tests/test_partials.py
- **Check:** a test calls `get_calendar_detail()` for a non-40Δ strike and gets break-evens that straddle that strike; the panel for the default pair's ~40Δ strike shows the same break-evens as `cli candidates`; selecting another strike updates the panel without a full page load.

## Step 9 — Finder log and error handling, end to end
- **Build:** make sure every Refresh (and only a Refresh, not a click or a poll) writes the whole strike ladder to `finder_log`; the page shows API errors (401/502/503, "snapshot expired, press Refresh") in a banner under the filter bar; the footer's "last refresh" comes from the last snapshot. No polling this week.
- **Files:** app/api/finder.py, app/templates/finder.html, app/static/js/finder.js, tests/test_api_finder.py
- **Check:** pressing Refresh twice writes two ladders; clicking pairs and strikes writes none; an expired snapshot gives the banner message; stop the server, start it again, and the log from before is still in `data/paper_trades.db`.

## Step 10 — Copy a real thinkorswim order (you, not Claude)
- **Build:** in thinkorswim, set up a put calendar order (BUY the long, SELL the short, same strike; do not send it) and copy its order text. Save it, with the date and what the legs were, in `tests/fixtures/tos_order_samples.txt`. Week 3's "Copy to TOS" and "Paste from TOS" are built from the exact format, including how a Thursday weekly expiry such as 24 DEC 26 is written.
- **Files:** tests/fixtures/tos_order_samples.txt
- **Check:** the file has at least one real BUY and one real SELL calendar line, plus a note on any `(Weeklys)` or `(AM)` tags it shows.

## Step 11 — Wrap up
- **Build:** compare the page and the CLI for the default pair (strike, price, contracts, skew, break-evens) and record the match in HANDOVER.md; update HANDOVER.md (what works, open decisions) and the README run instructions (`uv run serve`); update the week-2 boxes in `docs/PLAN.md`. Push to GitHub.
- **Check:** `uv run pytest` and `node --test tests/js/*.test.mjs` all green; `git status` clean; `grep -rn "fastapi\|starlette\|jinja2" app/core` prints nothing; no `data/`, `.env` or token in `git log --stat`.

---

## Decisions I would make (change any before starting)
1. **IVs shown and used for skew** switch to the mid-implied IVs (Step 1), so the Finder agrees with thinkorswim (skew about 0.7, not 0.85) and "best skew" ranks the same way. The sheet-reproduction test is unaffected because it feeds the sheet's own IVs.
2. **Snapshots in memory:** the table, strike rows and panel all read one stored `FinderResult` per Refresh, so clicking never re-pulls Schwab and the three always agree. Each snapshot is also saved to `data/snapshots.json` (one file, newest 20), so after a restart the page reopens on the newest one, with its time in the status strip; delete the file to clear them.
3. **Spot, VIX and VIX9D from one `get_quotes` call**, not from the chain's `underlyingPrice`, so the status strip and `finder_log` use the quote Schwab updates most often.
4. **Filters in `app/pages.py`** (Jinja filters and `page_context`), so the layout in CLAUDE.md doesn't gain a file.
5. **Refresh is a POST** (`/api/finder/refresh`) because it writes `finder_log`; the GET only reads a stored snapshot.
6. **T/D shows "—"** when the absolute position delta is under 0.5 (`config.TD_MIN_DELTA`, was 2). T/D is theta divided by the **absolute** position delta (changed in week 3), so it has the same sign as theta.
7. **Open trade… is visible but disabled** this week, so the panel matches the mockup.
