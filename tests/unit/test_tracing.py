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
