"""HTML pages: the shared Jinja templates, filters, page_context(), and the Finder page route."""
import asyncio
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from starlette.templating import Jinja2Templates

from app import formatting, view_models
from app.core import config, services
from app.schemas import FinderFilters
from app.settings import app_version, get_settings

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
for _name in ("money", "pct", "signed", "pts", "num", "edate", "strike", "etime", "gamma", "mdate"):
    templates.env.filters[_name] = getattr(formatting, _name)
templates.env.globals.update(delta_label=config.DELTA_LABEL, delta_band_label=config.DELTA_BAND_LABEL)

router = APIRouter()


def page_context(request: Request, active_tab: str) -> dict:
    """The context every page shares: feature flags, active tab, app version, account, last refresh."""
    snap = request.app.state.snapshots.latest()
    return {"active_tab": active_tab, "version": app_version(), "account": "Paper",
            "feature_analyzer": get_settings().feature_analyzer,
            "last_refresh": snap.result.time if snap else None}


@router.get("/", include_in_schema=False)
async def home() -> RedirectResponse:
    return RedirectResponse("/finder")


@router.get("/finder", response_class=HTMLResponse, include_in_schema=False)
async def finder_page(request: Request):
    saved = await asyncio.to_thread(request.app.state.store.get_setting, "finder_filters")
    try:
        filters = FinderFilters(**(saved or {}))
    except (ValidationError, TypeError):
        filters = FinderFilters()
    exp = services.get_expirations(filters.dte_range, tuple(filters.widths))   # date math only, no Schwab call
    snap = request.app.state.snapshots.latest()
    ctx = {**page_context(request, "finder"), "filters": filters, "widths_all": config.WIDTHS,
           "unavailable_widths": exp.unavailable_widths, "holidays": exp.holidays, "dte_limits": config.SHORT_DTE_LIMITS,
           "results": view_models.results_context(snap) if snap else None,
           "default_margin": config.MARGIN, "default_contracts": config.DEFAULT_CONTRACTS,
           "compare_width": config.COMPARE_WIDTH, "quote_interval_s": config.QUOTE_INTERVAL_S, "fill_offset": config.FILL_OFFSET}
    return templates.TemplateResponse(request, "finder.html", ctx)
