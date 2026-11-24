import asyncio

from fastapi import APIRouter

from app.core import services
from app.core.models import ComparisonResult, SpxAverages

router = APIRouter()


@router.post("/compare", response_model=ComparisonResult)
async def compare(strike: float | None = None, exact: bool = False) -> ComparisonResult:
    """The Weekly Comparison: one fixed strike (`strike`, else the starred row's) rounded to 25, for the Friday nearest each of 7, 14, ... 42 DTE.
    One chain pull; saves nothing and does not touch the Finder's snapshot or filters."""
    return await asyncio.to_thread(services.get_dte_comparison, strike=strike, exact=exact)


@router.get("/spx-averages", response_model=SpxAverages)
async def spx_averages() -> SpxAverages:
    """10/20/50-day simple moving averages of SPX daily closes against the latest SPX price."""
    return await asyncio.to_thread(services.get_spx_averages)
