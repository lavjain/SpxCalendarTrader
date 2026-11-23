import pytest
from pydantic import ValidationError

from app.core import config
from app.schemas import FinderFilters
from app.snapshots import SnapshotStore
from app.core.models import FinderResult


def test_defaults_match_config():
    f = FinderFilters()
    assert f.dte_range == config.SHORT_DTE_DEFAULT and f.widths == [7]
    assert f.strike_sets == ["10", "25"] and (f.size_mode, f.size_value) == ("margin", 10_000)


@pytest.mark.parametrize("bad", [
    {"dte_min": 5}, {"dte_max": 60}, {"dte_min": 40, "dte_max": 30}, {"widths": []}, {"widths": [2]},
    {"strike_sets": []}, {"strike_sets": ["50"]}, {"size_mode": "shares"}, {"size_value": 0},
    {"size_value": -5}, {"size_mode": "contracts", "size_value": 2.5}])
def test_bad_filters_are_rejected(bad):
    with pytest.raises(ValidationError):
        FinderFilters(**bad)


def test_filters_are_normalised():
    f = FinderFilters(widths=[7, 4, 4], strike_sets=["25", "10"], size_mode="contracts", size_value=3)
    assert f.widths == [4, 7] and f.strike_sets == ["10", "25"]


def snap_result():
    return FinderResult(time="2026-11-24T10:00:00-05:00", spx=1.0, filters={}, pairs=[])


def test_snapshot_ids_resolve_and_old_ones_drop_out():
    s = SnapshotStore(max_items=2)
    ids = [s.put(snap_result()).snapshot_id for _ in range(3)]
    assert s.get(ids[0]) is None and s.get(ids[1]) and s.get(ids[2])
    assert s.latest().snapshot_id == ids[2]
    assert s.get(None) is None and s.get("nope") is None


def test_snapshots_expire():
    t = [0.0]
    s = SnapshotStore(ttl_s=10, clock=lambda: t[0])
    sid = s.put(snap_result()).snapshot_id
    t[0] = 5
    assert s.get(sid)
    t[0] = 20
    assert s.get(sid) is None and s.latest() is None


def test_snapshots_survive_a_restart_in_one_file(tmp_path):
    f = tmp_path / "data" / "snapshots.json"
    a = SnapshotStore(path=f)
    one = a.put(snap_result())
    two = a.put(snap_result())
    b = SnapshotStore(path=f)                                 # a "restart": new object, same file
    assert b.get(one.snapshot_id).result.time == one.result.time
    assert b.latest().snapshot_id == two.snapshot_id
    assert b.get("../etc/passwd") is None and b.get("nope") is None
    assert [p.name for p in f.parent.iterdir()] == ["snapshots.json"]    # one file, no leftovers


def test_saved_snapshots_are_pruned_and_a_bad_file_ignored(tmp_path):
    f = tmp_path / "s.json"
    s = SnapshotStore(path=f, max_saved=3)
    ids = [s.put(snap_result()).snapshot_id for _ in range(5)]
    again = SnapshotStore(path=f)
    assert list(again._saved) == ids[-3:]
    f.write_text("{not json")
    assert SnapshotStore(path=f).latest() is None
