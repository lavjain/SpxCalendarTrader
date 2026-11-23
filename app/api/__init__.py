"""JSON API under /api. Every endpoint declares a response_model, so /docs documents all of it."""
from fastapi import APIRouter

from app.api import finder, health, market, quotes, settings, tos, trades

router = APIRouter(prefix="/api")
router.include_router(health.router, tags=["health"])
router.include_router(market.router, tags=["market"])
router.include_router(finder.router, tags=["finder"])
router.include_router(settings.router, tags=["settings"])
router.include_router(quotes.router, tags=["quotes"])
router.include_router(trades.router, tags=["trades"])
router.include_router(tos.router, tags=["tos"])
