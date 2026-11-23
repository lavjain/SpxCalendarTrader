"""Glue shared by the JSON route and the page: run the Finder once, log it, keep the snapshot.

This is web-layer plumbing, not trading logic: get_finder() and get_spot() decide everything."""
import logging

from app.core import services
from app.core.schwab_api import SchwabError
from app.core.store import Store
from app.schemas import FinderFilters, FinderSnapshot
from app.snapshots import SnapshotStore

log = logging.getLogger(__name__)


def refresh_finder(filters: FinderFilters, store: Store, snapshots: SnapshotStore) -> FinderSnapshot:
    """Blocking (Schwab calls): the routes run it with asyncio.to_thread."""
    result = services.get_finder(filters.dte_range, tuple(filters.widths), tuple(filters.strike_sets),
                                 filters.size_mode, filters.size_value)
    try:
        spot = services.get_spot()               # a missing quote must not break a Refresh
    except SchwabError as e:
        log.warning("spot quote failed: %s", e)
        spot = None
    snap = snapshots.put(result, spot)
    store.log_finder(result, spot, snap.snapshot_id)   # only a Refresh writes the ladder
    return snap
