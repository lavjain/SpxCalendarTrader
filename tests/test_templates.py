"""Render the Finder templates against a real snapshot (jinja only, no web server needed)."""
from datetime import date

import pytest
from starlette.templating import Jinja2Templates

from app import formatting, view_models as vm
from app.core import config, schwab_api, services
from app.snapshots import SnapshotStore
from app.schemas import FinderFilters
from pathlib import Path
from tests.test_services import CHAIN

T = Jinja2Templates(directory=str(Path(__file__).parent.parent / "app" / "templates"))
for n in ("money", "pct", "signed", "pts", "num", "edate", "strike", "etime", "gamma", "mdate"):
    T.env.filters[n] = getattr(formatting, n)
T.env.globals.update(delta_label=config.DELTA_LABEL, delta_band_label=config.DELTA_BAND_LABEL)
T.env.globals["url_for"] = lambda name, **kw: "/static/" + kw.get("path", "")


@pytest.fixture
def snap(monkeypatch):
    monkeypatch.setattr(services, "market_today", lambda: date(2026, 11, 24))
    monkeypatch.setattr(schwab_api, "get_chain", lambda s, p, **kw: CHAIN)
    monkeypatch.setattr(schwab_api, "get_call_chain", lambda s, p, **kw: CHAIN)
    return SnapshotStore().put(services.get_finder(dte_range=(7, 56), widths=(7,)))


def render(name, **ctx):
    return T.env.get_template(name).render(**ctx)


def test_results_fragment_has_default_pair_open_and_panel(snap):
    ctx = vm.results_context(snap)
    html = render("partials/_results.html", results=ctx)
    assert "calendars-table" in html and "strike-rows" in html and "Open Trade" in html
    assert html.count("★") == 1 and "Break-Evens" in html and "IV Ratio" in html


def test_closed_pair_has_no_strike_rows(snap):
    ctx = vm.results_context(snap)
    ctx["open_key"] = None
    html = render("partials/_calendars_table.html", **ctx)
    assert 'class="strike-rows"' not in html


def test_empty_snapshot_message(snap):
    snap.result.pairs.clear()
    html = render("partials/_results.html", results=vm.results_context(snap))
    assert "No expiry pairs" in html and "Select a pair" in html


def test_finder_page_renders_both_states(snap):
    filters = FinderFilters()
    base = dict(active_tab="finder", version="0.1", account="Paper", feature_analyzer=False, last_refresh=None,
                filters=filters, widths_all=config.WIDTHS, unavailable_widths=[7], dte_limits=config.SHORT_DTE_LIMITS,
                quote_interval_s=2, fill_offset=config.FILL_OFFSET,
                default_margin=config.MARGIN, default_contracts=config.DEFAULT_CONTRACTS)
    empty = render("finder.html", results=None, **base)
    assert "Press" in empty and "unavailable" in empty and 'id="refresh"' in empty and "Holdings" in empty
    full = render("finder.html", results=vm.results_context(snap), **{**base, "last_refresh": snap.result.time})
    assert "calendars-table" in full and "ET" in full


def test_no_unformatted_floats_leak(snap):
    html = render("partials/_results.html", results=vm.results_context(snap))
    import re
    assert not re.search(r"\d\.\d{7,}", html)


def test_the_open_trade_button_carries_the_calendar_and_the_dialog_is_on_the_page(snap):
    base = dict(active_tab="finder", version="0.1", account="Paper", feature_analyzer=False, last_refresh=None,
                filters=FinderFilters(), widths_all=config.WIDTHS, unavailable_widths=[], dte_limits=config.SHORT_DTE_LIMITS,
                quote_interval_s=2, fill_offset=config.FILL_OFFSET,
                default_margin=config.MARGIN, default_contracts=config.DEFAULT_CONTRACTS)
    full = render("finder.html", results=vm.results_context(snap), **base)
    assert 'id="open-dialog"' in full and 'data-interval-ms="2000"' in full and "js/opentrade.js" in full
    assert 'id="open-trade-btn"' in full and f'data-snapshot-id="{snap.snapshot_id}"' in full
    assert 'data-short-symbol="SPXW' in full and 'data-size-mode="margin"' in full and "Copy to TOS" in full


def test_size_by_select_carries_the_defaults_for_each_mode(snap):
    base = dict(active_tab="finder", version="0.1", account="Paper", feature_analyzer=False, last_refresh=None,
                filters=FinderFilters(), widths_all=config.WIDTHS, unavailable_widths=[], dte_limits=config.SHORT_DTE_LIMITS,
                quote_interval_s=2, fill_offset=config.FILL_OFFSET,
                default_margin=config.MARGIN, default_contracts=config.DEFAULT_CONTRACTS)
    html = render("finder.html", results=None, **base)
    assert 'data-default-contracts="10"' in html and 'data-default-margin="10000"' in html


def test_holiday_note_shows_under_the_width_chips(snap):
    from app.core.models import HolidayNote
    base = dict(active_tab="finder", version="0.1", account="Paper", feature_analyzer=False, last_refresh=None,
                filters=FinderFilters(), widths_all=config.WIDTHS, unavailable_widths=[], dte_limits=config.SHORT_DTE_LIMITS,
                quote_interval_s=2, fill_offset=config.FILL_OFFSET,
                default_margin=config.MARGIN, default_contracts=config.DEFAULT_CONTRACTS,
                holidays=[HolidayNote(date="2026-12-25", name="Christmas Day", moves_to="2026-12-24")])
    html = render("finder.html", results=None, **base)
    assert "Holiday Dec 25 (Christmas Day)" in html and "Move To" not in html and 'id="width-notes"' in html
