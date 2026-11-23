import asyncio

from fastapi import APIRouter

from app.core import services
from app.core.models import QuoteSpread
from app.schemas import QuoteSpreadRequest

router = APIRouter()


@router.post("/quote-spread", response_model=QuoteSpread)
async def quote_spread(req: QuoteSpreadRequest) -> QuoteSpread:
    """Re-quote the two legs right now (never cached) and say whether the price is steady. Called by the dialog every 2 s."""
    return await asyncio.to_thread(services.quote_spread, req.short_symbol, req.long_symbol, req.size_mode,
                                   req.size_value, req.fill_price, req.keep_waiting)
