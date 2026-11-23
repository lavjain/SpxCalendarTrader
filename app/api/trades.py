import asyncio

from fastapi import APIRouter, HTTPException, Request

from app.core import services
from app.core.models import OpenTradeResult, Trade
from app.core.schwab_api import SchwabError
from app.core.store import DuplicateTradeError
from app.schemas import OpenTradeRequest

router = APIRouter()


def _find(snap, req: OpenTradeRequest):
    for pair in snap.result.pairs:
        if pair.short_expiry == req.short_expiry and pair.long_expiry == req.long_expiry:
            for row in pair.rows:
                if abs(row.strike - req.strike) < 1e-6:
                    return pair, row
    return None, None


def _open(st, req: OpenTradeRequest) -> OpenTradeResult:
    snap = st.snapshots.get(req.snapshot_id)
    if snap is None:
        raise HTTPException(404, "That Finder snapshot expired or the server restarted: press Refresh and try again")
    pair, row = _find(snap, req)
    if row is None:
        raise HTTPException(404, "That calendar is not in the snapshot")
    try:
        spot = services.get_spot()
    except SchwabError:
        spot = snap.spot
    try:
        return services.open_trade(st.store, pair, row, spot, req.size_mode, req.size_value, req.contracts,
                                   req.fill_price, req.price_source, account=req.account)
    except DuplicateTradeError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/trades", response_model=OpenTradeResult, status_code=201)
async def open_trade(req: OpenTradeRequest, request: Request) -> OpenTradeResult:
    """Save a paper trade from a Finder snapshot. Nothing is sent to a broker."""
    return await asyncio.to_thread(_open, request.app.state, req)


@router.get("/trades", response_model=list[Trade])
async def list_trades(request: Request, status: str | None = None, account: str = "Paper") -> list[Trade]:
    return await asyncio.to_thread(request.app.state.store.list_trades, status, account)
