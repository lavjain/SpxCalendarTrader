"""SQLite store: saved settings (per account) and the Finder log. Plain sqlite3, no web imports.

Week 2 tables: meta, settings, finder_log. trades, marks and spx_daily arrive in later weeks.
Each call opens its own short-lived connection, so it is safe from any thread.
"""
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core import config
from app.core.models import FinderResult, Spot

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings (
    account TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY (account, key));
CREATE TABLE IF NOT EXISTS finder_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at TEXT NOT NULL, trade_date TEXT NOT NULL, is_close_snapshot INTEGER NOT NULL DEFAULT 0,
    snapshot_id TEXT, spx REAL, vix REAL, vix9d REAL, filters TEXT NOT NULL,
    short_expiry TEXT NOT NULL, long_expiry TEXT NOT NULL, short_dte INTEGER, long_dte INTEGER,
    width INTEGER, strike REAL NOT NULL, short_delta REAL,
    short_mark REAL, short_bid REAL, short_ask REAL, long_mark REAL, long_bid REAL, long_ask REAL,
    short_iv REAL, long_iv REAL, skew REAL, price REAL, contracts INTEGER, margin REAL,
    be_lower REAL, be_upper REAL, is_near_40_delta INTEGER, is_best_skew INTEGER);
CREATE INDEX IF NOT EXISTS finder_log_date ON finder_log (trade_date, short_expiry, long_expiry);
"""


class Store:
    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def init(self) -> None:
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        with closing(self._connect()) as con, con:
            con.executescript(SCHEMA)
            con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
                        (str(SCHEMA_VERSION),))

    # ---- settings
    def get_setting(self, key: str, default=None, account: str = "Paper"):
        with closing(self._connect()) as con:
            row = con.execute("SELECT value FROM settings WHERE account = ? AND key = ?",
                              (account, key)).fetchone()
        return json.loads(row["value"]) if row else default

    def put_setting(self, key: str, value, account: str = "Paper") -> None:
        now = datetime.now(ZoneInfo(config.MARKET_TZ)).isoformat(timespec="seconds")
        with closing(self._connect()) as con, con:
            con.execute(
                "INSERT INTO settings (account, key, value, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (account, key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at", (account, key, json.dumps(value), now))

    # ---- finder_log
    def log_finder(self, result: FinderResult, spot: Spot | None = None, snapshot_id: str | None = None,
                   is_close_snapshot: bool = False) -> int:
        """One row per strike of every pair. Called on a Finder Refresh (and the close snapshot later)."""
        logged_at = result.time
        trade_date = logged_at[:10]
        filters = json.dumps(result.filters)
        rows = []
        for p in result.pairs:
            for r in p.rows:
                be = r.break_evens
                rows.append((
                    logged_at, trade_date, int(is_close_snapshot), snapshot_id, result.spx,
                    spot.vix if spot else None, spot.vix9d if spot else None, filters,
                    p.short_expiry, p.long_expiry, p.short_dte, p.long_dte, p.width, r.strike,
                    r.short.delta, r.short.mark, r.short.bid, r.short.ask,
                    r.long.mark, r.long.bid, r.long.ask, r.short_iv, r.long_iv, r.skew, r.price,
                    r.contracts, r.margin, be.lower if be else None, be.upper if be else None,
                    int(r.is_near_40_delta), int(r.is_best_skew)))
        if not rows:
            return 0
        with closing(self._connect()) as con, con:
            con.executemany("INSERT INTO finder_log (logged_at, trade_date, is_close_snapshot, snapshot_id, "
                            "spx, vix, vix9d, filters, short_expiry, long_expiry, short_dte, long_dte, width, "
                            "strike, short_delta, short_mark, short_bid, short_ask, long_mark, long_bid, long_ask, "
                            "short_iv, long_iv, skew, price, contracts, margin, be_lower, be_upper, "
                            "is_near_40_delta, is_best_skew) VALUES (" + ",".join("?" * 31) + ")", rows)
        return len(rows)

    def count_finder_rows(self) -> int:
        with closing(self._connect()) as con:
            return con.execute("SELECT COUNT(*) FROM finder_log").fetchone()[0]
