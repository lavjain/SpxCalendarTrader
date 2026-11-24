import pytest

from app.core import schwab_api


@pytest.fixture(autouse=True)
def no_live_schwab_for_the_newer_pulls(monkeypatch):
    """Tests never reach Schwab: the Weekly Comparison's call pull and the daily-closes pull answer 'nothing'
    unless a test sets its own (on a machine with a Schwab token they would otherwise go live)."""
    monkeypatch.setattr(schwab_api, "get_call_chain_at", lambda sym, pairs, strike: {})
    monkeypatch.setattr(schwab_api, "get_daily_closes", lambda symbol="$SPX", use_cache=True: [])
