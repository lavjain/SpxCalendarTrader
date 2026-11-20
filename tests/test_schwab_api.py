import json
from pathlib import Path

import pytest

from app.core import config, schwab_api
from app.core.models import ExpiryPair

CHAIN = json.loads((Path(__file__).parent / "fixtures" / "chain_sample.json").read_text())
# today is 2026-11-24 in the fixture
PAIR_A = ExpiryPair(short="2026-12-24", long="2026-12-31", short_dte=30, long_dte=37, width=7)
PAIR_THIRD = ExpiryPair(short="2026-12-18", long="2026-12-24", short_dte=24, long_dte=30, width=6)


def puts(pairs, **kw):
    return schwab_api.parse(CHAIN, pairs, **kw)


def test_same_strike_on_both_legs():
    rows = puts([PAIR_A])
    shorts = {q.strike for q in rows if q.expiry == PAIR_A.short}
    longs = {q.strike for q in rows if q.expiry == PAIR_A.long}
    assert shorts and shorts == longs
    for k in shorts:
        s, l = schwab_api.calendar_legs(rows, PAIR_A.short, PAIR_A.long, k)
        assert s.strike == l.strike == k and s.right == l.right == "P"


def test_calendar_legs_missing_leg_returns_none():
    rows = puts([PAIR_A])
    assert schwab_api.calendar_legs(rows, PAIR_A.short, PAIR_A.long, 1234.0) is None


def test_short_strikes_in_delta_band_and_on_spacing():
    lo, hi = config.DELTA_BAND
    for sets in (("10",), ("25",), ("10", "25")):
        rows = puts([PAIR_A], strike_sets=sets)
        shorts = [q for q in rows if q.expiry == PAIR_A.short]
        assert shorts
        for q in shorts:
            assert lo <= abs(q.delta) <= hi
            assert any(q.strike % int(s) == 0 for s in sets)
    only25 = {q.strike for q in puts([PAIR_A], strike_sets=("25",))}
    assert all(k % 25 == 0 for k in only25)


def test_long_leg_keeps_any_delta():
    wide = ExpiryPair(short="2026-12-18", long="2026-12-31", short_dte=24, long_dte=37, width=13)
    rows = puts([wide], delta_band=(0.35, 0.37))
    long_deltas = [abs(q.delta) for q in rows if q.expiry == wide.long]
    assert long_deltas and any(not 0.35 <= d <= 0.37 for d in long_deltas)


def test_no_spx_am_rows_on_third_friday():
    raw = [c for strikes in CHAIN["putExpDateMap"]["2026-12-18:24"].values() for c in strikes]
    assert {c["optionRoot"] for c in raw} == {"SPX", "SPXW"}    # the fixture has both
    rows = puts([PAIR_THIRD])
    third = [q for q in rows if q.expiry == "2026-12-18"]
    assert third
    spxw = {c["strikePrice"]: c["mark"] for strikes in CHAIN["putExpDateMap"]["2026-12-18:24"].values()
            for c in strikes if c["optionRoot"] == "SPXW"}
    assert len(third) == len({q.strike for q in third})          # one row per strike
    assert all(q.mark == spxw[q.strike] for q in third)         # the SPXW price, not the SPX twin


def test_root_fallback_to_symbol_when_field_missing():
    assert schwab_api._is_spxw({"symbol": "SPXW  261224P06700000"})
    assert not schwab_api._is_spxw({"symbol": "SPX   261218P06700000"})


def test_nothing_past_63_dte():
    far = ExpiryPair(short="2027-03-12", long="2027-03-19", short_dte=108, long_dte=115, width=7)
    assert puts([far]) == []
    with pytest.raises(ValueError):
        schwab_api.get_chain("$SPX", [far], today=__import__("datetime").date(2026, 11, 24))


def test_missing_values_become_none_and_rows_are_skipped():
    rows = puts([PAIR_A], strike_sets=("10",))
    assert all(None not in (q.mark, q.delta, q.iv) for q in rows)    # the "NaN" delta row is gone
    assert schwab_api._num("NaN") is None and schwab_api._num(-999) is None
    assert schwab_api._num(None) is None and schwab_api._num("1.5") == 1.5
    # a missing bid stays None, it is not turned into 0
    q = schwab_api._quote("2026-12-31", {"strikePrice": 6600.0, "bid": None, "ask": 5.0,
                                         "mark": 4.9, "delta": -0.2, "volatility": 15.0}, "P")
    assert q.bid is None and q.ask == 5.0


def test_call_nearest_the_money_on_each_expiry():
    calls = schwab_api.parse_calls(CHAIN, [PAIR_A, PAIR_THIRD])
    spot = CHAIN["underlyingPrice"]
    for exp in (PAIR_A.short, PAIR_A.long, PAIR_THIRD.short):
        near = min((q for q in calls if q.expiry == exp), key=lambda q: abs(q.strike - spot))
        assert near.right == "C" and abs(near.strike - spot) <= 5
    third = [q for q in calls if q.expiry == "2026-12-18"]
    assert len({q.strike for q in third}) == len(third)           # SPX twins dropped


def test_get_chain_requests_only_the_window(monkeypatch):
    seen = []
    monkeypatch.setattr(schwab_api, "_get_json", lambda url: seen.append(url) or {})
    schwab_api.get_chain("$SPX", [PAIR_A], today=__import__("datetime").date(2026, 11, 24))
    schwab_api.get_call_chain("$SPX", [PAIR_A])
    assert "fromDate=2026-12-24" in seen[0] and "toDate=2026-12-31" in seen[0]
    assert "contractType=PUT" in seen[0]
    assert "contractType=CALL" in seen[1] and f"strikeCount={config.CALL_STRIKE_COUNT}" in seen[1]


# ------------------------------------------------------------- item 6: safe for a web server
import io
import threading
import urllib.error
from datetime import datetime, timedelta, timezone


@pytest.fixture
def token_file(tmp_path, monkeypatch):
    path = tmp_path / "tok.json"
    monkeypatch.setattr(schwab_api, "TOKEN_PATH", str(path))
    monkeypatch.setenv("SCHWAB_APP_KEY", "k")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "s")
    schwab_api.clear_cache()
    return path


def write_tok(path, login_days_ago, access_minutes_ago):
    now = datetime.now(timezone.utc)
    path.write_text(json.dumps({
        "access_token": "AT", "refresh_token": "RT",
        "login_at": (now - timedelta(days=login_days_ago)).isoformat(),
        "access_at": (now - timedelta(minutes=access_minutes_ago)).isoformat()}))


class FakeResp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_no_sys_exit_outside_main():
    src = Path(schwab_api.__file__).read_text().splitlines()
    lines = [i for i, l in enumerate(src, 1) if "sys.exit" in l]
    main_start = next(i for i, l in enumerate(src, 1) if l.startswith("def main("))
    main_end = next(i for i, l in enumerate(src, 1) if l.startswith("def _main("))
    assert lines and all(main_start <= i < main_end for i in lines)


def test_missing_keys_raise_not_exit(monkeypatch):
    monkeypatch.delenv("SCHWAB_APP_KEY", raising=False)
    with pytest.raises(schwab_api.SchwabAuthError):
        schwab_api.cfg()
    with pytest.raises(schwab_api.SchwabAuthError):
        schwab_api.extract_code("https://127.0.0.1/?nothing=here")


def test_no_token_and_expired_login_raise(token_file):
    with pytest.raises(schwab_api.SchwabAuthError, match="no token"):
        schwab_api.access_token()
    write_tok(token_file, login_days_ago=7.2, access_minutes_ago=1)
    with pytest.raises(schwab_api.SchwabAuthError, match="7 days"):
        schwab_api.access_token()


def test_login_age_survives_a_refresh(token_file, monkeypatch):
    write_tok(token_file, login_days_ago=5, access_minutes_ago=60)     # access token is stale
    monkeypatch.setattr(schwab_api.urllib.request, "urlopen", lambda req, timeout=0: FakeResp(
        json.dumps({"access_token": "NEW", "refresh_token": "RT2"}).encode()))
    assert schwab_api.access_token() == "NEW"
    tok = json.loads(token_file.read_text())
    assert 4.9 < schwab_api.login_age_days(tok) < 5.1                 # still ~5 days, not reset to 0
    assert datetime.now(timezone.utc) - datetime.fromisoformat(tok["access_at"]) < timedelta(seconds=5)
    assert oct(token_file.stat().st_mode & 0o777) == "0o600"


def test_login_sets_a_fresh_login_time(token_file, monkeypatch):
    write_tok(token_file, login_days_ago=6, access_minutes_ago=1)
    monkeypatch.setattr(schwab_api.urllib.request, "urlopen", lambda req, timeout=0: FakeResp(
        json.dumps({"access_token": "A", "refresh_token": "R"}).encode()))
    tok = schwab_api.post_token("k", "s", {"grant_type": "authorization_code"}, login=True)
    assert schwab_api.login_age_days(tok) < 0.01


def test_old_token_format_still_readable(token_file):
    token_file.write_text(json.dumps({"access_token": "AT", "refresh_token": "RT",
        "obtained_at": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()}))
    assert schwab_api.access_token() == "AT"


def test_schwabpy_flow_uses_its_own_token_path():
    assert schwab_api.SCHWABPY_TOKEN_PATH != schwab_api.TOKEN_PATH


def test_concurrent_refresh_happens_once(token_file, monkeypatch):
    write_tok(token_file, login_days_ago=1, access_minutes_ago=60)
    calls = []

    def fake(req, timeout=0):
        calls.append(1)
        return FakeResp(json.dumps({"access_token": "NEW", "refresh_token": "RT"}).encode())
    monkeypatch.setattr(schwab_api.urllib.request, "urlopen", fake)
    out = []
    threads = [threading.Thread(target=lambda: out.append(schwab_api.access_token())) for _ in range(6)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert out == ["NEW"] * 6 and len(calls) == 1


def test_market_date_not_machine_date(monkeypatch):
    import app.core.expiries as ex
    seen = {}
    monkeypatch.setattr(schwab_api, "market_today", lambda: seen.setdefault("d", __import__("datetime").date(2026, 11, 24)))
    urls = []
    monkeypatch.setattr(schwab_api, "_get_json", lambda url, **kw: urls.append(url) or {})
    schwab_api.get_chain("$SPX", [PAIR_A])          # no `today` given -> market_today()
    assert seen and "fromDate=2026-12-24" in urls[0]
    assert ex.market_today().__class__.__name__ == "date"


def test_cache_serves_second_call_within_ttl(token_file, monkeypatch):
    write_tok(token_file, 1, 1)
    n = []
    monkeypatch.setattr(schwab_api.urllib.request, "urlopen",
                        lambda req, timeout=0: n.append(1) or FakeResp(b'{"a": 1}'))
    t = [100.0]
    monkeypatch.setattr(schwab_api, "_clock", lambda: t[0])
    assert schwab_api._get_json("http://x/1") == {"a": 1}
    assert schwab_api._get_json("http://x/1") == {"a": 1}
    assert len(n) == 1
    t[0] += config.CACHE_TTL_S + 1
    schwab_api._get_json("http://x/1")
    assert len(n) == 2
    schwab_api._get_json("http://x/1", use_cache=False)       # quote_spread() bypasses the cache
    assert len(n) == 3


def http_error(code, headers=None):
    return urllib.error.HTTPError("http://x", code, "err", headers or {}, io.BytesIO(b"body"))


def test_429_backs_off_then_succeeds(token_file, monkeypatch):
    write_tok(token_file, 1, 1)
    answers = [http_error(429, {"Retry-After": "2"}), http_error(429), FakeResp(b'{"ok": true}')]

    def fake(req, timeout=0):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a
    sleeps = []
    monkeypatch.setattr(schwab_api.urllib.request, "urlopen", fake)
    monkeypatch.setattr(schwab_api, "_sleep", sleeps.append)
    assert schwab_api._get_json("http://x/429", use_cache=False) == {"ok": True}
    assert sleeps == [2.0, 4.0]                                # exponential: Retry-After, then doubled


def test_other_http_errors_raise(token_file, monkeypatch):
    write_tok(token_file, 1, 1)
    monkeypatch.setattr(schwab_api.urllib.request, "urlopen",
                        lambda req, timeout=0: (_ for _ in ()).throw(http_error(502)))
    with pytest.raises(schwab_api.SchwabHTTPError) as e:
        schwab_api._get_json("http://x/502", use_cache=False)
    assert e.value.status == 502


def test_rate_limiter_waits_when_full(monkeypatch):
    schwab_api._calls.clear()
    t = [0.0]
    sleeps = []
    monkeypatch.setattr(schwab_api, "_clock", lambda: t[0])
    monkeypatch.setattr(schwab_api, "_sleep", lambda s: (sleeps.append(s), t.__setitem__(0, t[0] + s)))
    for _ in range(config.SCHWAB_REQUESTS_PER_MIN):
        schwab_api._rate_limit()
    assert sleeps == []
    schwab_api._rate_limit()                                   # the 101st must wait for the window
    assert sleeps and sum(sleeps) >= 60 - 0.01
    schwab_api._calls.clear()


def test_get_quotes_one_call_none_for_missing(monkeypatch):
    urls = []
    monkeypatch.setattr(schwab_api, "_get_json", lambda url, **kw: urls.append(url) or {
        "$SPX": {"quote": {"bidPrice": 1.0, "askPrice": 2.0, "mark": 1.5, "lastPrice": 1.4}},
        "$VIX": {"quote": {"lastPrice": 17.0}}})
    out = schwab_api.get_quotes(["$SPX", "$VIX", "$SPX"])
    assert len(urls) == 1 and urls[0].count("%24SPX") == 1
    assert out["$SPX"]["mark"] == 1.5 and out["$VIX"]["bid"] is None and out["$VIX"]["last"] == 17.0
