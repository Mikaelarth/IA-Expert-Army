import platform
import subprocess

from fastapi import APIRouter

APP_NAME: str = "ia-expert-army"
VERSION: str = "0.1.0"


def _get_git_commit() -> str:
    """Run `git rev-parse --short HEAD` once at module load.

    Returns the short commit hash, or 'unknown' when git is unavailable
    (Docker images without .git, CI shallow clones, missing git binary, etc.).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 — `git` PATH-resolved volontairement (cross-platform Docker/CI)
            capture_output=True,
            text=True,
            timeout=2.0,
            check=True,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return "unknown"


# Computed once at import time — git_commit is stable for the lifetime of the process.
_GIT_COMMIT: str = _get_git_commit()

router: APIRouter = APIRouter()


@router.get("/version")
async def get_version() -> dict[str, str]:
    return {
        "app_name": APP_NAME,
        "version": VERSION,
        "git_commit": _GIT_COMMIT,
        "python_version": platform.python_version(),
    }
