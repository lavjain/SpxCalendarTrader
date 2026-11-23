import sqlite3

import pytest

from app.core.models import Trade
from app.core.store import DuplicateTradeError, Store


def make(**kw):
    base = dict(opened_at="2026-11-23T15:58:52-05:00", short_expiry="2026-12-24", long_expiry="2026-12-31",
                strike=7140.0, width=7, short_dte=31, contracts=8, size_mode="margin", size_value=10000,
                open_bid=12.5, open_ask=13.1, open_mid=12.8, open_range_low=12.78, open_range_high=12.85,
                open_suggested=12.9, open_fill=12.9, open_price_source="auto", entry_spx=7237.17,
                entry_vix=26.58, entry_short_iv=23.6, entry_long_iv=23.01, entry_skew=0.59,
                entry_break_lower=6918.0, entry_break_upper=7412.0, entry_snapshot_source="refresh")
    base.update(kw)
    return Trade(**base)


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.init()
    return s


def test_insert_and_read_back_every_field(store):
    t = make()
    tid = store.insert_trade(t)
    back = store.get_trade(tid)
    assert back.id == tid
    assert back.model_dump(exclude={"id"}) == t.model_dump(exclude={"id"})
    assert back.account == "Paper" and back.status == "open" and back.entry_vol_pnl is None


def test_table_columns_match_the_trade_model(store):
    with sqlite3.connect(store.path) as con:
        cols = [r[1] for r in con.execute("PRAGMA table_info(trades)")]
    assert cols == ["id"] + [f for f in Trade.model_fields if f != "id"]


def test_list_filters_by_status_and_account_newest_first(store):
    a = store.insert_trade(make(strike=7140.0, opened_at="2026-11-23T10:00:00-05:00"))
    b = store.insert_trade(make(strike=7150.0, opened_at="2026-11-23T11:00:00-05:00"))
    store.insert_trade(make(strike=7100.0, account="Other"))
    assert [t.id for t in store.list_trades()] == [b, a]
    assert [t.id for t in store.list_trades(status="open")] == [b, a]
    assert store.list_trades(status="closed") == []
    assert len(store.list_trades(account="Other")) == 1


def test_find_open_sees_only_open_trades_of_that_account(store):
    store.insert_trade(make())
    assert store.find_open(7140.0, "2026-12-24", "2026-12-31").strike == 7140.0
    assert store.find_open(7140.0, "2026-12-24", "2026-12-31", account="Other") is None
    assert store.find_open(7150.0, "2026-12-24", "2026-12-31") is None
    with sqlite3.connect(store.path) as con:
        con.execute("UPDATE trades SET status = 'closed'")
    assert store.find_open(7140.0, "2026-12-24", "2026-12-31") is None


def test_the_same_open_calendar_cannot_be_saved_twice(store):
    store.insert_trade(make())
    with pytest.raises(DuplicateTradeError, match="already open"):
        store.insert_trade(make())
    assert len(store.list_trades()) == 1
    store.insert_trade(make(account="Other"))                 # another account is fine


def test_a_closed_trade_does_not_block_reopening(store):
    tid = store.insert_trade(make())
    with sqlite3.connect(store.path) as con:
        con.execute("UPDATE trades SET status = 'closed' WHERE id = ?", (tid,))
    store.insert_trade(make())


def test_a_failed_insert_leaves_no_row(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_trade(make(contracts=0))                 # CHECK (contracts >= 1)
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_trade(make(open_fill=-1.0))
    assert store.list_trades() == []


def test_a_v1_database_upgrades_in_place(tmp_path):
    path = str(tmp_path / "old.db")
    with sqlite3.connect(path) as con:                         # what week 2 created
        con.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE settings (account TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
                                   updated_at TEXT NOT NULL, PRIMARY KEY (account, key));
            INSERT INTO meta VALUES ('schema_version', '1');
            INSERT INTO settings VALUES ('Paper', 'finder_filters', '{"widths": [7]}', '2026-11-23T10:00:00-05:00');""")
    s = Store(path)
    s.init()
    assert s.get_setting("finder_filters") == {"widths": [7]}            # old data intact
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == "3"
    s.init()                                                            # and repeatable
    assert s.insert_trade(make()) == 1


def test_a_v2_file_gets_the_renamed_finder_log_column_and_keeps_its_rows(tmp_path):
    import sqlite3
    path = str(tmp_path / "old.db")
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO meta VALUES ('schema_version', '2');
            CREATE TABLE finder_log (id INTEGER PRIMARY KEY, trade_date TEXT, short_expiry TEXT, long_expiry TEXT,
                                     is_near_40_delta INTEGER);
            INSERT INTO finder_log VALUES (1, '2026-11-20', '2026-12-24', '2026-12-31', 1);
        """)
    Store(path).init()
    with sqlite3.connect(path) as con:
        cols = [r[1] for r in con.execute("PRAGMA table_info(finder_log)")]
        assert "is_near_target_delta" in cols and "is_near_40_delta" not in cols
        assert con.execute("SELECT is_near_target_delta FROM finder_log").fetchone()[0] == 1
        assert con.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == "3"
