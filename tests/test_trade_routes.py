"""Route tests for /api/quote-spread and /api/trades. Skipped where the web dependencies are missing."""
from datetime import date

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("pydantic_settings")
from fastapi.testclient import TestClient  # noqa: E402

from app.core import schwab_api, services  # noqa: E402
from app.core.models import Spot  # noqa: E402
from app.core.stability import StabilityTracker  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.test_services import CHAIN  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(services, "market_today", lambda: date(2026, 11, 24))
    monkeypatch.setattr(services, "quote_tracker", StabilityTracker())
    monkeypatch.setattr(services, "get_spot", lambda: Spot(time="2026-11-24T10:00:00-05:00", spx=6800.0, vix=20.0, vix9d=19.0))
    monkeypatch.setattr(schwab_api, "get_chain", lambda s, p, **kw: CHAIN)
    monkeypatch.setattr(schwab_api, "get_call_chain", lambda s, p, **kw: CHAIN)
    monkeypatch.setattr(schwab_api, "get_quotes", lambda syms, use_cache=True: {
        s: {"bid": 137.6 if i == 0 else 150.0, "ask": 139.3 if i == 0 else 153.0} for i, s in enumerate(syms)})
    with TestClient(create_app(str(tmp_path / "t.db"), str(tmp_path / "snaps.json"))) as c:
        yield c


def _calendar(client):
    snap = client.post("/api/finder/refresh", json={"dte_min": 7, "dte_max": 56, "widths": [7]}).json()
    pair = next(p for p in snap["result"]["pairs"] if p["rows"])
    row = pair["rows"][0]
    return snap["snapshot_id"], pair, row


def test_quote_spread_returns_the_price_and_the_decision_fields(client):
    _, _, row = _calendar(client)
    r = client.post("/api/quote-spread", json={"short_symbol": row["short"]["symbol"], "long_symbol": row["long"]["symbol"]})
    assert r.status_code == 200
    body = r.json()
    assert body["suggested_price"] is not None and body["contracts"] >= 1
    assert body["stability_required"] is False and body["quotes_seen"] == 1


def test_open_trade_saves_a_row_and_lists_it(client):
    sid, pair, row = _calendar(client)
    req = {"snapshot_id": sid, "short_expiry": pair["short_expiry"], "long_expiry": pair["long_expiry"],
           "strike": row["strike"], "contracts": 2, "fill_price": 12.9}
    r = client.post("/api/trades", json=req)
    assert r.status_code == 201 and r.json()["trade"]["id"] == 1
    assert [t["strike"] for t in client.get("/api/trades").json()] == [row["strike"]]
    assert client.post("/api/trades", json=req).status_code == 409           # already open


def test_open_trade_errors(client):
    sid, pair, row = _calendar(client)
    base = {"snapshot_id": sid, "short_expiry": pair["short_expiry"], "long_expiry": pair["long_expiry"],
            "strike": row["strike"], "contracts": 2, "fill_price": 12.9}
    assert client.post("/api/trades", json={**base, "snapshot_id": "nope"}).status_code == 404
    assert client.post("/api/trades", json={**base, "strike": 1.0}).status_code == 404
    assert client.post("/api/trades", json={**base, "fill_price": 0}).status_code == 422
    assert client.get("/api/trades").json() == []


def test_tos_order_endpoint_writes_the_line(client):
    r = client.post("/api/tos-order", json={"short_expiry": "2027-02-12", "long_expiry": "2027-02-19",
                                            "strike": 6800, "contracts": 13, "price": 7.7})
    assert r.status_code == 200
    assert r.json()["line"] == "BUY +13 CALENDAR SPX 100 (Weeklys) 19 FEB 27/12 FEB 27 6800 PUT @7.70 LMT"
    assert client.post("/api/tos-order", json={"short_expiry": "2027-02-12", "long_expiry": "2027-02-19",
                                               "strike": 6800, "contracts": 0, "price": 7.7}).status_code == 422


def test_parse_endpoint_reads_a_line_and_explains_a_refusal(client):
    line = "BUY +13 CALENDAR SPX 100 (Weeklys) 19 FEB 27/12 FEB 27 6800 PUT @7.70 LMT"
    ok = client.post("/api/tos-order/parse", json={"text": line, "short_expiry": "2027-02-12",
                                                   "long_expiry": "2027-02-19", "strike": 6800})
    assert ok.status_code == 200 and ok.json()["contracts"] == 13 and ok.json()["price"] == 7.7
    sell = client.post("/api/tos-order/parse", json={"text": line.replace("BUY +13", "SELL -13")})
    assert sell.status_code == 422 and "closing order" in sell.json()["detail"]
    other = client.post("/api/tos-order/parse", json={"text": line, "strike": 6790})
    assert other.status_code == 422 and "strike 6800" in other.json()["detail"]


def test_compare_endpoint_returns_rows_without_saving_a_snapshot(client):
    r = client.post("/api/compare")
    assert r.status_code == 200 and r.json()["width"] == 7
    assert client.get("/api/finder").status_code == 404                  # the comparison is not a Finder snapshot
    assert "compare-table" in client.post("/partials/compare").text
