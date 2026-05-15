"""Tests pour src.core.tracing — graceful degradation sans Langfuse credentials."""

from __future__ import annotations

import pytest

from src.core import tracing


@pytest.fixture(autouse=True)
def _reset_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset state module-level avant chaque test."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    tracing.reset_for_tests()


def test_init_tracing_disabled_when_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    # Force la lecture des settings frais
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    enabled = tracing.init_tracing()
    assert enabled is False


def test_init_tracing_disabled_with_force_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    enabled = tracing.init_tracing(force_disable=True)
    assert enabled is False


def test_observe_is_noop_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans credentials, @observe doit passer la fonction inchangée."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    @tracing.observe(name="test")
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5
    assert add(10, 20) == 30


def test_observe_works_without_parentheses(monkeypatch: pytest.MonkeyPatch) -> None:
    """@observe sans () (sur une fonction directement) doit aussi marcher en NO-OP."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    @tracing.observe
    def hello() -> str:
        return "world"

    assert hello() == "world"


def test_observe_preserves_function_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    """@functools.wraps doit conserver __name__ et __doc__."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    @tracing.observe(name="my_func")
    def my_func() -> int:
        """Cette docstring doit être préservée."""
        return 42

    assert my_func.__name__ == "my_func"
    assert "Cette docstring" in (my_func.__doc__ or "")
    assert my_func() == 42


def test_observe_works_on_async_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le NO-OP doit aussi marcher sur les coroutines (BaseAgent.run est async)."""
    import asyncio

    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    @tracing.observe(name="async_test")
    async def async_double(x: int) -> int:
        return x * 2

    result = asyncio.run(async_double(21))
    assert result == 42


def test_init_tracing_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Appeler init_tracing() plusieurs fois ne doit pas re-init / casser."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    first = tracing.init_tracing()
    second = tracing.init_tracing()
    third = tracing.init_tracing()
    assert first == second == third  # status stable


def test_observe_lazy_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """observe() peut être utilisé avant init_tracing() explicite — il init lazy."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    # Pas d'init_tracing() préalable
    @tracing.observe(name="lazy")
    def f(x: int) -> int:
        return x + 1

    assert f(10) == 11
    # init_tracing a été appelé en interne
    assert tracing._initialized is True


def test_reset_for_tests_clears_state() -> None:
    tracing._initialized = True
    tracing._langfuse_available = True
    tracing.reset_for_tests()
    assert tracing._initialized is False
    assert tracing._langfuse_available is False


# ============================================================================
# Sprint JJJ.3a — couverture du chemin Langfuse ACTIF (jamais testé avant)
# ============================================================================
# Avant ce sprint, on n'avait que le path no-op (pas de credentials).
# Le path actif (credentials + SDK importable + observe forward) restait à
# 0% de couverture. On le simule en mockant _try_import_langfuse +
# l'import dynamique de la classe Langfuse.


def _fake_langfuse_observe_decorator(*decorator_args, **decorator_kwargs):
    """Décorateur de mock qui marque les fonctions appelées."""
    if decorator_args and callable(decorator_args[0]) and not decorator_kwargs:
        # @observe sans () : args[0] est la fonction
        fn = decorator_args[0]
        fn._langfuse_decorated = True  # type: ignore[attr-defined]
        return fn

    def decorator(func):
        func._langfuse_decorated = True  # type: ignore[attr-defined]
        return func

    return decorator


def test_init_tracing_active_when_credentials_present_and_sdk_importable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sprint JJJ.3a : path actif jamais testé. Mock SDK Langfuse présent +
    credentials → init_tracing doit renvoyer True et marquer _langfuse_available."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test-12345")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test-67890")
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    # Mock _try_import_langfuse pour simuler "SDK présent"
    monkeypatch.setattr(
        tracing,
        "_try_import_langfuse",
        lambda: (True, _fake_langfuse_observe_decorator),
    )

    # Mock l'import dynamique de Langfuse class — on remplace le module
    # `langfuse` dans sys.modules pour simuler v4.
    import sys

    fake_langfuse_module = type(sys)("langfuse")
    fake_langfuse_module.Langfuse = type(  # type: ignore[attr-defined]
        "MockLangfuse",
        (),
        {"__init__": lambda self, **kw: None},
    )
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse_module)

    enabled = tracing.init_tracing()
    assert enabled is True, "init_tracing doit retourner True quand credentials + SDK présents"
    assert tracing._langfuse_available is True
    assert tracing._real_observe is _fake_langfuse_observe_decorator


def test_observe_forwards_to_langfuse_when_active(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sprint JJJ.3a : si Langfuse actif, observe doit appeler le décorateur
    Langfuse réel (et pas le no-op)."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    monkeypatch.setattr(
        tracing,
        "_try_import_langfuse",
        lambda: (True, _fake_langfuse_observe_decorator),
    )
    import sys

    fake_module = type(sys)("langfuse")
    fake_module.Langfuse = type("L", (), {"__init__": lambda self, **kw: None})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", fake_module)

    tracing.init_tracing()

    @tracing.observe(name="my_traced")
    def fn() -> int:
        return 42

    assert fn() == 42
    # Notre fake décorateur marque la fonction
    assert getattr(fn, "_langfuse_decorated", False) is True


def test_init_tracing_disabled_when_credentials_present_but_sdk_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si credentials présents mais SDK Langfuse absent (pas pip-installé) →
    désactivé proprement, pas de crash."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    # SDK absent → _try_import_langfuse renvoie (False, None)
    monkeypatch.setattr(tracing, "_try_import_langfuse", lambda: (False, None))

    enabled = tracing.init_tracing()
    assert enabled is False


def test_init_tracing_handles_langfuse_init_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si Langfuse(...).__init__ lève (config réseau invalide, etc.) → log warning,
    pas de crash, retourne False. Couvre le except Exception ligne 113-115."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    monkeypatch.setattr(
        tracing,
        "_try_import_langfuse",
        lambda: (True, _fake_langfuse_observe_decorator),
    )

    import sys

    class _RaisingLangfuse:
        def __init__(self, **kw):
            raise RuntimeError("simulated init failure (e.g. network)")

    fake_module = type(sys)("langfuse")
    fake_module.Langfuse = _RaisingLangfuse  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", fake_module)

    enabled = tracing.init_tracing()
    assert enabled is False


def test_init_tracing_v3_fallback_when_langfuse_class_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Couvre le fallback Langfuse v2/v3 ligne 110-112 : si l'import de la classe
    Langfuse échoue (TypeError ou ImportError), on passe en mode env-vars-only
    et l'instrumentation reste active."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    monkeypatch.setattr(
        tracing,
        "_try_import_langfuse",
        lambda: (True, _fake_langfuse_observe_decorator),
    )

    import sys

    # Crée un module sans attribut Langfuse → AttributeError au moment de
    # `from langfuse import Langfuse`. Le code catch ImportError seulement
    # dans le try (ligne 102-110). Pour couvrir le path TypeError/ImportError,
    # on supprime la classe.
    fake_module = type(sys)("langfuse")
    # Pas d'attribut Langfuse → ImportError attendu
    monkeypatch.setitem(sys.modules, "langfuse", fake_module)

    enabled = tracing.init_tracing()
    # Sans la classe Langfuse, le import échoue avec ImportError.
    # Le code catch (ImportError, TypeError) → pass → retourne True quand même
    # car _langfuse_available est mis à True après le try.
    assert enabled is True
