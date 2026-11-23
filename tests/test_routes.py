"""Route tests. Need the web dependencies (fastapi, httpx); skipped where they are missing."""
from datetime import date

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("pydantic_settings")
from fastapi.testclient import TestClient  # noqa: E402

from app.core import schwab_api, services  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.test_services import CHAIN  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(services, "market_today", lambda: date(2026, 11, 24))
    monkeypatch.setattr(schwab_api, "get_chain", lambda s, p, **kw: CHAIN)
    monkeypatch.setattr(schwab_api, "get_call_chain", lambda s, p, **kw: CHAIN)
    monkeypatch.setattr(schwab_api, "get_quotes", lambda syms, **kw: {})
    with TestClient(create_app(str(tmp_path / "t.db"), str(tmp_path / "snaps.json"))) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").status_code == 200


def test_root_redirects_and_finder_renders_empty(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/finder"
    assert "Press" in client.get("/finder").text


def test_refresh_then_partials(client):
    r = client.post("/api/finder/refresh", json={"dte_min": 7, "dte_max": 56, "widths": [7]})
    assert r.status_code == 200
    sid = r.json()["snapshot_id"]
    html = client.get(f"/partials/results?snapshot_id={sid}").text
    assert "calendars-table" in html
    assert "Break-Evens" in client.get(f"/finder").text
    pair = r.json()["result"]["pairs"][2]
    s = client.get(f"/partials/strike-rows?snapshot_id={sid}&short={pair['short_expiry']}&long={pair['long_expiry']}")
    assert s.status_code == 200 and "strike-row" in s.text


def test_expired_snapshot_is_404(client):
    r = client.get("/partials/results?snapshot_id=nope")
    assert r.status_code == 404 and "expired" in r.json()["detail"]


def test_settings_round_trip(client):
    assert client.put("/api/settings/finder_filters", json={"value": {"widths": [7]}}).status_code == 200
    assert client.get("/api/settings/finder_filters").json()["value"] == {"widths": [7]}
