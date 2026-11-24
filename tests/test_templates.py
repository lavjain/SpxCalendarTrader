"""Render the Finder templates against a real snapshot (jinja only, no web server needed)."""
from datetime import date

import pytest
from starlette.templating import Jinja2Templates

from app import formatting, info_text, view_models as vm
from app.core import config, schwab_api, services
from app.snapshots import SnapshotStore
from app.schemas import FinderFilters
from pathlib import Path
from tests.test_services import CHAIN

T = Jinja2Templates(directory=str(Path(__file__).parent.parent / "app" / "templates"))
for n in ("money", "pct", "signed", "pts", "num", "edate", "strike", "etime", "gamma", "mdate"):
    T.env.filters[n] = getattr(formatting, n)
T.env.globals.update(delta_label=config.DELTA_LABEL, delta_band_label=config.DELTA_BAND_LABEL,
                     target_pct=round(config.FLAG_TARGET * 100), loss_pct=round(config.FLAG_LOSS * 100))
T.env.globals["url_for"] = lambda name, **kw: "/static/" + kw.get("path", "")
T.env.globals["static_url"] = lambda path: "/static/" + path
T.env.globals["info"] = info_text.info


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
                quote_interval_s=2, finder_refresh_s=60, fill_offset=config.FILL_OFFSET,
                default_margin=config.MARGIN, default_contracts=config.DEFAULT_CONTRACTS)
    empty = render("finder.html", results=None, **base)
    assert 'hx-post="/partials/compare"' in empty and 'data-refresh-s="60"' in empty and "↻ Compare" not in empty
    assert 'id="compare-box">' in empty and 'id="compare-box" open' not in empty
    assert 'id="compare-strike"' in empty and 'hx-post="/partials/spx-averages"' in empty
    assert "Press" in empty and "unavailable" in empty and 'id="refresh"' in empty and "Holdings" in empty
    assert empty.index('id="refresh"') < empty.index('id="updated-at"') and "Pulled" not in empty
    full = render("finder.html", results=vm.results_context(snap), **{**base, "last_refresh": snap.result.time})
    assert "calendars-table" in full and "ET" in full


def test_no_unformatted_floats_leak(snap):
    html = render("partials/_results.html", results=vm.results_context(snap))
    import re
    assert not re.search(r"\d\.\d{7,}", html)


def test_the_open_trade_button_carries_the_calendar_and_the_dialog_is_on_the_page(snap):
    base = dict(active_tab="finder", version="0.1", account="Paper", feature_analyzer=False, last_refresh=None,
                filters=FinderFilters(), widths_all=config.WIDTHS, unavailable_widths=[], dte_limits=config.SHORT_DTE_LIMITS,
                quote_interval_s=2, finder_refresh_s=60, fill_offset=config.FILL_OFFSET,
                default_margin=config.MARGIN, default_contracts=config.DEFAULT_CONTRACTS)
    full = render("finder.html", results=vm.results_context(snap), **base)
    assert 'id="open-dialog"' in full and 'data-interval-ms="2000"' in full and "js/opentrade.js" in full
    assert 'id="open-trade-btn"' in full and f'data-snapshot-id="{snap.snapshot_id}"' in full
    assert 'data-short-symbol="SPXW' in full and 'data-size-mode="margin"' in full and "Copy to TOS" in full


def test_size_by_select_carries_the_defaults_for_each_mode(snap):
    base = dict(active_tab="finder", version="0.1", account="Paper", feature_analyzer=False, last_refresh=None,
                filters=FinderFilters(), widths_all=config.WIDTHS, unavailable_widths=[], dte_limits=config.SHORT_DTE_LIMITS,
                quote_interval_s=2, finder_refresh_s=60, fill_offset=config.FILL_OFFSET,
                default_margin=config.MARGIN, default_contracts=config.DEFAULT_CONTRACTS)
    html = render("finder.html", results=None, **base)
    assert 'data-default-contracts="10"' in html and 'data-default-margin="10000"' in html


def test_holiday_note_shows_under_the_width_chips(snap):
    from app.core.models import HolidayNote
    base = dict(active_tab="finder", version="0.1", account="Paper", feature_analyzer=False, last_refresh=None,
                filters=FinderFilters(), widths_all=config.WIDTHS, unavailable_widths=[], dte_limits=config.SHORT_DTE_LIMITS,
                quote_interval_s=2, finder_refresh_s=60, fill_offset=config.FILL_OFFSET,
                default_margin=config.MARGIN, default_contracts=config.DEFAULT_CONTRACTS,
                holidays=[HolidayNote(date="2026-12-25", name="Christmas Day", moves_to="2026-12-24")])
    html = render("finder.html", results=None, **base)
    assert "Holiday Dec 25 (Christmas Day)" in html and "Move To" not in html and 'id="width-notes"' in html


def test_weekly_comparison_table_renders_bid_ask_and_greeks(snap):
    from app.core.models import ComparisonResult, ComparisonRow
    row = dict(short_expiry="2026-12-18", long_expiry="2026-12-24", short_dte=24, long_dte=30, strike=7210.0, price=7.15, short_iv=14.2, long_iv=13.6, skew=0.6)
    c = ComparisonResult(time="2026-11-24T10:00:00-05:00", spx=7240.0, width=7, rows=[
        ComparisonRow(target_dte=21, bid=7.05, ask=7.25, delta=-0.18, gamma=-0.0056, theta=30.6, vega=58.6, **row),
        ComparisonRow(target_dte=28, bid=None, ask=None, delta=-0.2, gamma=-0.004, theta=25.0, vega=70.0, **row)])
    html = render("partials/_compare.html", comparison=c)
    assert 'id="compare-table"' in html and "$7.05 / $7.25" in html and "Bid / Ask" in html and "Price" in html and "$7.15" in html
    assert all(h in html for h in ("Delta", "Gamma", "Theta", "Vega")) and "Short IV" in html and "Long IV" in html and "Skew" in html and "14.2%" in html and html.count("<tr>") == 3
    assert "No calendars found" in render("partials/_compare.html", comparison=c.model_copy(update={"rows": []}))


def test_calendar_panel_has_legs_and_risk_profile_tabs(snap):
    html = render("partials/_results.html", results=vm.results_context(snap))
    assert 'data-tab="legs"' in html and 'data-tab="risk"' in html
    assert 'id="risk-canvas"' in html and 'data-range="300"' in html



def test_results_keep_the_open_pair_and_fall_back_when_it_is_gone(snap):
    base = vm.results_context(snap)
    other = next(p for p in snap.result.pairs if p.rows and f"{p.short_expiry}|{p.long_expiry}" != base["open_key"])
    key = f"{other.short_expiry}|{other.long_expiry}"
    kept = vm.results_context(snap, None, key, other.rows[0].strike)
    assert kept["open_key"] == key and kept["selected_strike"] == other.rows[0].strike
    gone = vm.results_context(snap, None, "2000-01-07|2000-01-14", 1.0)
    assert gone["open_key"] == base["open_key"] and gone["selected_strike"] == base["selected_strike"]


def test_weekly_comparison_labels_rows_by_week_number():
    from app.core.models import ComparisonResult, ComparisonRow
    row = dict(short_expiry="2026-12-18", long_expiry="2026-12-24", short_dte=24, long_dte=30, strike=7210.0, price=7.15,
               bid=7.0, ask=7.2, delta=-0.2, gamma=-0.005, theta=30.0, vega=60.0, short_iv=14.0, long_iv=13.5, skew=0.5)
    c = ComparisonResult(time="2026-11-24T10:00:00-05:00", spx=7240.0, width=7,
                         rows=[ComparisonRow(target_dte=t, **row) for t in (7, 14, 42)])
    html = render("partials/_compare.html", comparison=c)
    assert ">Week</th>" in html and "<td>1</td>" in html and "<td>2</td>" in html and "<td>6</td>" in html and "Target DTE" not in html


def test_collapsing_the_open_pair_closes_the_table_but_keeps_the_panel(snap):
    base = vm.results_context(snap)
    out = vm.results_context(snap, None, vm.COLLAPSED, None, base["open_key"])
    assert out["open_pair"] is None and out["open_key"] is None
    assert out["pair"] is base["open_pair"] and out["row"] is not None          # the panel keeps its calendar
    html = render("partials/_calendars_table.html", **out)
    assert "strike-rows" not in html and "▾" not in html
    assert vm.results_context(snap, None, vm.COLLAPSED)["pair"] is not None     # no panel given: the default


def test_strike_rows_show_both_ivs_before_the_skew(snap):
    ctx = vm.results_context(snap)
    html = render("partials/_strike_rows.html", **ctx)
    assert html.index("Short IV") < html.index("Long IV") < html.index(">Skew<")
    r = ctx["open_pair"].rows[0]
    assert f"{r.short_iv:.2f}%" in html and f"{r.long_iv:.2f}%" in html


def test_open_dialog_has_target_flag_levels_and_the_keep_waiting_prompt(snap):
    html = render("finder.html", results=None, active_tab="finder", version="0.1", account="Paper", feature_analyzer=False,
                  last_refresh=None, filters=FinderFilters(), widths_all=config.WIDTHS, unavailable_widths=[7],
                  dte_limits=config.SHORT_DTE_LIMITS, quote_interval_s=2, finder_refresh_s=60, fill_offset=config.FILL_OFFSET,
                  default_margin=config.MARGIN, default_contracts=config.DEFAULT_CONTRACTS)
    assert 'id="od-target"' in html and 'id="od-flag"' in html and "+10%" in html and "-10%" in html
    assert 'id="od-keep"' in html and 'id="od-giveup-cancel"' in html


def test_both_finder_tables_show_a_bid_ask_column(snap):
    ctx = vm.results_context(snap)
    for name in ("partials/_calendars_table.html", "partials/_strike_rows.html"):
        html = render(name, **ctx)
        assert "Bid / Ask" in html and html.index("Price") < html.index("Bid / Ask"), name
    r = ctx["open_pair"].rows[0]
    assert f"${r.bid:,.2f} / ${r.ask:,.2f}" in render("partials/_strike_rows.html", **ctx)


def test_spx_averages_panel_and_strike_override_box():
    from app.core.models import SmaRow, SpxAverages
    a = SpxAverages(time="2026-11-23T10:00:00-05:00", spx=7000.0, last_close_date="2026-11-20",
                    rows=[SmaRow(days=10, value=6950.0, pct_from=0.72, side="above"),
                          SmaRow(days=50, value=7100.0, pct_from=-1.41, side="below")], missing=[20])
    html = render("partials/_spx_averages.html", averages=a)
    assert 'id="sma-table"' in html and "10-Day" in html and "50-Day" in html and "below" in html and "No 20-day average" in html
    assert "Not enough daily closes" in render("partials/_spx_averages.html", averages=SpxAverages(time="t", missing=[10, 20, 50]))
