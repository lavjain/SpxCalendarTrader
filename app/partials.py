"""HTMX fragments under /partials. They only render a stored snapshot: no Schwab calls, no calculation.
The one exception is POST /partials/compare, which runs the Weekly Comparison (one chain pull) and renders it."""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

import asyncio

from app import view_models
from app.core import services
from app.core.schwab_api import SchwabError
from app.pages import templates
from app.schemas import FinderSnapshot

router = APIRouter(prefix="/partials", include_in_schema=False)
EXPIRED = "That Finder snapshot has expired (or the server restarted): press Refresh"


def _snapshot(request: Request, snapshot_id: str) -> FinderSnapshot:
    snap = request.app.state.snapshots.get(snapshot_id)
    if snap is None:
        raise HTTPException(status_code=404, detail=EXPIRED)
    return snap


@router.get("/results", response_class=HTMLResponse)
async def results(request: Request, snapshot_id: str, sort: str | None = None):
    ctx = view_models.results_context(_snapshot(request, snapshot_id), sort)
    return templates.TemplateResponse(request, "partials/_results.html", {"results": ctx})


@router.get("/calendars", response_class=HTMLResponse)
async def calendars(request: Request, snapshot_id: str, sort: str | None = None,
                    open_key: str | None = Query(None, alias="open"), strike: float | None = None):
    ctx = view_models.results_context(_snapshot(request, snapshot_id), sort, open_key, strike)
    return templates.TemplateResponse(request, "partials/_calendars_table.html", ctx)


@router.get("/strike-rows", response_class=HTMLResponse)
async def strike_rows(request: Request, snapshot_id: str, short: str, long: str, strike: float | None = None):
    snap = _snapshot(request, snapshot_id)
    ctx = view_models.results_context(snap, None, f"{short}|{long}", strike)
    if ctx["open_pair"] is None:
        raise HTTPException(status_code=404, detail="That expiry pair is not in this snapshot")
    return templates.TemplateResponse(request, "partials/_strike_rows.html", ctx)


@router.get("/calendar-panel", response_class=HTMLResponse)
async def calendar_panel(request: Request, snapshot_id: str, short: str, long: str, strike: float | None = None):
    ctx = view_models.panel_context(_snapshot(request, snapshot_id), short, long, strike)
    return templates.TemplateResponse(request, "partials/_calendar_panel.html", ctx)


@router.post("/compare", response_class=HTMLResponse)
async def compare(request: Request):
    try:
        result = await asyncio.to_thread(services.get_dte_comparison)
    except SchwabError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    return templates.TemplateResponse(request, "partials/_compare.html", {"comparison": result})
