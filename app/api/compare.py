import asyncio

from fastapi import APIRouter

from app.core import services
from app.core.models import ComparisonResult

router = APIRouter()


@router.post("/compare", response_model=ComparisonResult)
async def compare(strike: float | None = None) -> ComparisonResult:
    """The Weekly Comparison: one fixed strike (`strike`, else the starred row's) rounded to 25, for the Friday nearest each of 7, 14, ... 42 DTE.
    One chain pull; saves nothing and does not touch the Finder's snapshot or filters."""
    return await asyncio.to_thread(services.get_dte_comparison, strike=strike)
