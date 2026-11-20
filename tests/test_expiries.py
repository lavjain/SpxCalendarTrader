from datetime import date

import pytest

from app.core.expiries import is_trading_day, pick_expiries, previous_trading_day


def shorts_longs(pairs):
    return [(p.short, p.long) for p in pairs]


def test_thanksgiving_week_defaults_move_both_legs_to_thursday():
    # Tue Nov 24 2026: Fri Dec 25 and Fri Jan 1 are holidays
    pairs = pick_expiries(date(2026, 11, 24))
    assert shorts_longs(pairs) == [("2026-12-24", "2026-12-31")]
    p = pairs[0]
    assert (p.short_dte, p.long_dte, p.width) == (30, 37, 7)   # DTE to the actual expiry


def test_presidents_day_removes_three_day_pair():
    pairs = pick_expiries(date(2027, 1, 12), widths=(3, 4, 5, 6, 7))
    feb12 = [p for p in pairs if p.short == "2027-02-12"]
    assert [p.long for p in feb12] == ["2027-02-16", "2027-02-17", "2027-02-18", "2027-02-19"]
    assert 3 not in [p.width for p in feb12]
    assert [p.width for p in feb12] == [4, 5, 6, 7]       # widths counted from the nominal Friday


def test_full_range_returns_seven_or_eight_fridays():
    for today in (date(2026, 11, 24), date(2027, 1, 12), date(2027, 2, 2), date(2026, 12, 1)):
        assert len(pick_expiries(today, dte_range=(7, 56))) in (7, 8)


def test_good_friday_short_moves_to_thursday():
    pairs = pick_expiries(date(2027, 2, 23), widths=(7,))
    assert ("2027-03-25", "2027-04-02") in shorts_longs(pairs)


def test_friday_holiday_long_moves_to_thursday():
    # short Fri Dec 18 2026, 7-day long = Fri Dec 25 (holiday) -> Thu Dec 24
    pairs = pick_expiries(date(2026, 11, 17), widths=(7,))
    assert ("2026-12-18", "2026-12-24") in shorts_longs(pairs)


def test_juneteenth_observed_short_moves_to_thursday():
    pairs = pick_expiries(date(2027, 5, 18), widths=(7,))
    assert ("2027-06-17", "2027-06-25") in shorts_longs(pairs)


def test_holidays_in_set():
    assert not is_trading_day(date(2027, 2, 15))   # Presidents' Day
    assert not is_trading_day(date(2027, 1, 18))   # MLK Day
    assert not is_trading_day(date(2026, 12, 25))
    assert is_trading_day(date(2026, 12, 24))
    assert previous_trading_day(date(2027, 2, 15)) == date(2027, 2, 12)


def test_dte_range_and_width_validation():
    with pytest.raises(ValueError):
        pick_expiries(date(2026, 11, 24), dte_range=(5, 30))
    with pytest.raises(ValueError):
        pick_expiries(date(2026, 11, 24), dte_range=(25, 60))
    with pytest.raises(ValueError):
        pick_expiries(date(2026, 11, 24), widths=(2,))
