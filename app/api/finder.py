import asyncio

from fastapi import APIRouter, HTTPException, Request

from app.core import services
from app.core.models import RiskProfile
from app.finder_flow import find_calendar, refresh_finder
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


@router.get("/risk-profile", response_model=RiskProfile)
async def risk_profile(request: Request, snapshot_id: str, short: str, long: str, strike: float,
                       half_range: float = 300.0) -> RiskProfile:
    """P/L over SPX for one calendar of a stored snapshot: today and at the short expiry, repriced with Black-Scholes."""
    snap = request.app.state.snapshots.get(snapshot_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="That Finder snapshot expired or the server restarted: press Refresh")
    _, row = find_calendar(snap, short, long, strike)
    if row is None:
        raise HTTPException(status_code=404, detail="That calendar is not in the snapshot")
    try:
        return await asyncio.to_thread(services.get_risk_profile, row, snap.result.spx, half_range)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
