"""Every tunable trading number. No web imports; environment/secret settings live in app/settings.py."""

# --- sizing / fills
DEFAULT_CONTRACTS = 10               # default when switching Size By to contracts
MARGIN = 10_000                      # default when sizing by margin
MODEL_GREEKS = True                  # delta and gamma from Black-Scholes at the mid-implied IVs (False: Schwab's, 3 decimals)
SIZE_ROUNDING = "nearest"            # margin -> contracts: "nearest" (half up, min 1), "ceil" or "floor"
SIZE_MODES = ("margin", "contracts")
FILL_OFFSET = 0.10                   # open at mid + 0.10, close at mid - 0.10

# --- what the Finder looks for
DELTA_TARGET = 0.45                  # the strike the Finder stars and the Open Trade dialog starts from
DELTA_BAND = (0.40, 0.50)            # short-put deltas the Finder lists
DELTA_LABEL = "45Δ"                  # shown in headings (keep in step with DELTA_TARGET)
DELTA_BAND_LABEL = "40–50Δ"
SHORT_DTE_TARGET = 30
SHORT_DTE_DEFAULT = (25, 35)
SHORT_DTE_LIMITS = (7, 56)
WIDTHS = (3, 4, 5, 6, 7)             # days between short and long expiry
WIDTHS_DEFAULT = (7,)
STRIKE_SETS = ("10", "25")           # multiples of 10 and/or 25; default both
MAX_DTE = 63                         # 56 + 7
CALL_STRIKE_COUNT = 6                # calls requested around the money, per expiry (for the forward)

# --- stability check before a fill
REQUIRE_STABLE = False               # deferred: when True, Confirm waits for a stable price (the check below still runs)
STABLE_RANGE = 0.10
STABLE_QUOTES = 5
QUOTE_INTERVAL_S = 2
MAX_SPREAD_PCT = 0.10
WAIT_TIMEOUT_S = 60

# --- flags
FLAG_LOSS = -0.10
FLAG_TARGET = 0.10
MAX_DELTA_PER_CONTRACT = 2.0
TD_MIN_DELTA = 2.0                   # below this position delta, T/D means nothing (shown as a dash)

# --- market time and polling
CLOSE_SNAPSHOT_ET = "16:15"
MARKET_TZ = "America/New_York"
HOLDINGS_POLL_S = 30
MARKS_EVERY_S = 300

# --- Schwab request budget
CACHE_TTL_S = 20
SCHWAB_MAX_CONCURRENT = 4
SCHWAB_REQUESTS_PER_MIN = 100

# --- pricing
RATE = 0.04

# --- storage
DB_PATH = "data/paper_trades.db"
SNAPSHOT_PATH = "data/snapshots.json"

# --- NYSE full-day closures (2026-2027). Verify against the NYSE holiday calendar each year.
MARKET_HOLIDAYS = frozenset({
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
    "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
    "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
})
