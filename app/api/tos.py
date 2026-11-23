import asyncio

from fastapi import APIRouter, HTTPException

from app.core import services
from app.core.models import TosOrder
from app.core.tos import TosParseError
from app.schemas import TosOrderLine, TosOrderRequest, TosParseRequest

router = APIRouter()


@router.post("/tos-order", response_model=TosOrderLine)
async def tos_order(req: TosOrderRequest) -> TosOrderLine:
    """The thinkorswim order line for the dialog's calendar and price. The app sends no orders; the UI only copies it."""
    line = await asyncio.to_thread(services.tos_order, req.side, req.contracts, req.short_expiry, req.long_expiry,
                                   req.strike, req.price)
    return TosOrderLine(line=line)


@router.post("/tos-order/parse", response_model=TosOrder)
async def parse_tos_order(req: TosParseRequest) -> TosOrder:
    """Read a pasted thinkorswim line. 422 with the reason when it cannot be used in the Open Trade dialog."""
    try:
        return await asyncio.to_thread(services.parse_tos_order, req.text, req.short_expiry, req.long_expiry, req.strike)
    except TosParseError as e:
        raise HTTPException(422, str(e))
