"""Settings — configuration centralisée, type-safe, chargée depuis .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Anthropic ---
    anthropic_api_key: SecretStr = Field(..., description="Clé API Anthropic")

    # --- Modèles par tier ---
    model_strategic: str = Field("claude-opus-4-7", description="Modèle pour rôles stratégiques")
    model_operational: str = Field(
        "claude-sonnet-4-6", description="Modèle pour rôles opérationnels"
    )
    model_bulk: str = Field(
        "claude-haiku-4-5-20251001", description="Modèle pour tâches volumineuses"
    )

    # --- Limites & garde-fous ---
    daily_budget_usd: float = Field(10.0, ge=0, description="Plafond budget quotidien en USD")
    max_agent_turns: int = Field(20, ge=1, description="Nombre max de tours par agent")
    max_concurrent_agents: int = Field(5, ge=1, description="Agents concurrents max")
    circuit_breaker_error_rate: float = Field(
        0.3, ge=0, le=1, description="Seuil d'erreur déclenchant le circuit breaker"
    )

    # --- Logging ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    # --- Infrastructure ---
    redis_url: str = Field("redis://localhost:6379/0", description="URL Redis")
    chroma_persist_dir: Path = Field(PROJECT_ROOT / "data" / "chroma")
    sqlite_db_path: Path = Field(PROJECT_ROOT / "data" / "memory.db")

    # --- Langfuse ---
    langfuse_host: str = Field("http://localhost:3000")
    langfuse_public_key: str = Field("")
    langfuse_secret_key: SecretStr = Field(SecretStr(""))

    # --- Sandbox ---
    sandbox_image: str = Field("python:3.12-slim")
    sandbox_network: str = Field("none")
    sandbox_timeout_seconds: int = Field(30, ge=1)
    sandbox_memory_limit: str = Field("512m")

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton settings, chargé une seule fois."""
    return Settings()  # type: ignore[call-arg]
