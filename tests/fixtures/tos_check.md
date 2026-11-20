# thinkorswim break-even check (Step 6) — PENDING, needs a live pull on a market day

Goal: each break-even within ~5% of thinkorswim's distance from the strike.

1. `uv run --env-file .env python -m cli candidates` and note the ~40Δ row of one pair
   (strike, expiries, short/long IV, SPX) and the app's break-evens.
2. In thinkorswim → Analyze, enter the same put calendar (same strike, same two expiries), read the
   break-evens at the short expiry.
3. Fill in below. If they differ by more than ~5%, look at the long-leg IV and the day count first.

| field | value |
|---|---|
| date / time (ET) | |
| SPX | |
| strike | |
| short expiry / long expiry | |
| short IV / long IV | |
| app lower BE (distance from strike) | |
| app upper BE (distance from strike) | |
| tos lower BE (distance from strike) | |
| tos upper BE (distance from strike) | |
| difference, lower / upper | |
