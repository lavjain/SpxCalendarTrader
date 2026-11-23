import asyncio

from fastapi import APIRouter, Path, Request

from app.schemas import SettingValue

router = APIRouter()
KEY = Path(..., pattern=r"^[a-z0-9_]{1,40}$")


@router.get("/settings/{key}", response_model=SettingValue)
async def read_setting(request: Request, key: str = KEY) -> SettingValue:
    value = await asyncio.to_thread(request.app.state.store.get_setting, key)
    return SettingValue(value=value)


@router.put("/settings/{key}", response_model=SettingValue)
async def write_setting(body: SettingValue, request: Request, key: str = KEY) -> SettingValue:
    await asyncio.to_thread(request.app.state.store.put_setting, key, body.value)
    return body
