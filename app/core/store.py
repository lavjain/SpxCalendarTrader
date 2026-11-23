"""SQLite store: saved settings (per account) and the Finder log. Plain sqlite3, no web imports.

Tables: meta, settings, finder_log, trades (week 3). marks and spx_daily arrive in later weeks.
Each call opens its own short-lived connection, so it is safe from any thread.
"""
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core import config
from app.core.models import FinderResult, Spot, Trade

SCHEMA_VERSION = 2


class DuplicateTradeError(ValueError):
    """The same calendar (account, strike, expiries) is already open."""

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
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL DEFAULT 'Paper', status TEXT NOT NULL DEFAULT 'open',
    opened_at TEXT NOT NULL, short_expiry TEXT NOT NULL, long_expiry TEXT NOT NULL, strike REAL NOT NULL,
    width INTEGER NOT NULL, short_dte INTEGER NOT NULL, contracts INTEGER NOT NULL,
    size_mode TEXT NOT NULL, size_value REAL NOT NULL,
    open_bid REAL, open_ask REAL, open_mid REAL, open_range_low REAL, open_range_high REAL,
    open_suggested REAL, open_fill REAL NOT NULL, open_price_source TEXT NOT NULL,
    entry_spx REAL, entry_vix REAL, entry_vix9d REAL, entry_short_iv REAL, entry_long_iv REAL,
    entry_skew REAL, entry_break_lower REAL, entry_break_upper REAL, entry_vol_pnl REAL,
    entry_snapshot_source TEXT, notes TEXT NOT NULL DEFAULT '', closed_at TEXT,
    CHECK (status IN ('open', 'closed')), CHECK (contracts >= 1), CHECK (open_fill > 0));
CREATE UNIQUE INDEX IF NOT EXISTS trades_one_open
    ON trades (account, strike, short_expiry, long_expiry) WHERE status = 'open';
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
            con.executescript(SCHEMA)            # every statement is IF NOT EXISTS, so a v1 file upgrades in place
            con.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
                        "ON CONFLICT (key) DO UPDATE SET value = excluded.value "
                        "WHERE CAST(meta.value AS INTEGER) < CAST(excluded.value AS INTEGER)",
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

    # ---- trades
    def insert_trade(self, trade: Trade) -> int:
        """Save one trade in a single transaction and return its id. Raises DuplicateTradeError if the same
        calendar is already open in this account."""
        data = trade.model_dump(exclude={"id"})
        cols = ", ".join(data)
        try:
            with closing(self._connect()) as con, con:
                cur = con.execute(f"INSERT INTO trades ({cols}) VALUES ({','.join('?' * len(data))})",
                                  list(data.values()))
                return cur.lastrowid
        except sqlite3.IntegrityError as e:
            if "trades.account" in str(e) or "UNIQUE" in str(e).upper():
                raise DuplicateTradeError(
                    f"SPX {trade.strike:.0f} put calendar {trade.short_expiry} / {trade.long_expiry} "
                    f"is already open") from e
            raise

    @staticmethod
    def _trade(row: sqlite3.Row) -> Trade:
        return Trade(**dict(row))

    def get_trade(self, trade_id: int) -> Trade | None:
        with closing(self._connect()) as con:
            row = con.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return self._trade(row) if row else None

    def list_trades(self, status: str | None = None, account: str = "Paper") -> list[Trade]:
        sql, args = "SELECT * FROM trades WHERE account = ?", [account]
        if status:
            sql, args = sql + " AND status = ?", args + [status]
        with closing(self._connect()) as con:
            rows = con.execute(sql + " ORDER BY opened_at DESC, id DESC", args).fetchall()
        return [self._trade(r) for r in rows]

    def find_open(self, strike: float, short_expiry: str, long_expiry: str, account: str = "Paper") -> Trade | None:
        with closing(self._connect()) as con:
            row = con.execute("SELECT * FROM trades WHERE account = ? AND strike = ? AND short_expiry = ? "
                              "AND long_expiry = ? AND status = 'open'",
                              (account, strike, short_expiry, long_expiry)).fetchone()
        return self._trade(row) if row else None
