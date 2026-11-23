import asyncio

from fastapi import APIRouter

from app.core import services
from app.schemas import TosOrderLine, TosOrderRequest

router = APIRouter()


@router.post("/tos-order", response_model=TosOrderLine)
async def tos_order(req: TosOrderRequest) -> TosOrderLine:
    """The thinkorswim order line for the dialog's calendar and price. The app sends no orders; the UI only copies it."""
    line = await asyncio.to_thread(services.tos_order, req.side, req.contracts, req.short_expiry, req.long_expiry,
                                   req.strike, req.price)
    return TosOrderLine(line=line)
