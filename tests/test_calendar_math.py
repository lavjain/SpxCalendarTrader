"""Lane Snell's 2021-09-17 sheet reproduced by calendar_math.build() — same tolerances as selftest()."""
import pytest

from app.core.calendar_math import LANE_2021_09_17, LANE_EXPECTED, Leg, build

CAPITAL = 80000


@pytest.fixture(scope="module")
def cals():
    legs = [Leg(*r) for r in LANE_2021_09_17]
    return {(c.s.dte, c.l.dte): c for c in build(legs, CAPITAL)}


def test_all_sixteen_rows_present(cals):
    assert len(LANE_EXPECTED) == 16
    for sd, ld, *_ in LANE_EXPECTED:
        assert (sd, ld) in cals


@pytest.mark.parametrize("row", LANE_EXPECTED, ids=lambda r: f"{r[0]}/{r[1]}")
def test_row_matches_lane_sheet(cals, row):
    sd, ld, ctr, deb, mgn, dl, gm, th, vg, sk, td = row
    c = cals[(sd, ld)]
    assert c.contracts == ctr
    assert c.debit == pytest.approx(deb, abs=0.005)
    assert c.margin == pytest.approx(mgn, abs=1.0)
    assert c.delta == pytest.approx(dl, abs=0.02)
    assert c.gamma == pytest.approx(gm, abs=0.02)
    assert c.theta == pytest.approx(th, abs=0.05)
    assert c.vega == pytest.approx(vg, abs=0.05)
    assert c.skew == pytest.approx(sk, abs=0.005)
    assert c.td == pytest.approx(td, abs=1.0)
