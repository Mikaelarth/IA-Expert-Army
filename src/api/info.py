import os
import platform
import time

from fastapi import APIRouter
from pydantic import BaseModel

START_TIME: float = time.monotonic()

router: APIRouter = APIRouter()


class InfoResponse(BaseModel):
    uptime_seconds: float
    python_version: str
    pid: int


@router.get("/info", response_model=InfoResponse, summary="Runtime info")
async def get_info() -> InfoResponse:
    return InfoResponse(
        uptime_seconds=time.monotonic() - START_TIME,
        python_version=platform.python_version(),
        pid=os.getpid(),
    )
