import asyncio

from fastapi import APIRouter

from app.core import services
from app.core.models import ComparisonResult

router = APIRouter()


@router.post("/compare", response_model=ComparisonResult)
async def compare() -> ComparisonResult:
    """The Weekly Comparison: the target-delta calendar for the Friday nearest each of 7, 14, ... 42 DTE.
    One chain pull; saves nothing and does not touch the Finder's snapshot or filters."""
    return await asyncio.to_thread(services.get_dte_comparison)
