"""Tests pour src.orchestrator.base_agent — Claude est mocké."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import Settings
from src.memory.file_memory import FileMemory
from src.orchestrator.base_agent import AgentInput, BaseAgent


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


@pytest.fixture
def prompt_file(tmp_path: Path) -> Path:
    p = tmp_path / "prompt.md"
    p.write_text(
        "---\nagent: test_agent\nversion: 0.1.0\n---\n\n# Test agent\n\nTu es un agent de test.\n",
        encoding="utf-8",
    )
    return p


def _fake_response(
    text: str,
    in_tokens: int = 50,
    out_tokens: int = 30,
    stop_reason: str = "end_turn",
) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=in_tokens, output_tokens=out_tokens),
        model="claude-sonnet-4-6",
        stop_reason=stop_reason,
    )


@pytest.mark.asyncio
async def test_base_agent_runs_and_records_episode(
    settings: Settings, memory: FileMemory, prompt_file: Path
) -> None:
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=_fake_response("hello")))
    )

    agent = BaseAgent(
        name="test_agent",
        prompt_path=prompt_file,
        model="claude-sonnet-4-6",
        memory=memory,
        settings=settings,
        client=fake_client,  # type: ignore[arg-type]
    )

    mid = uuid4()
    out = await agent.run(AgentInput(mission_id=mid, task="dis bonjour"))

    assert out.success is True
    assert out.raw_text == "hello"
    assert out.tokens_in == 50
    assert out.tokens_out == 30
    assert out.cost_usd > 0

    episodes = memory.list_episodes(mid)
    assert len(episodes) == 1


@pytest.mark.asyncio
async def test_base_agent_handles_failure(
    settings: Settings, memory: FileMemory, prompt_file: Path
) -> None:
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("API down")))
    )
    agent = BaseAgent(
        name="failing_agent",
        prompt_path=prompt_file,
        model="claude-sonnet-4-6",
        memory=memory,
        settings=settings,
        client=fake_client,  # type: ignore[arg-type]
    )

    mid = uuid4()
    out = await agent.run(AgentInput(mission_id=mid, task="impossible"))

    assert out.success is False
    assert "API down" in (out.error or "")
    # L'épisode est tout de même journalisé (traçabilité)
    assert len(memory.list_episodes(mid)) == 1


def test_base_agent_loads_prompt_body_only(
    settings: Settings, memory: FileMemory, prompt_file: Path
) -> None:
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock()))
    agent = BaseAgent(
        name="x",
        prompt_path=prompt_file,
        model="claude-sonnet-4-6",
        memory=memory,
        settings=settings,
        client=fake_client,  # type: ignore[arg-type]
    )
    assert "Test agent" in agent.system_prompt
    assert "agent: test_agent" not in agent.system_prompt  # frontmatter stripped


def test_base_agent_user_message_includes_context(
    settings: Settings, memory: FileMemory, prompt_file: Path
) -> None:
    agent = BaseAgent(
        name="x",
        prompt_path=prompt_file,
        model="claude-sonnet-4-6",
        memory=memory,
        settings=settings,
        client=SimpleNamespace(messages=SimpleNamespace(create=AsyncMock())),  # type: ignore[arg-type]
    )
    msg = agent.build_user_message(
        AgentInput(mission_id=uuid4(), task="faire X", context={"input_y": "valeur Y"})
    )
    assert "faire X" in msg
    assert "input_y" in msg
    assert "valeur Y" in msg


@pytest.mark.asyncio
async def test_base_agent_marks_saturation_when_stop_reason_is_max_tokens(
    settings: Settings, memory: FileMemory, prompt_file: Path
) -> None:
    """L'API dit explicitement stop_reason='max_tokens' → saturated=True + warning loggé."""
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(
                return_value=_fake_response(
                    "réponse tronquée", in_tokens=100, out_tokens=2048, stop_reason="max_tokens"
                )
            )
        )
    )
    agent = BaseAgent(
        name="x",
        prompt_path=prompt_file,
        model="claude-sonnet-4-6",
        memory=memory,
        settings=settings,
        client=fake_client,  # type: ignore[arg-type]
        max_tokens=2048,
    )
    out = await agent.run(AgentInput(mission_id=uuid4(), task="t"))
    assert out.success is True
    assert out.saturated is True
    assert out.stop_reason == "max_tokens"

    # Le metadata persiste l'info pour analyse post-mortem
    last_path = sorted(memory.list_episodes())[-1]
    record = memory.read_episode(last_path)
    assert record.metadata.get("saturated") is True


@pytest.mark.asyncio
async def test_base_agent_marks_saturation_at_token_threshold(
    settings: Settings, memory: FileMemory, prompt_file: Path
) -> None:
    """Garde-fou : tokens_out ≥ 99% de max_tokens → saturated=True même si stop_reason=end_turn."""
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(
                return_value=_fake_response(
                    "ok", in_tokens=100, out_tokens=2048, stop_reason="end_turn"
                )
            )
        )
    )
    agent = BaseAgent(
        name="x",
        prompt_path=prompt_file,
        model="claude-sonnet-4-6",
        memory=memory,
        settings=settings,
        client=fake_client,  # type: ignore[arg-type]
        max_tokens=2048,
    )
    out = await agent.run(AgentInput(mission_id=uuid4(), task="t"))
    assert out.saturated is True


@pytest.mark.asyncio
async def test_base_agent_no_saturation_on_normal_completion(
    settings: Settings, memory: FileMemory, prompt_file: Path
) -> None:
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(
                return_value=_fake_response(
                    "ok", in_tokens=100, out_tokens=200, stop_reason="end_turn"
                )
            )
        )
    )
    agent = BaseAgent(
        name="x",
        prompt_path=prompt_file,
        model="claude-sonnet-4-6",
        memory=memory,
        settings=settings,
        client=fake_client,  # type: ignore[arg-type]
        max_tokens=2048,
    )
    out = await agent.run(AgentInput(mission_id=uuid4(), task="t"))
    assert out.saturated is False
    assert out.stop_reason == "end_turn"


def test_detect_saturation_explicit_signal() -> None:
    """Unit test direct du critère de détection."""
    assert BaseAgent._detect_saturation(BaseAgent, 100, 2048, "max_tokens") is True


def test_detect_saturation_token_ratio_above_threshold() -> None:
    # 99% de 2048 = 2027.52 → arrondi int = 2027 → 2030 >= 2027 → True
    assert BaseAgent._detect_saturation(BaseAgent, 2030, 2048, "end_turn") is True


def test_detect_saturation_below_threshold_returns_false() -> None:
    assert BaseAgent._detect_saturation(BaseAgent, 1500, 2048, "end_turn") is False


def test_detect_saturation_zero_max_tokens_handled() -> None:
    """Edge case : max_tokens=0 ne doit pas crash (division par zéro évitée)."""
    assert BaseAgent._detect_saturation(BaseAgent, 0, 0, "end_turn") is False


# ===== Sprint VV.1 — Retry/backoff explicite =====


def test_base_agent_default_client_uses_settings_retry_config(
    settings: Settings, memory: FileMemory, prompt_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quand on n'injecte pas de client, BaseAgent doit configurer AsyncAnthropic
    avec max_retries et timeout depuis Settings (pas les défauts SDK silencieux)."""
    captured: dict = {}

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.messages = SimpleNamespace(create=AsyncMock())

    monkeypatch.setattr("src.orchestrator.base_agent.AsyncAnthropic", _FakeAsyncAnthropic)

    BaseAgent(
        name="x",
        prompt_path=prompt_file,
        model="claude-sonnet-4-6",
        memory=memory,
        settings=settings,
    )

    assert "max_retries" in captured, "BaseAgent doit passer max_retries au client"
    assert captured["max_retries"] == settings.anthropic_max_retries
    assert "timeout" in captured
    assert captured["timeout"] == settings.anthropic_timeout_seconds
    assert captured["api_key"] == "sk-ant-test-12345"


def test_settings_anthropic_retry_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les défauts retry/timeout doivent être raisonnables (pas 0, pas 600)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.anthropic_max_retries == 2
    assert s.anthropic_timeout_seconds == 300.0


def test_settings_anthropic_retry_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    monkeypatch.setenv("ANTHROPIC_MAX_RETRIES", "4")
    monkeypatch.setenv("ANTHROPIC_TIMEOUT_SECONDS", "60")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.anthropic_max_retries == 4
    assert s.anthropic_timeout_seconds == 60.0


def test_settings_anthropic_max_retries_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_retries doit être borné à [0, 5] (sinon retry storm en cas de 5xx persistant)."""
    from pydantic import ValidationError

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    monkeypatch.setenv("ANTHROPIC_MAX_RETRIES", "99")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_base_agent_rag_injects_precedents_and_indexes(
    settings: Settings, memory: FileMemory, prompt_file: Path, tmp_path: Path
) -> None:
    """Phase 2 : si VectorMemory est fourni, les précédents sont injectés au prompt
    ET la nouvelle exécution est indexée pour les futures requêtes."""
    from src.memory.vector_memory import VectorMemory

    vmem = VectorMemory(persist_dir=tmp_path / "chroma_int")
    # Pré-charge un précédent qui matchera sémantiquement la tâche
    vmem.add_episode(
        "precedent_1",
        "Tâche: Implémenter un endpoint healthcheck FastAPI\n\nSortie:\nrouter avec @router.get('/health')",
        {
            "agent": "test_agent_rag",
            "success": True,
            "quality_score": 0.95,
            "mission_title": "Endpoint /health",
        },
    )

    captured_messages: list[str] = []

    async def capture(*args, **kwargs):
        captured_messages.append(kwargs["messages"][0]["content"])
        return _fake_response("réponse de test", in_tokens=100, out_tokens=50)

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=capture)))

    agent = BaseAgent(
        name="test_agent_rag",
        prompt_path=prompt_file,
        model="claude-sonnet-4-6",
        memory=memory,
        settings=settings,
        client=fake_client,  # type: ignore[arg-type]
        vector_memory=vmem,
        rag_max_distance=2.0,  # large pour garantir que le précédent passe en test
    )

    out = await agent.run(
        AgentInput(mission_id=uuid4(), task="Crée un endpoint REST de santé pour mon API")
    )
    assert out.success is True
    # Le user_message envoyé à Claude doit contenir la section "Précédents pertinents"
    assert len(captured_messages) == 1
    assert "Précédents pertinents" in captured_messages[0]
    assert "Endpoint /health" in captured_messages[0]
    # Le nouvel épisode doit avoir été indexé
    assert vmem.count() == 2
