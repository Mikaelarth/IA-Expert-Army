"""Tracing — instrumentation Langfuse opt-in pour les agents et workflows.

L'instrumentation est OPT-IN via les variables d'environnement :
- LANGFUSE_PUBLIC_KEY=pk-lf-...
- LANGFUSE_SECRET_KEY=sk-lf-...
- LANGFUSE_HOST=http://localhost:3000  (ou cloud.langfuse.com)

Si l'une est absente, le décorateur `@observe()` exposé ici est un NO-OP
silencieux : aucun trace n'est envoyé et aucune exception n'est levée. Le
système fonctionne identiquement avec ou sans Langfuse — l'instrumentation
ne crée jamais de hard dependency runtime.

Usage type :
    from src.core.tracing import observe, init_tracing

    init_tracing()  # à faire une fois au démarrage du process

    class BaseAgent:
        @observe(name="agent.run")
        async def run(self, agent_input):
            ...
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from typing_extensions import ParamSpec

from src.core.config import get_settings
from src.core.logging import get_logger

_log = get_logger("tracing")

P = ParamSpec("P")
R = TypeVar("R")

_initialized = False
_langfuse_available = False
_real_observe: Callable[..., Any] | None = None


def _try_import_langfuse() -> tuple[bool, Callable[..., Any] | None]:
    """Importe Langfuse de manière défensive.

    Renvoie (available, observe_decorator). Si Langfuse SDK n'est pas
    installé, on renvoie (False, None) sans crasher l'import du module.
    """
    # Langfuse v4 a déplacé observe de langfuse.decorators vers langfuse.
    # On résout dynamiquement pour supporter les deux générations sans
    # déclencher no-redef de mypy (les deux imports portent le même nom).
    lf_observe: Callable[..., Any] | None = None
    try:
        try:
            import langfuse as _lf_v4

            lf_observe = _lf_v4.observe
        except (ImportError, AttributeError):
            from langfuse.decorators import observe as _lf_v3_observe

            lf_observe = _lf_v3_observe
        return True, lf_observe
    except ImportError:
        return False, None


def init_tracing(force_disable: bool = False) -> bool:
    """Initialise Langfuse si les credentials sont présents.

    Renvoie True si l'instrumentation est ACTIVE (= Langfuse SDK importable
    + credentials non vides + force_disable=False). Sinon False.

    Sûr à appeler plusieurs fois — l'init Langfuse est idempotente.
    """
    global _initialized, _langfuse_available, _real_observe

    if _initialized:
        return _langfuse_available

    _initialized = True

    if force_disable:
        _log.info("tracing.disabled", reason="force_disable=True")
        return False

    settings = get_settings()
    public_key = settings.langfuse_public_key
    # Bascule v0.4.0 : langfuse_secret_key est désormais un str simple (plus
    # SecretStr) — Ollama local n'a plus besoin du même niveau de protection
    # secret et ça aligne les autres clés string (ollama_api_key, etc.).
    secret_key = settings.langfuse_secret_key

    if not public_key or not secret_key:
        _log.info(
            "tracing.disabled",
            reason="missing_credentials",
            advice="Set LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY in .env to enable",
        )
        return False

    available, observe_decorator = _try_import_langfuse()
    if not available:
        _log.warning("tracing.disabled", reason="langfuse_sdk_not_installed")
        return False

    # Langfuse v4 : initialisation explicite via Langfuse(...)
    try:
        try:
            from langfuse import Langfuse

            Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=settings.langfuse_host,
            )
        except (ImportError, TypeError):
            # Langfuse v2/v3 : les env vars suffisent (LANGFUSE_HOST déjà lu par le SDK)
            pass
    except Exception as exc:
        _log.warning("tracing.init_failed", error=str(exc))
        return False

    _langfuse_available = True
    _real_observe = observe_decorator
    _log.info("tracing.enabled", host=settings.langfuse_host, public_key_prefix=public_key[:8])
    return True


def _noop_observe(
    *decorator_args: Any, **decorator_kwargs: Any
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Décorateur NO-OP qui passe la fonction inchangée.

    Compatible avec les deux usages :
        @observe                       # sans parenthèses
        @observe(name="...", ...)      # avec arguments
    """
    # Cas usage sans parenthèses : @observe direct sur une fonction
    if len(decorator_args) == 1 and callable(decorator_args[0]) and not decorator_kwargs:
        from typing import cast

        return cast(Callable[[Callable[P, R]], Callable[P, R]], decorator_args[0])

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            return func(*args, **kwargs)

        return wrapper

    return decorator


def observe(*args: Any, **kwargs: Any) -> Any:
    """Décorateur de tracing : forward vers Langfuse si actif, sinon NO-OP.

    Initialise Langfuse de manière paresseuse au premier usage. Ainsi un
    module qui importe `observe` au top-level ne déclenche pas l'init avant
    que le code applicatif ait eu le temps d'appeler `init_tracing()` ou
    de lire la config.
    """
    if not _initialized:
        init_tracing()

    if _langfuse_available and _real_observe is not None:
        return _real_observe(*args, **kwargs)
    return _noop_observe(*args, **kwargs)


def reset_for_tests() -> None:
    """Réinitialise l'état module-level. Réservé aux tests unit."""
    global _initialized, _langfuse_available, _real_observe
    _initialized = False
    _langfuse_available = False
    _real_observe = None
