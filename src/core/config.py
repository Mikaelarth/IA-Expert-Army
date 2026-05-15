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
    # Retry/timeout du SDK AsyncAnthropic (Sprint VV.1). Exposés depuis le SDK
    # mais implicites par défaut — on les rend explicites + configurables.
    # Le SDK fait du backoff exponentiel automatique entre les retries.
    anthropic_max_retries: int = Field(
        2, ge=0, le=5, description="Retries auto sur 5xx/timeout/connection error"
    )
    anthropic_timeout_seconds: float = Field(
        300.0, ge=10.0, description="Timeout par appel Claude (défaut SDK = 600s, on serre)"
    )

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
    # Quality Guardian (Sprint YY) — peer review méta cross-guilde. Opt-in car
    # ajoute ~$0.10-0.20/mission (1 appel Opus). À activer en mode autonome.
    enable_quality_guardian: bool = Field(
        False,
        description="Active le QG après chaque mission guilde (alignement promesse↔livraison)",
    )
    # Security Auditor (Sprint AAA) — audit OWASP / secrets / pratiques sécu
    # défensives sur les missions Engineering APPROVED. Opt-in car ajoute
    # ~$0.05-0.10/mission (1 appel Sonnet). À activer en mode autonome ou pour
    # les missions touchant des endpoints publics / données sensibles.
    enable_security_auditor: bool = Field(
        False,
        description="Active le SecurityAuditor après CodeReviewer pour les missions Engineering",
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
    # Sprint GGG.1 — kill-switch explicite pour environnements sans Docker
    # ou volontairement minimaux (VPS-1 phase démarrage). Quand False, les
    # appels validate_files_in_sandbox court-circuitent : aucun build d'image
    # demandé, aucune tentative de connexion daemon, simple log warning. Sûr
    # à laisser à True si Docker n'est pas installé : SandboxRunner détecte
    # déjà SandboxUnavailable gracieusement, mais ce flag évite même la
    # tentative (utile pour CI rapide ou diagnostic).
    enable_sandbox: bool = Field(
        True,
        description="False = skip validation sandbox (run_mission --validate devient no-op silencieux)",
    )

    # --- VPS profile (Sprint GGG) ---
    # Champ informatif pour adapter les warnings/comportements selon la
    # capacité hardware. Valeurs reconnues : "vps1" (8Go), "vps2" (12Go),
    # "vps3" (24Go), "local" (poste dev), "" (auto/inconnu).
    # N'affecte pas la logique métier — pur indicateur de diagnostic dans
    # les digests et le runbook.
    vps_profile: Literal["", "vps1", "vps2", "vps3", "local"] = Field(
        "",
        description="Indicateur du profil hardware (vps1/vps2/vps3/local) pour diagnostic",
    )

    # --- Notifications (Sprint HHH) ---
    # Webhook pour recevoir les notifications mobiles : daily digest, warnings
    # autonomous_run, alertes critiques (budget, killswitch).
    # Auto-détection du backend depuis l'URL :
    #   - discord.com/api/webhooks/...    → discord (embeds colorés)
    #   - hooks.slack.com/services/...    → slack (blocks)
    #   - api.telegram.org/bot.../sendMessage → telegram (markdown)
    #   - autre URL                       → generic (POST JSON brut, n8n/pipedream/zapier)
    notify_webhook_url: str = Field(
        "",
        description="Webhook URL pour notifications (Discord/Slack/Telegram/generic). Vide = désactivé.",
    )
    notify_backend: Literal["auto", "discord", "slack", "telegram", "generic", "none"] = Field(
        "auto",
        description="Backend notifier (auto = détection depuis URL)",
    )

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton settings, chargé une seule fois."""
    return Settings()  # type: ignore[call-arg]
