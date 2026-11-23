"""JSON API under /api. Every endpoint declares a response_model, so /docs documents all of it."""
from fastapi import APIRouter

from app.api import finder, health, market, settings

router = APIRouter(prefix="/api")
router.include_router(health.router, tags=["health"])
router.include_router(market.router, tags=["market"])
router.include_router(finder.router, tags=["finder"])
router.include_router(settings.router, tags=["settings"])
