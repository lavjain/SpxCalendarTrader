import pytest

from app.core import services, tos
from app.core.tos import TosParseError, format_order, parse_order

OPEN = "BUY +13 CALENDAR SPX 100 (Weeklys) 19 FEB 27/12 FEB 27 6800 PUT @7.70 LMT"
CLOSE = "SELL -13 CALENDAR SPX 100 (Weeklys) 12 FEB 27/5 FEB 27 6735 PUT @8.70 LMT"


def test_format_matches_the_thinkorswim_lines():
    assert format_order("BUY", 13, "2027-02-12", "2027-02-19", 6800, 7.70) == OPEN
    assert format_order("SELL", 13, "2027-02-05", "2027-02-12", 6735.0, 8.7) == CLOSE


def test_a_thursday_expiry_and_a_single_digit_day():
    line = format_order("BUY", 8, "2026-12-24", "2026-12-31", 7140, 12.9)
    assert line == "BUY +8 CALENDAR SPX 100 (Weeklys) 31 DEC 26/24 DEC 26 7140 PUT @12.90 LMT"
    assert format_order("BUY", 1, "2027-02-05", "2027-02-12", 6800, 9.2).count("5 FEB 27") == 1


@pytest.mark.parametrize("line,side,n,short,long_,k,price", [
    (OPEN, "BUY", 13, "2027-02-12", "2027-02-19", 6800, 7.70),
    (CLOSE, "SELL", 13, "2027-02-05", "2027-02-12", 6735, 8.70)])
def test_parse_reads_every_field(line, side, n, short, long_, k, price):
    o = parse_order(line)
    assert (o.side, o.contracts, o.short_expiry, o.long_expiry, o.strike, o.price) == (side, n, short, long_, k, price)


def test_round_trip():
    line = format_order("BUY", 8, "2026-12-24", "2026-12-31", 7140, 12.95)
    o = parse_order(line)
    assert format_order(o.side, o.contracts, o.short_expiry, o.long_expiry, o.strike, o.price) == line


def test_parse_is_forgiving_about_case_spacing_and_the_dates_order():
    o = parse_order("  buy  +2 calendar spx 100 (weeklys) 12 feb 27/19 feb 27  6800 put @7.7  \n")
    assert (o.short_expiry, o.long_expiry, o.contracts, o.price) == ("2027-02-12", "2027-02-19", 2, 7.7)


@pytest.mark.parametrize("line,msg", [
    ("", "nothing to read"),
    ("CALENDAR SPX 100 (Weeklys) 19 FEB 27/12 FEB 27 6800 PUT @7.70 LMT", "BUY or SELL"),
    ("BUY CALENDAR SPX 100 (Weeklys) 19 FEB 27/12 FEB 27 6800 PUT @7.70 LMT", "quantity"),
    ("BUY +13 CALENDAR SPX 100 (Weeklys) 19 FEB 27 6800 PUT @7.70 LMT", "both expiries"),
    ("BUY +13 CALENDAR SPX 100 (Weeklys) 19 FEB 27/12 FEB 27 PUT @7.70 LMT", "strike"),
    ("BUY +13 CALENDAR SPX 100 (Weeklys) 19 FEB 27/12 FEB 27 6800 CALL @7.70 LMT", "Put calendars only"),
    ("BUY +13 CALENDAR SPX 100 (Weeklys) 26 FEB 27/12 FEB 27 6800 PUT @7.70 LMT", "14-day width"),
    ("BUY +13 CALENDAR SPX 100 (Weeklys) 19 FEB 27/12 FEB 27 6800 PUT LMT", "price"),
    ("BUY +13 CALENDAR SPX 100 (Weeklys) 19 FEB 27/12 FEB 27 6800 PUT @7.70 LMT GTC", "Unexpected text"),
    ("BUY +13 CALENDAR SPX 100 (AM) 19 FEB 27/12 FEB 27 6800 PUT @7.70 LMT", "Weeklys"),
    ("BUY +13 CALENDAR SPX 100 19 FEB 27/12 FEB 27 6800 PUT @7.70 LMT", "Weeklys"),
    ("BUY +13 CALENDAR SPX 100 (Weeklys) 19 FEB 27/12 FEB 27 6800 PUT @7.70 LMT\n" + OPEN, "one order"),
    ("BUY +13 CALENDAR SPX 100 (Weeklys) 19 XYZ 27/12 FEB 27 6800 PUT @7.70 LMT", "expir")])
def test_each_kind_of_bad_line_says_what_is_wrong(line, msg):
    with pytest.raises(TosParseError, match=msg):
        parse_order(line)


def test_the_dialog_check_refuses_a_closing_order_and_a_different_calendar():
    ok = services.parse_tos_order(OPEN, "2027-02-12", "2027-02-19", 6800)
    assert ok.contracts == 13
    with pytest.raises(TosParseError, match="closing order"):
        services.parse_tos_order(CLOSE)
    with pytest.raises(TosParseError, match="strike 6800"):
        services.parse_tos_order(OPEN, "2027-02-12", "2027-02-19", 6790)
    with pytest.raises(TosParseError, match="not 2027-02-05"):
        services.parse_tos_order(OPEN, "2027-02-05", "2027-02-12", 6800)
    assert services.tos_order("BUY", 13, "2027-02-12", "2027-02-19", 6800, 7.7) == OPEN
