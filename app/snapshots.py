"""The last few Finder refreshes (one uvicorn worker, CLAUDE.md rule 9).

The table, strike rows and panel all read the same snapshot, so clicking never re-pulls Schwab.
With a file path, every snapshot is also kept in that one JSON file (newest `max_saved`), so a restart
reopens on the newest one (its time is in the status strip) instead of asking you to press Refresh.
Without a path (tests) it is memory-only and snapshots expire after ttl_s."""
import json
import logging
import os
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path

from app.core.models import FinderResult, Spot
from app.schemas import FinderSnapshot

log = logging.getLogger(__name__)


class SnapshotStore:
    def __init__(self, max_items: int = 5, ttl_s: float = 600, clock=time.monotonic,
                 path: str | os.PathLike | None = None, max_saved: int = 20):
        self.max_items, self.ttl_s, self._clock = max_items, ttl_s, clock
        self.path = Path(path).expanduser() if path else None
        self.max_saved = max_saved
        self._items: OrderedDict[str, tuple[float, FinderSnapshot]] = OrderedDict()   # memory-only mode
        self._saved: OrderedDict[str, FinderSnapshot] = OrderedDict()                 # file mode, oldest first
        self._lock = threading.Lock()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    # ---- file mode ----
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            for raw in json.loads(self.path.read_text()).get("snapshots", []):
                try:
                    snap = FinderSnapshot.model_validate(raw)
                    self._saved[snap.snapshot_id] = snap
                except ValueError as e:                  # one snapshot from an older version: skip it
                    log.warning("skipping a saved snapshot: %s", e)
        except (OSError, ValueError) as e:
            log.warning("ignoring unreadable snapshot file %s: %s", self.path, e)

    def _save(self) -> None:
        try:
            body = '{"snapshots": [' + ",".join(s.model_dump_json() for s in self._saved.values()) + "]}"
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(body)
            os.replace(tmp, self.path)                   # atomic: never a half-written file
        except OSError as e:                             # a full disk must not break a Refresh
            log.warning("could not save snapshots: %s", e)

    # ---- API ----
    def put(self, result: FinderResult, spot: Spot | None = None) -> FinderSnapshot:
        snap = FinderSnapshot(snapshot_id=uuid.uuid4().hex[:8], spot=spot, result=result)
        with self._lock:
            if self.path:
                self._saved[snap.snapshot_id] = snap
                while len(self._saved) > self.max_saved:
                    self._saved.popitem(last=False)
                self._save()
            else:
                self._items[snap.snapshot_id] = (self._clock(), snap)
                while len(self._items) > self.max_items:
                    self._items.popitem(last=False)
        return snap

    def get(self, snapshot_id: str | None) -> FinderSnapshot | None:
        if not snapshot_id:
            return None
        with self._lock:
            if self.path:
                return self._saved.get(snapshot_id)
            hit = self._items.get(snapshot_id)
            if hit and self._clock() - hit[0] > self.ttl_s:
                del self._items[snapshot_id]
                hit = None
        return hit[1] if hit else None

    def latest(self) -> FinderSnapshot | None:
        with self._lock:
            if self.path:
                return next(reversed(self._saved.values()), None)
            now = self._clock()
            for sid in reversed(self._items):
                t, snap = self._items[sid]
                if now - t <= self.ttl_s:
                    return snap
        return None
