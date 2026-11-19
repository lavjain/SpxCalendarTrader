# Week 1 — Schwab data and calendar pricing (Nov 24–30)

Give Claude Code one step at a time. Finish each step's check before moving on, and commit after each step.
**Week done when:** `uv run --env-file .env python -m cli candidates` prints today's 35–45Δ put calendars, and one calendar's break-evens are within ~5% of thinkorswim Analyze.

---

## Step 0 — Repo baseline
- **Build:** `pyproject.toml`, `.python-version`, `.gitignore`, `tests/` and `HANDOVER.md` already exist. Run `uv sync` to create `.venv/` (Python 3.12, pinned in `.python-version`) and `uv.lock`, and commit `uv.lock`. Copy `.env.example` to `.env` and add your Schwab keys; commands that call Schwab run as `uv run --env-file .env …`. (The optional `mockups` group is only for `docs/mockups/`.)
- **Files:** uv.lock, .env (not committed)
- **Check:** `uv run python -c "import streamlit, pandas, numpy, scipy, pydantic"` succeeds; `git status` shows no `data/` or `.env`.

## Step 1 — Starting files (done Nov 18)
`schwab_api.py`, `calendar_math.py` and `README.md` are in place; `calendar_math.py` logs to `data/`.
- **Check:** `uv run python calendar_math.py selftest` prints "16/16 rows reproduce exactly." and `uv run python schwab_api.py chain --demo` parses the demo chain.

## Step 2 — Self-test as pytest
- **Build:** `tests/test_calendar_math.py` runs the Lane 2021-09-17 data (`LANE_2021_09_17` vs `LANE_EXPECTED`) through `build()` and asserts all 16 rows with the same tolerances as `selftest()`. Don't edit the expected numbers.
- **Files:** tests/test_calendar_math.py (calendar_math.py only if an import needs fixing)
- **Check:** `uv run pytest tests/test_calendar_math.py` → 16 rows pass. `uv run python calendar_math.py selftest` still prints "16/16 rows reproduce exactly."

## Step 3 — settings.py and models.py skeleton
- **Build:** `settings.py` with constants: `MARGIN = 10_000` (default when sizing by margin), `SIZE_MODES = ("margin", "contracts")`, `FILL_OFFSET = 0.10`, `DELTA_TARGET = 0.40`, `DELTA_BAND = (0.35, 0.45)`, `SHORT_DTE_TARGET = 30`, `SHORT_DTE_DEFAULT = (25, 35)`, `SHORT_DTE_LIMITS = (7, 56)`, `WIDTHS = (3, 4, 5, 6, 7)`, `WIDTHS_DEFAULT = (7,)`, `STRIKE_SETS = ("10", "25")` (multiples of 10 and/or 25; default both), `MAX_DTE = 63` (56 + 7), `STABLE_RANGE = 0.10`, `STABLE_QUOTES = 5`, `QUOTE_INTERVAL_S = 2`, `MAX_SPREAD_PCT = 0.10`, `WAIT_TIMEOUT_S = 60`, `FLAG_LOSS = -0.10`, `FLAG_TARGET = 0.10`, `MAX_DELTA_PER_CONTRACT = 2.0`, `CLOSE_SNAPSHOT_ET = "16:15"`, `DB_PATH = "data/paper_trades.db"`. `models.py` with Pydantic models for week 1: `OptionQuote` (expiry, strike, bid, ask, mark, delta, gamma, theta, vega, iv), `ExpiryPair` (short, long as ISO dates, dte each, width), `CalendarRow` (strike, width, short/long legs, contracts, price, margin, greeks, short and long IV, short and long vega, skew, td, theta_margin, `is_best_skew`, `is_near_40_delta`), `BreakEvens` (lower, upper, at_date), `PairSummary` (short and long expiry, DTEs, width, the ~40Δ `CalendarRow`, best skew and its strike, strike count), `FinderResult` (time, spx, filters used, pairs: list of `PairSummary` each with its rows).
- **Files:** settings.py, models.py, tests/test_models.py
- **Check:** a test round-trips each model with `model_dump_json()` / `model_validate_json()`; the only number types are `float`/`int` (no numpy).

## Step 4 — schwab_api fixes (the four from the plan)
- **Build:**
  1. **One strike for both legs.** Add `calendar_legs(rows, short_exp, long_exp, strike)` that returns the short and long put at the same strike. Drop the per-expiry `nearest()`/ATM path from the app's flow (leave it for the CLI if handy).
  2. **35–45Δ puts for the chosen expiries only.** `get_chain` requests `fromDate`/`toDate` covering the short Fridays in the DTE range through the last long expiry; `parse` keeps puts with |Δ| in `settings.DELTA_BAND` on each short expiry, on the strikes switched on (multiples of 10 and/or 25), plus the put at each of those strikes on every long expiry 3–7 days later (whatever its delta).
  3. **SPXW on the third Friday.** On monthly expiry, the chain returns both SPX (AM-settled) and SPXW (PM-settled). Keep only `optionRoot == "SPXW"` (check the field name against a live pull or the README notes).
  4. **Limit to 63 DTE** (8-week short + 7-day width). Default `dte_max = settings.MAX_DTE`; reject anything past it. A 60-DTE `range=OTM` pull was ~7 MB in testing, so this should stay under Schwab's size limit; check once.
  Parse into `OptionQuote` models, keep bid and ask (needed for the fill rules). Keep the token path at `~/.schwab/` and add the `$VIX`/`$VIX9D`/`$SPX` quote helper for later snapshots (`get_quotes(symbols)`).
- **Files:** schwab_api.py, tests/test_schwab_api.py, tests/fixtures/chain_sample.json
- **Check:** tests on a saved fixture (save one real pull to `tests/fixtures/` after removing anything account-specific, or extend the DEMO fixture with a third-Friday SPX+SPXW duplicate): same strike on both legs, only 35–45Δ short strikes on the chosen spacing, no SPX-AM rows, nothing past 63 DTE. Then one live pull with the default filters (`uv run --env-file .env python schwab_api.py chain`) returns rows for exactly two expiries (one short Friday, its 7-day long).

## Step 5 — Expiry picker
- **Build:** `pick_expiries(today, dte_range=(25, 35), widths=(7,)) -> list[ExpiryPair]` in `calendar_math.py` (or `expiries.py`): one short per Friday whose DTE is inside `dte_range` (allowed 7–56); for each width, long = that Friday + width days. A short Friday that is a holiday moves to the Thursday before; a long date that isn't a trading day moves back to the previous trading day, and the pair is dropped if that's on or before the short. DTE is counted to the actual expiry. Holidays come from a small hard-coded set in `settings.py` for 2026–2027 (incl. Dec 25 2026, Jan 1 2027, Good Friday Mar 26 2027, Juneteenth observed Fri Jun 18 2027; check the full list against the NYSE holiday calendar).
- **Files:** calendar_math.py (or expiries.py), settings.py, tests/test_expiries.py
- **Check:** tests include: from **Tue Nov 24 2026** with defaults → short **Thu Dec 24** (Dec 25 holiday), long **Thu Dec 31** (Jan 1 holiday); from **Tue Jan 12 2027**, widths 3–7 on the Feb 12 short → longs Feb 16, 17, 18, 19 and **no 3-day pair** (Mon Feb 15 is Presidents' Day); a DTE range of 7–56 returns 7 or 8 Fridays; a Good Friday case. Add Presidents' Day Feb 15 2027 and MLK Day Jan 18 2027 to the holiday set. Run it live on the first day: both picked expiries must exist in the Schwab chain (step 4).

## Step 6 — Calendar pricer and break-evens
- **Build:** `pricing.py`: Black-Scholes put price in forward form (numpy + `scipy.stats.norm`; r in settings, default 4.0%); `forward_from_parity(chain, expiry)` = K + e^(rT)·(call − put) at the strike nearest the money, so no dividend input is needed; `calendar_value_now(short, long)` at mid; `pl_curve(trade, spx_levels, at_date=short_expiry)` (any date up to the short expiry, IVs held fixed) where the short leg is worth intrinsic and the long leg is priced with Black-Scholes at its IV and remaining days; `break_evens(trade)` using `scipy.optimize.brentq` on each side of the strike → `BreakEvens`. Include the $0.10 entry cost in P/L. No streamlit, plain floats out.
- **Files:** pricing.py, tests/test_pricing.py
- **Check:** unit tests (put-call parity on BS, P/L peaks near the strike, lower BE < strike < upper BE). Then the **thinkorswim check**: pick one live calendar, enter it in tos Analyze with the same strike/expiries, read tos's break-evens at the short expiry, and record both sets in `tests/fixtures/tos_check.md` with date, SPX, and IVs. Each break-even within ~5% of tos's distance from the strike. If not, look at the IV used for the long leg and the day count first.

## Step 7 — services.py skeleton and a CLI
- **Build:** `services.py` with all six signatures from CLAUDE.md. Implement `get_finder(dte_range, widths, strike_sets, size_mode="margin", size_value=settings.MARGIN)` now (pick expiry pairs → pull chain → build one `CalendarRow` per pair × strike, sized by margin via `calendar_math` or by a fixed contract count → set `is_best_skew` and `is_near_40_delta` per pair → return `FinderResult` with one `PairSummary` per pair (its ~40Δ row, best skew and that strike, strike count) plus each pair's rows). Other five raise `NotImplementedError` with a one-line docstring of their future input/output models. Add `cli.py` with `candidates` that calls `get_finder()` and prints the table plus break-evens for the near-40Δ row.
- **Files:** services.py, cli.py, tests/test_services.py
- **Check:** `uv run --env-file .env python -m cli candidates` prints today's rows; `test_services.py` runs `get_finder()` on the fixture (Schwab call mocked) and checks exactly one `is_best_skew` and one `is_near_40_delta`. `grep -r "import streamlit" --include=*.py .` returns nothing.

## Step 8 — Wrap up
- **Build:** update HANDOVER.md (what works, tos check result, open decisions such as r/q values). Push to a new GitHub repo if ready.
- **Check:** `uv run pytest` all green; `git status` clean; no `data/` or token in `git log --stat`.
