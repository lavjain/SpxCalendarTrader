"""Every tunable trading number. No web imports; environment/secret settings live in app/settings.py."""

# --- sizing / fills
MARGIN = 10_000                      # default when sizing by margin
SIZE_MODES = ("margin", "contracts")
FILL_OFFSET = 0.10                   # open at mid + 0.10, close at mid - 0.10

# --- what the Finder looks for
DELTA_TARGET = 0.40
DELTA_BAND = (0.35, 0.45)
SHORT_DTE_TARGET = 30
SHORT_DTE_DEFAULT = (25, 35)
SHORT_DTE_LIMITS = (7, 56)
WIDTHS = (3, 4, 5, 6, 7)             # days between short and long expiry
WIDTHS_DEFAULT = (7,)
STRIKE_SETS = ("10", "25")           # multiples of 10 and/or 25; default both
MAX_DTE = 63                         # 56 + 7

# --- stability check before a fill
STABLE_RANGE = 0.10
STABLE_QUOTES = 5
QUOTE_INTERVAL_S = 2
MAX_SPREAD_PCT = 0.10
WAIT_TIMEOUT_S = 60

# --- flags
FLAG_LOSS = -0.10
FLAG_TARGET = 0.10
MAX_DELTA_PER_CONTRACT = 2.0

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
