"""Settings — configuration centralisée, type-safe, chargée depuis .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Backend LLM : Ollama local (ADR-025) ---
    # Bascule v0.4.0 — l'API Anthropic est remplacée par Ollama via son
    # endpoint OpenAI-compatible (http://localhost:11434/v1). Le SDK `openai`
    # est utilisé comme client générique. Aucune clé API requise (placeholder
    # "ollama" suffit), aucun coût USD : tout tourne en local.
    ollama_base_url: str = Field(
        "http://localhost:11434/v1",
        description="URL de l'endpoint OpenAI-compatible d'Ollama (peut viser un LAN/proxy).",
    )
    ollama_api_key: str = Field(
        "ollama",
        description="Placeholder API key — Ollama ignore la valeur mais le SDK openai l'exige.",
    )
    ollama_max_retries: int = Field(
        2, ge=0, le=5, description="Retries auto sur erreurs réseau / 5xx"
    )
    ollama_timeout_seconds: float = Field(
        600.0,
        ge=10.0,
        description=(
            "Timeout par appel Ollama. Plus généreux qu'avec Claude car les "
            "modèles locaux (Qwen 32B…) peuvent prendre plusieurs minutes à "
            "générer 16k tokens, surtout sans GPU."
        ),
    )

    # --- Modèles par tier (Ollama tags exacts) ---
    # Setup recommandé (ADR-025) : trio Qwen2.5 — qualité YAML structuré et
    # gestion du français très solides à ces tailles. À adapter au hardware
    # local : sur machine modeste, basculer sur qwen2.5:14b / 7b.
    model_strategic: str = Field(
        "qwen2.5:32b",
        description=(
            "Modèle pour rôles stratégiques (Architect, ChiefOrch, "
            "QualityGuardian, BusinessAnalyst, ResearchLead, ContentStrategist). "
            "Doit gérer le jugement nuancé."
        ),
    )
    model_operational: str = Field(
        "qwen2.5-coder:32b",
        description=(
            "Modèle pour rôles opérationnels (BackendDeveloper, CodeReviewer, "
            "SecurityAuditor, Copywriter, Editor, Synthesizer, ResearchReviewer, "
            "LegalReviewer, PM, SkillExtractor, MetaDecomposer). Spécialisé code "
            "pour la guilde Engineering, mais reste capable sur du texte structuré."
        ),
    )
    model_bulk: str = Field(
        "qwen2.5:14b",
        description=(
            "Modèle pour tâches volumineuses simples (TechWatch findings). "
            "Plus rapide / moins gourmand que les 32B."
        ),
    )

    # --- Limites & garde-fous ---
    # Backend local = coût USD = 0. Le BudgetController devient no-op si
    # daily_budget_usd <= 0 (cf. src/core/budget.py). On garde la mécanique en
    # place pour pouvoir re-câbler un cap en tokens/temps plus tard sans
    # toucher le wiring.
    daily_budget_usd: float = Field(
        0.0, ge=0, description="Plafond budget quotidien en USD (0 = désactivé, défaut Ollama)"
    )
    max_agent_turns: int = Field(20, ge=1, description="Nombre max de tours par agent")
    max_concurrent_agents: int = Field(5, ge=1, description="Agents concurrents max")
    circuit_breaker_error_rate: float = Field(
        0.3, ge=0, le=1, description="Seuil d'erreur déclenchant le circuit breaker"
    )
    # Quality Guardian (Sprint YY) — peer review méta cross-guilde. Opt-in.
    # En mode Ollama c'est gratuit donc l'argument coût ne joue plus, mais
    # ça reste un appel LLM supplémentaire qui rallonge la mission de ~30-60s.
    enable_quality_guardian: bool = Field(
        False,
        description="Active le QG après chaque mission guilde (alignement promesse↔livraison)",
    )
    # Security Auditor (Sprint AAA) — audit OWASP / secrets / pratiques sécu
    # défensives sur les missions Engineering APPROVED. Opt-in.
    enable_security_auditor: bool = Field(
        False,
        description="Active le SecurityAuditor après CodeReviewer pour les missions Engineering",
    )
    # LLM Classifier (v0.7.0) — désambiguïse les missions ambiguës via Qwen 14B
    # bulk. Fallback automatique sur l'héuristique mots-clés en cas d'erreur.
    # Coût : ~0.5-2 s par routage en plus. Opt-in pour rétrocompat.
    use_llm_classifier: bool = Field(
        False,
        description=(
            "Active le classifier LLM (Qwen 14B) pour le routage de guilde. "
            "Fallback automatique sur l'héuristique mots-clés si Ollama down. "
            "Recommandé pour les missions ambiguës que l'héuristique tranche mal."
        ),
    )
    # Hot-reload prompts (v0.8.0 F4) — quand True, BaseAgent re-lit son prompt
    # disque AVANT chaque appel LLM. Permet de modifier prompts/**/*.md sans
    # redémarrer Streamlit/CLI. Overhead négligeable (~10ms vs 30s+ d'appel LLM).
    # Désactivé par défaut pour rétrocompat stricte et perf en production.
    hot_reload_prompts: bool = Field(
        False,
        description=(
            "Active la relecture du prompt système à chaque appel agent. "
            "Pratique en développement pour itérer sur prompts/**/*.md sans "
            "redémarrer. Surcoût négligeable (~10ms par appel). À désactiver "
            "en production pour cohérence stricte entre agents d'une même mission."
        ),
    )
    # A/B testing prompts (v0.9.0 A2, ADR-029) — liste d'agents pour lesquels
    # PromptAB pick une variante aléatoire (déterministe par mission_id) parmi
    # les fichiers `<role>_<label>.md` trouvés dans le même dossier.
    # Format env var : "code_reviewer,software_architect" (séparé virgules).
    # Vide (défaut) = A/B désactivé partout, comportement v0.8.0 inchangé.
    ab_testing_agents: str = Field(
        "",
        description=(
            "Liste d'agents (séparés par virgules) pour lesquels l'A/B testing "
            "des variantes de prompts est activé. Ex: 'code_reviewer,software_architect'. "
            "Vide = A/B désactivé (canonique partout). Cf. ADR-029."
        ),
    )

    @property
    def ab_testing_agents_set(self) -> set[str]:
        """Parse `ab_testing_agents` (CSV) en set pour matching rapide."""
        return {a.strip() for a in self.ab_testing_agents.split(",") if a.strip()}

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
    langfuse_secret_key: str = Field("")

    # --- Sandbox ---
    sandbox_image: str = Field("python:3.12-slim")
    sandbox_network: str = Field("none")
    sandbox_timeout_seconds: int = Field(30, ge=1)
    sandbox_memory_limit: str = Field("512m")
    # Sprint GGG.1 — kill-switch explicite pour environnements sans Docker
    # ou volontairement minimaux (VPS-1 phase démarrage). Quand False, les
    # appels validate_files_in_sandbox court-circuitent : aucun build d'image
    # demandé, aucune tentative de connexion daemon, simple log warning.
    enable_sandbox: bool = Field(
        True,
        description="False = skip validation sandbox (run_mission --validate devient no-op silencieux)",
    )

    # --- VPS profile (Sprint GGG) ---
    vps_profile: Literal["", "vps1", "vps2", "vps3", "local"] = Field(
        "",
        description="Indicateur du profil hardware (vps1/vps2/vps3/local) pour diagnostic",
    )

    # --- Notifications (Sprint HHH) ---
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
