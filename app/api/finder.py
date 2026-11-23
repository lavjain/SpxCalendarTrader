import asyncio

from fastapi import APIRouter, HTTPException, Request

from app.finder_flow import refresh_finder
from app.schemas import FinderFilters, FinderSnapshot

router = APIRouter()


@router.post("/finder/refresh", response_model=FinderSnapshot)
async def refresh(filters: FinderFilters, request: Request) -> FinderSnapshot:
    """Pull the chain, log the whole strike ladder, remember the snapshot. The only call that writes finder_log."""
    st = request.app.state
    return await asyncio.to_thread(refresh_finder, filters, st.store, st.snapshots)


@router.get("/finder", response_model=FinderSnapshot)
async def snapshot(request: Request, snapshot_id: str | None = None) -> FinderSnapshot:
    """A stored snapshot (the latest if no id). Never pulls Schwab."""
    snaps = request.app.state.snapshots
    snap = snaps.get(snapshot_id) if snapshot_id else snaps.latest()
    if snap is None:
        raise HTTPException(status_code=404, detail="No Finder snapshot (it expired or the server restarted): press Refresh")
    return snap
