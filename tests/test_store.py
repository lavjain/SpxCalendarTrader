import json
import sqlite3
from datetime import date

import pytest

from app.core.models import Spot
from app.core.store import Store
from tests.test_services import CHAIN, flat  # noqa: F401  (fixture chain)
from app.core import schwab_api, services


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "data" / "t.db"))
    s.init()
    return s


@pytest.fixture
def result(monkeypatch):
    monkeypatch.setattr(services, "market_today", lambda: date(2026, 11, 24))
    monkeypatch.setattr(schwab_api, "get_chain", lambda sym, pairs, **kw: CHAIN)
    monkeypatch.setattr(schwab_api, "get_call_chain", lambda sym, pairs, **kw: CHAIN)
    return services.get_finder()


def test_init_creates_folder_tables_and_is_repeatable(tmp_path):
    s = Store(str(tmp_path / "deep" / "dir" / "x.db"))
    s.init(); s.init()
    names = {r[0] for r in sqlite3.connect(s.path).execute("select name from sqlite_master where type='table'")}
    assert {"meta", "settings", "finder_log"} <= names


def test_settings_round_trip_and_accounts_do_not_mix(store):
    assert store.get_setting("finder_filters") is None
    assert store.get_setting("finder_filters", default={"a": 1}) == {"a": 1}
    store.put_setting("finder_filters", {"dte_min": 25, "widths": [7]})
    store.put_setting("finder_filters", {"dte_min": 28, "widths": [7, 6]})            # overwrite
    store.put_setting("finder_filters", {"dte_min": 10}, account="IRA")
    assert store.get_setting("finder_filters") == {"dte_min": 28, "widths": [7, 6]}
    assert store.get_setting("finder_filters", account="IRA") == {"dte_min": 10}


def test_settings_survive_reopening(store):
    store.put_setting("theme_free_key", [1, 2, 3])
    assert Store(store.path).get_setting("theme_free_key") == [1, 2, 3]


def test_log_finder_writes_one_row_per_strike_with_flags(store, result):
    n = store.log_finder(result, Spot(time=result.time, spx=6800.0, vix=18.5, vix9d=19.1), snapshot_id="abc")
    rows = sqlite3.connect(store.path).execute(
        "select snapshot_id, vix, strike, is_near_target_delta, is_best_skew, be_lower, be_upper, is_close_snapshot, "
        "trade_date, filters from finder_log").fetchall()
    assert n == len(rows) == sum(p.strike_count for p in result.pairs) > 1
    assert {r[0] for r in rows} == {"abc"} and {r[1] for r in rows} == {18.5}
    assert sum(r[3] for r in rows) == 1 and sum(r[4] for r in rows) == 1
    assert all(r[5] < r[2] < r[6] for r in rows) and {r[7] for r in rows} == {0}
    assert rows[0][8] == result.time[:10] and json.loads(rows[0][9])["widths"] == [7]


def test_log_finder_without_spot_or_rows(store, result):
    assert store.log_finder(result) > 0
    result.pairs[0].rows = []
    before = store.count_finder_rows()
    assert store.log_finder(result) == 0 and store.count_finder_rows() == before


def test_no_web_imports_in_store():
    import pathlib
    src = pathlib.Path(__file__).parents[1].joinpath("app/core/store.py").read_text()
    assert not any(w in src for w in ("fastapi", "starlette", "jinja2"))
