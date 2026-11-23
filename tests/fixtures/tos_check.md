# thinkorswim break-even check (Step 6) - 2026-11-23, ~12:45 ET

Result: PASS after switching pricing to IVs implied from the mid prices (within 5% of tos on both sides).

| field | thinkorswim | app (`cli diagnose`) |
|---|---|---|
| SPX | live | 7,236.38 |
| strike | 7120 | 7125 (the app's ~40-delta row at that moment; tos was set up at 7120) |
| expiries | short Thu 24 Dec 26 (W), long Thu 31 Dec 26 | same |
| calendar price | 12.80 | mid 12.75 |
| short IV / long IV | 24.58 / 23.92 | Schwab field 23.18 / 22.36; implied from mids 24.49 / 23.82 |
| break-evens at the short expiry | 6,871.92 / 7,415.05 | 6,880 / 7,413 (mid-implied IVs) |
| distance error vs tos | - | -3.1% / -0.7% |

Before the change (Schwab's `volatility` field as the IV): 6,901 / 7,387, i.e. -11.5% / -9.5% from tos.
Why: Schwab's IV does not reproduce its own marks (model 134.27 vs mid 144.75 on the short put).
tos model: Bjerksund-Stensland, 4.00% interest. App: Black-Scholes on the put-call-parity forward (carry +3.61%/yr that day).
Caveat: the strikes differ by 5 points (7120 in tos, 7125 in the app); the gap is smaller than the error margin.
