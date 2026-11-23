import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from app.core import config, services
from app.core.models import ExpirationsResult, Spot
from app.schemas import FinderFilters

router = APIRouter()


@router.get("/spot", response_model=Spot)
async def spot() -> Spot:
    return await asyncio.to_thread(services.get_spot)


@router.get("/expirations", response_model=ExpirationsResult)
async def expirations(dte_min: int = config.SHORT_DTE_DEFAULT[0], dte_max: int = config.SHORT_DTE_DEFAULT[1],
                      widths: list[int] = Query(default=list(config.WIDTHS_DEFAULT))) -> ExpirationsResult:
    try:
        f = FinderFilters(dte_min=dte_min, dte_max=dte_max, widths=widths)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=[err["msg"] for err in e.errors()]) from None
    return await asyncio.to_thread(services.get_expirations, f.dte_range, tuple(f.widths))
