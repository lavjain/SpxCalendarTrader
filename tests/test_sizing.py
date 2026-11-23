import pytest

from app.core.calendar_math import Calendar, Leg


def cal(debit, capital=10_000, **kw):
    s = Leg(30, 10.0, -0.4, 0.001, 5.0, 3.0, 20.0)
    l = Leg(37, 10.0 + debit, -0.4, 0.001, 5.0, 3.0, 20.0)
    return Calendar(s, l, capital, **kw).contracts


@pytest.mark.parametrize("debit,ceil,nearest,floor", [
    (12.50, 8, 8, 8),      # exactly 8.0
    (12.45, 9, 8, 8),      # 8.03: nearest rounds down, ceil up
    (12.40, 9, 8, 8),      # 8.06
    (10.60, 10, 9, 9),     # 9.43
    (10.40, 10, 10, 9),    # 9.62: nearest rounds up
    (60.0, 2, 2, 1),       # 1.67
    (500.0, 1, 1, 1),      # 0.2: never fewer than one contract
])
def test_rounding_modes(debit, ceil, nearest, floor):
    assert cal(debit, rounding="ceil") == ceil
    assert cal(debit, rounding="nearest") == nearest
    assert cal(debit, rounding="floor") == floor


def test_fixed_contracts_and_bad_mode():
    assert cal(12.0, contracts=3) == 3
    with pytest.raises(ValueError):
        cal(12.0, rounding="up")
