"""HTMX fragments under /partials. They only render a stored snapshot: no Schwab calls, no calculation.
The exceptions are POST /partials/compare (the Weekly Comparison, one chain pull) and POST /partials/spx-averages (daily closes), which pull from Schwab and render."""
from urllib.parse import parse_qs

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
async def results(request: Request, snapshot_id: str, sort: str | None = None,
                  open_key: str | None = Query(None, alias="open"), strike: float | None = None,
                  panel: str | None = None):
    """`open`, `strike` and `panel` keep the user's open pair, strike and shown calendar through an automatic refresh."""
    ctx = view_models.results_context(_snapshot(request, snapshot_id), sort, open_key, strike, panel)
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
    """`strike`: the starred row of the open pair (sent by the page); blank = the starred row of the pair nearest 30 DTE."""
    # htmx posts a urlencoded body; parsed by hand so the app needs no python-multipart
    form = parse_qs((await request.body()).decode())
    strike = (form.get("strike") or [""])[0]
    exact = (form.get("override") or [""])[0] == "1"          # the strike was typed in the box: keep it
    try:
        wanted = float(strike) if strike.strip() else None
    except ValueError:
        raise HTTPException(status_code=422, detail="strike must be a number") from None
    try:
        result = await asyncio.to_thread(services.get_dte_comparison, strike=wanted, exact=exact and wanted is not None)
    except SchwabError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    return templates.TemplateResponse(request, "partials/_compare.html", {"comparison": result})


@router.post("/spx-averages", response_class=HTMLResponse)
async def spx_averages(request: Request):
    try:
        result = await asyncio.to_thread(services.get_spx_averages)
    except SchwabError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    return templates.TemplateResponse(request, "partials/_spx_averages.html", {"averages": result})
