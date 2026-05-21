"""Tests pour src.orchestrator.base_agent — le client LLM (Ollama) est mocké.

Bascule v0.4.0 (ADR-025) : le shape mocké est celui d'AsyncOpenAI/Ollama.
Différences vs Anthropic :
- `client.chat.completions.create(...)` (pas `client.messages.create`)
- `response.choices[0].message.content` (pas `response.content[0].text`)
- `usage.prompt_tokens` / `usage.completion_tokens` (pas `input_tokens` / `output_tokens`)
- `finish_reason="length"` (pas `stop_reason="max_tokens"`)
- `system` passe comme premier message `{"role": "system", ...}` (pas en param)
"""

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
def settings() -> Settings:
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
    finish_reason: str = "stop",
) -> SimpleNamespace:
    """Fake d'une ChatCompletion OpenAI (le shape qu'Ollama renvoie)."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text),
                finish_reason=finish_reason,
            )
        ],
        usage=SimpleNamespace(prompt_tokens=in_tokens, completion_tokens=out_tokens),
        model="qwen2.5-coder:32b",
    )


def _make_fake_client(create_mock: AsyncMock) -> SimpleNamespace:
    """Construit un faux AsyncOpenAI : client.chat.completions.create(...)."""
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock)))


@pytest.mark.asyncio
async def test_base_agent_runs_and_records_episode(
    settings: Settings, memory: FileMemory, prompt_file: Path
) -> None:
    fake_client = _make_fake_client(AsyncMock(return_value=_fake_response("hello")))

    agent = BaseAgent(
        name="test_agent",
        prompt_path=prompt_file,
        model="qwen2.5-coder:32b",
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
    # Coût = 0 (backend local Ollama, pricing à 0 par défaut)
    assert out.cost_usd == 0.0

    episodes = memory.list_episodes(mid)
    assert len(episodes) == 1


@pytest.mark.asyncio
async def test_base_agent_handles_failure(
    settings: Settings, memory: FileMemory, prompt_file: Path
) -> None:
    fake_client = _make_fake_client(AsyncMock(side_effect=RuntimeError("API down")))
    agent = BaseAgent(
        name="failing_agent",
        prompt_path=prompt_file,
        model="qwen2.5-coder:32b",
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
    fake_client = _make_fake_client(AsyncMock())
    agent = BaseAgent(
        name="x",
        prompt_path=prompt_file,
        model="qwen2.5-coder:32b",
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
        model="qwen2.5-coder:32b",
        memory=memory,
        settings=settings,
        client=_make_fake_client(AsyncMock()),  # type: ignore[arg-type]
    )
    msg = agent.build_user_message(
        AgentInput(mission_id=uuid4(), task="faire X", context={"input_y": "valeur Y"})
    )
    assert "faire X" in msg
    assert "input_y" in msg
    assert "valeur Y" in msg


@pytest.mark.asyncio
async def test_base_agent_marks_saturation_when_finish_reason_is_length(
    settings: Settings, memory: FileMemory, prompt_file: Path
) -> None:
    """L'API dit explicitement finish_reason='length' → saturated=True + warning loggé."""
    fake_client = _make_fake_client(
        AsyncMock(
            return_value=_fake_response(
                "réponse tronquée", in_tokens=100, out_tokens=2048, finish_reason="length"
            )
        )
    )
    agent = BaseAgent(
        name="x",
        prompt_path=prompt_file,
        model="qwen2.5-coder:32b",
        memory=memory,
        settings=settings,
        client=fake_client,  # type: ignore[arg-type]
        max_tokens=2048,
    )
    out = await agent.run(AgentInput(mission_id=uuid4(), task="t"))
    assert out.success is True
    assert out.saturated is True
    assert out.stop_reason == "length"

    # Le metadata persiste l'info pour analyse post-mortem
    last_path = sorted(memory.list_episodes())[-1]
    record = memory.read_episode(last_path)
    assert record.metadata.get("saturated") is True


@pytest.mark.asyncio
async def test_base_agent_marks_saturation_at_token_threshold(
    settings: Settings, memory: FileMemory, prompt_file: Path
) -> None:
    """Garde-fou : tokens_out ≥ 99% de max_tokens → saturated=True même si finish_reason=stop."""
    fake_client = _make_fake_client(
        AsyncMock(
            return_value=_fake_response("ok", in_tokens=100, out_tokens=2048, finish_reason="stop")
        )
    )
    agent = BaseAgent(
        name="x",
        prompt_path=prompt_file,
        model="qwen2.5-coder:32b",
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
    fake_client = _make_fake_client(
        AsyncMock(
            return_value=_fake_response("ok", in_tokens=100, out_tokens=200, finish_reason="stop")
        )
    )
    agent = BaseAgent(
        name="x",
        prompt_path=prompt_file,
        model="qwen2.5-coder:32b",
        memory=memory,
        settings=settings,
        client=fake_client,  # type: ignore[arg-type]
        max_tokens=2048,
    )
    out = await agent.run(AgentInput(mission_id=uuid4(), task="t"))
    assert out.saturated is False
    assert out.stop_reason == "stop"


def test_detect_saturation_explicit_signal() -> None:
    """Unit test direct du critère de détection."""
    assert BaseAgent._detect_saturation(BaseAgent, 100, 2048, "length") is True


def test_detect_saturation_token_ratio_above_threshold() -> None:
    # 99% de 2048 = 2027.52 → arrondi int = 2027 → 2030 >= 2027 → True
    assert BaseAgent._detect_saturation(BaseAgent, 2030, 2048, "stop") is True


def test_detect_saturation_below_threshold_returns_false() -> None:
    assert BaseAgent._detect_saturation(BaseAgent, 1500, 2048, "stop") is False


def test_detect_saturation_zero_max_tokens_handled() -> None:
    """Edge case : max_tokens=0 ne doit pas crash (division par zéro évitée)."""
    assert BaseAgent._detect_saturation(BaseAgent, 0, 0, "stop") is False


# ===== Sprint VV.1 — Retry/backoff explicite (ADR-025 : Ollama) =====


def test_base_agent_default_client_uses_settings_retry_config(
    settings: Settings, memory: FileMemory, prompt_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quand on n'injecte pas de client, BaseAgent doit configurer AsyncOpenAI
    avec base_url, max_retries et timeout depuis Settings (pas les défauts SDK silencieux)."""
    captured: dict = {}

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=AsyncMock()))

    monkeypatch.setattr("src.orchestrator.base_agent.AsyncOpenAI", _FakeAsyncOpenAI)

    BaseAgent(
        name="x",
        prompt_path=prompt_file,
        model="qwen2.5-coder:32b",
        memory=memory,
        settings=settings,
    )

    assert captured["base_url"] == settings.ollama_base_url
    assert captured["api_key"] == settings.ollama_api_key
    assert captured["max_retries"] == settings.ollama_max_retries
    assert captured["timeout"] == settings.ollama_timeout_seconds


def test_settings_ollama_retry_defaults() -> None:
    """Les défauts retry/timeout doivent être raisonnables."""
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.ollama_max_retries == 2
    assert s.ollama_timeout_seconds == 600.0
    assert s.ollama_base_url == "http://localhost:11434/v1"


def test_settings_ollama_retry_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MAX_RETRIES", "4")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "60")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.ollama_max_retries == 4
    assert s.ollama_timeout_seconds == 60.0


def test_settings_ollama_max_retries_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_retries doit être borné à [0, 5] (sinon retry storm en cas d'erreur persistante)."""
    from pydantic import ValidationError

    monkeypatch.setenv("OLLAMA_MAX_RETRIES", "99")
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
        # Shape OpenAI : messages=[{"role":"system",...}, {"role":"user",...}]
        # On capture le contenu user (index 1).
        captured_messages.append(kwargs["messages"][1]["content"])
        return _fake_response("réponse de test", in_tokens=100, out_tokens=50)

    fake_client = _make_fake_client(AsyncMock(side_effect=capture))

    agent = BaseAgent(
        name="test_agent_rag",
        prompt_path=prompt_file,
        model="qwen2.5-coder:32b",
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
    # Le user_message envoyé au LLM doit contenir la section "Précédents pertinents"
    assert len(captured_messages) == 1
    assert "Précédents pertinents" in captured_messages[0]
    assert "Endpoint /health" in captured_messages[0]
    # Le nouvel épisode doit avoir été indexé
    assert vmem.count() == 2
