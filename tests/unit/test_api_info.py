import os

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.info import router


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_info_status_and_schema(client: AsyncClient) -> None:
    response = await client.get("/info")

    assert response.status_code == 200

    data = response.json()
    assert set(data.keys()) == {"uptime_seconds", "python_version", "pid"}
    assert isinstance(data["uptime_seconds"], float)
    assert isinstance(data["python_version"], str)
    assert isinstance(data["pid"], int)


@pytest.mark.asyncio
async def test_info_uptime_monotonic(client: AsyncClient) -> None:
    first = (await client.get("/info")).json()
    second = (await client.get("/info")).json()

    # >= and not > : two calls in rapid succession may return identical monotonic values
    assert second["uptime_seconds"] >= first["uptime_seconds"]


@pytest.mark.asyncio
async def test_info_pid_stable(client: AsyncClient) -> None:
    first = (await client.get("/info")).json()
    second = (await client.get("/info")).json()

    assert first["pid"] == second["pid"] == os.getpid()
