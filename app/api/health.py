from fastapi import APIRouter

from app.schemas import HealthResponse
from app.settings import app_version

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=app_version())
