import re
import subprocess

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.version import _get_git_commit, router


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.mark.asyncio
async def test_version_returns_200_with_all_keys(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/version")

    assert r.status_code == 200
    assert set(r.json().keys()) == {"app_name", "version", "git_commit", "python_version"}


@pytest.mark.asyncio
async def test_version_contract_constants(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/version")

    data = r.json()
    assert data["app_name"] == "ia-expert-army"
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_version_git_commit_format(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/version")

    git_commit = r.json()["git_commit"]
    assert isinstance(git_commit, str)
    assert git_commit == "unknown" or re.match(r"^[0-9a-f]{7,}$", git_commit), (
        f"git_commit '{git_commit}' is neither 'unknown' nor a valid short hash"
    )


@pytest.mark.asyncio
async def test_version_python_version_format(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/version")

    assert re.match(r"^\d+\.\d+\.\d+", r.json()["python_version"])


# --- Unit tests for _get_git_commit() fallback logic ---


def test_get_git_commit_returns_stripped_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="a1b2c3d\n", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)

    assert _get_git_commit() == "a1b2c3d"


def test_get_git_commit_fallback_on_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_file_not_found(*args, **kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", raise_file_not_found)

    assert _get_git_commit() == "unknown"


def test_get_git_commit_fallback_on_called_process_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_called_process_error(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=128, cmd="git")

    monkeypatch.setattr(subprocess, "run", raise_called_process_error)

    assert _get_git_commit() == "unknown"


def test_get_git_commit_fallback_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=2.0)

    monkeypatch.setattr(subprocess, "run", raise_timeout)

    assert _get_git_commit() == "unknown"


def test_get_git_commit_fallback_on_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_os_error(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(subprocess, "run", raise_os_error)

    assert _get_git_commit() == "unknown"
