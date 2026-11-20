# Week 1 — Schwab data and calendar pricing (Nov 24–30)

Give Claude Code one step at a time. Finish each step's check before moving on, and commit after each step.
This week is all `app/core/` (plain Python, no web code); the FastAPI app itself starts in week 2. Layout and rules: `CLAUDE.md`.
**Week done when:** `uv run --env-file .env python -m cli candidates` prints today's 35–45Δ put calendars, and one calendar's break-evens are within ~5% of thinkorswim Analyze.

---

## Step 0 — Repo baseline
- **Build:** `pyproject.toml`, `.python-version`, `.gitignore`, `tests/` and `HANDOVER.md` already exist. Run `uv sync` to create `.venv/` (Python 3.12, pinned in `.python-version`) and `uv.lock`, and commit `uv.lock`. Copy `.env.example` to `.env` and add your Schwab keys; commands that call Schwab run as `uv run --env-file .env …`. (The optional `mockups` group is only for `docs/mockups/`.)
- **Files:** uv.lock, .env (not committed)
- **Check:** `uv run python -c "import pandas, numpy, scipy, pydantic"` succeeds; `git status` shows no `data/` or `.env`.

## Step 1 — Starting files (done Nov 18)
`schwab_api.py`, `calendar_math.py` and `README.md` are in place; `calendar_math.py` logs to `data/`.
- **Check:** `uv run python calendar_math.py selftest` prints "16/16 rows reproduce exactly." and `uv run python schwab_api.py chain --demo` parses the demo chain.

## Step 2 — Move into `app/core/`, and the self-test as pytest
- **Build:** create `app/__init__.py` and `app/core/__init__.py`; `git mv` `calendar_math.py` and `schwab_api.py` into `app/core/` with no other changes to them. Update the two places that run them: `docs/mockups/data.py` (`from app.core.calendar_math import Leg, Calendar`) and the Self-test / Schwab demo entries in `.vscode/launch.json` (`"module": "app.core.calendar_math"` etc.). Then `tests/test_calendar_math.py` runs the Lane 2021-09-17 data (`LANE_2021_09_17` vs `LANE_EXPECTED`) through `build()` and asserts all 16 rows with the same tolerances as `selftest()`. Don't edit the expected numbers.
- **Files:** app/__init__.py, app/core/__init__.py, app/core/calendar_math.py, app/core/schwab_api.py (moved), docs/mockups/data.py, .vscode/launch.json, tests/test_calendar_math.py
- **Check:** `uv run pytest tests/test_calendar_math.py` → 16 rows pass. `uv run python -m app.core.calendar_math selftest` still prints "16/16 rows reproduce exactly." and `uv run python -m app.core.schwab_api chain --demo` still parses the demo chain.

## Step 3 — config.py and models.py skeleton
- **Build:** `app/core/config.py` with constants: `MARGIN = 10_000` (default when sizing by margin), `SIZE_MODES = ("margin", "contracts")`, `FILL_OFFSET = 0.10`, `DELTA_TARGET = 0.40`, `DELTA_BAND = (0.35, 0.45)`, `SHORT_DTE_TARGET = 30`, `SHORT_DTE_DEFAULT = (25, 35)`, `SHORT_DTE_LIMITS = (7, 56)`, `WIDTHS = (3, 4, 5, 6, 7)`, `WIDTHS_DEFAULT = (7,)`, `STRIKE_SETS = ("10", "25")` (multiples of 10 and/or 25; default both), `MAX_DTE = 63` (56 + 7), `STABLE_RANGE = 0.10`, `STABLE_QUOTES = 5`, `QUOTE_INTERVAL_S = 2`, `MAX_SPREAD_PCT = 0.10`, `WAIT_TIMEOUT_S = 60`, `FLAG_LOSS = -0.10`, `FLAG_TARGET = 0.10`, `MAX_DELTA_PER_CONTRACT = 2.0`, `CLOSE_SNAPSHOT_ET = "16:15"`, `MARKET_TZ = "America/New_York"`, `HOLDINGS_POLL_S = 30`, `MARKS_EVERY_S = 300`, `CACHE_TTL_S = 20`, `SCHWAB_MAX_CONCURRENT = 4`, `SCHWAB_REQUESTS_PER_MIN = 100`, `RATE = 0.04`, `DB_PATH = "data/paper_trades.db"`. `app/core/models.py` with Pydantic models for week 1: `OptionQuote` (expiry, strike, bid, ask, mark, delta, gamma, theta, vega, iv), `ExpiryPair` (short, long as ISO dates, dte each, width), `CalendarRow` (strike, width, short/long legs, contracts, price, margin, greeks, short and long IV, short and long vega, skew, td, theta_margin, `is_best_skew`, `is_near_40_delta`), `BreakEvens` (lower, upper, at_date), `PairSummary` (short and long expiry, DTEs, width, the ~40Δ `CalendarRow`, best skew and its strike, strike count), `FinderResult` (time, spx, filters used, pairs: list of `PairSummary` each with its rows).
- **Files:** app/core/config.py, app/core/models.py, tests/test_models.py
- **Check:** a test round-trips each model with `model_dump_json()` / `model_validate_json()`; the only number types are `float`/`int` (no numpy).

## Step 4 — schwab_api fixes (the four from the plan, plus making it safe for a web server)
- **Build:**
  1. **One strike for both legs.** Add `calendar_legs(rows, short_exp, long_exp, strike)` that returns the short and long put at the same strike. Drop the per-expiry `nearest()`/ATM path from the app's flow (leave it for the CLI if handy).
  2. **35–45Δ puts for the chosen expiries only.** `get_chain` requests `fromDate`/`toDate` covering the short Fridays in the DTE range through the last long expiry; `parse` keeps puts with |Δ| in `config.DELTA_BAND` on each short expiry, on the strikes switched on (multiples of 10 and/or 25), plus the put at each of those strikes on every long expiry 3–7 days later (whatever its delta).
  3. **SPXW on the third Friday.** On monthly expiry, the chain returns both SPX (AM-settled) and SPXW (PM-settled). Keep only `optionRoot == "SPXW"` (check the field name against a live pull or the README notes).
  4. **Limit to 63 DTE** (8-week short + 7-day width). Default `dte_max = config.MAX_DTE`; reject anything past it. A 60-DTE `range=OTM` pull was ~7 MB in testing, so this should stay under Schwab's size limit; check once.
  5. **Calls near the money, for the forward.** Put-call parity needs a call and a put at the same strike, and the pull is puts only today. Also request the few calls nearest the money on each expiry the Finder uses (e.g. a second request with `contractType=CALL`, `range=NTM`, or `contractType=ALL` with a `strikeCount`, whichever is smaller; check the payload size once).
  6. **Safe to call from a web server.** These came out of the migration review; commit them separately from items 1–5, since they change existing behaviour:
     - raise exceptions (`SchwabAuthError`, `SchwabHTTPError`, …) instead of `sys.exit()` in `cfg()`, `access_token()`, `get_chain()` and `extract_code()`; the command-line `main()` catches them and exits with the same messages as now
     - keep the login time separate from the access-token time: today `post_token()` resets `obtained_at` on every refresh, so the 6.5-day warning never fires. Store `login_at` (set by `auth` only) and `access_at` (set on every refresh); the 7-day check uses `login_at`
     - a lock around token refresh, so several requests at once don't refresh and rewrite the token file together
     - market dates from `config.MARKET_TZ`, not `date.today()` on the machine's clock
     - a missing mark, bid or ask becomes `None` (row skipped or flagged), not 0
     - `--flow schwabpy` writes to its own token path (or is removed), since its token format breaks `access_token()`
     - a small TTL cache (`config.CACHE_TTL_S`) for chain and quote pulls, a limit of `config.SCHWAB_MAX_CONCURRENT` requests in flight, a `config.SCHWAB_REQUESTS_PER_MIN` limiter, and backoff on HTTP 429
  Parse into `OptionQuote` models, keep bid and ask (needed for the fill rules). Keep the token path at `~/.schwab/` and add the quote helper `get_quotes(symbols)`, which takes many symbols in one call (`$SPX`, `$VIX`, `$VIX9D` and option legs).
- **Files:** app/core/schwab_api.py, app/core/config.py, tests/test_schwab_api.py, tests/fixtures/chain_sample.json
- **Check:** tests on a saved fixture (save one real pull to `tests/fixtures/` after removing anything account-specific, or extend the DEMO fixture with a third-Friday SPX+SPXW duplicate): same strike on both legs, only 35–45Δ short strikes on the chosen spacing, no SPX-AM rows, nothing past 63 DTE, a call at the strike nearest the money on each Finder expiry, no `sys.exit` left in the module (`grep -n sys.exit app/core/schwab_api.py` shows only `main()`), and the login age surviving a token refresh. Then one live pull with the default filters (`uv run --env-file .env python -m app.core.schwab_api chain`) returns rows for exactly two expiries (one short Friday, its 7-day long).

## Step 5 — Expiry picker
- **Build:** `pick_expiries(today, dte_range=(25, 35), widths=(7,)) -> list[ExpiryPair]` in `app/core/expiries.py`, with dates in `config.MARKET_TZ`: one short per Friday whose DTE is inside `dte_range` (allowed 7–56); for each width, long = that Friday + width days. A short Friday that is a holiday moves to the Thursday before, and a long date that isn't a trading day moves back the same way (a 7-day long on a Friday holiday becomes that Thursday); widths are always counted from the nominal Friday, not from the adjusted Thursday, and the pair is dropped if that's on or before the short. DTE is counted to the actual expiry. Holidays come from a small hard-coded set in `app/core/config.py` for 2026–2027 (incl. Dec 25 2026, Jan 1 2027, Good Friday Mar 26 2027, Juneteenth observed Fri Jun 18 2027; check the full list against the NYSE holiday calendar).
- **Files:** app/core/expiries.py, app/core/config.py, tests/test_expiries.py
- **Check:** tests include: from **Tue Nov 24 2026** with defaults → short **Thu Dec 24** (Dec 25 holiday), long **Thu Dec 31** (Jan 1 holiday); from **Tue Jan 12 2027**, widths 3–7 on the Feb 12 short → longs Feb 16, 17, 18, 19 and **no 3-day pair** (Mon Feb 15 is Presidents' Day); a DTE range of 7–56 returns 7 or 8 Fridays; a Good Friday case (short Fri Mar 26 2027 → Thu Mar 25, long Fri Apr 2); a Friday-holiday *long* (short Fri Dec 18 2026, 7-day long → Thu Dec 24); and the same for Juneteenth observed Fri Jun 18 2027 as short (→ Thu Jun 17). Add Presidents' Day Feb 15 2027 and MLK Day Jan 18 2027 to the holiday set. Run it live on the first day: both picked expiries must exist in the Schwab chain (step 4).

## Step 6 — Calendar pricer and break-evens
- **Build:** `app/core/pricing.py`: Black-Scholes put price in forward form (numpy + `scipy.stats.norm`; `config.RATE`, default 4.0%); `forward_from_parity(chain, expiry)` = K + e^(rT)·(call − put) at the strike nearest the money (the call comes from step 4, item 5), so no dividend input is needed; `calendar_value_now(short, long)` at mid; `pl_curve(trade, spx_levels, at_date=short_expiry)` (any date up to the short expiry, IVs held fixed) where the short leg is worth intrinsic and the long leg is priced with Black-Scholes at its IV and remaining days; `break_evens(trade)` using `scipy.optimize.brentq` on each side of the strike → `BreakEvens`. Include the $0.10 entry cost in P/L. No web imports, plain floats out.
- **Files:** app/core/pricing.py, tests/test_pricing.py
- **Check:** unit tests (put-call parity on BS, P/L peaks near the strike, lower BE < strike < upper BE). Then the **thinkorswim check**: pick one live calendar, enter it in tos Analyze with the same strike/expiries, read tos's break-evens at the short expiry, and record both sets in `tests/fixtures/tos_check.md` with date, SPX, and IVs. Each break-even within ~5% of tos's distance from the strike. If not, look at the IV used for the long leg and the day count first.

## Step 7 — services.py skeleton and a CLI
- **Build:** `app/core/services.py` with all nine signatures from CLAUDE.md (rule 2). Implement `get_finder(dte_range, widths, strike_sets, size_mode="margin", size_value=config.MARGIN)` now (pick expiry pairs → pull chain → build one `CalendarRow` per pair × strike, sized by margin via `calendar_math` or by a fixed contract count → set `is_best_skew` and `is_near_40_delta` per pair → return `FinderResult` with one `PairSummary` per pair (its ~40Δ row, best skew and that strike, strike count) plus each pair's rows). The others raise `NotImplementedError` with a one-line docstring of their future input/output models. Add `cli.py` with `candidates` that calls `get_finder()` and prints the table plus break-evens for the near-40Δ row.
- **Files:** app/core/services.py, cli.py, tests/test_services.py
- **Check:** `uv run --env-file .env python -m cli candidates` prints today's rows; `test_services.py` runs `get_finder()` on the fixture (Schwab call mocked) and checks exactly one `is_best_skew` and one `is_near_40_delta`. `grep -rn "streamlit\|fastapi\|starlette\|jinja2" app/core` returns nothing.

## Step 8 — Wrap up
- **Build:** update HANDOVER.md (what works, tos check result, open decisions such as r/q values). Push to a new GitHub repo if ready.
- **Check:** `uv run pytest` all green; `git status` clean; no `data/` or token in `git log --stat`.
