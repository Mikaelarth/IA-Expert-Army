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


def _fake_response(text: str, in_tokens: int = 50, out_tokens: int = 30) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=in_tokens, output_tokens=out_tokens),
        model="claude-sonnet-4-6",
        stop_reason="end_turn",
    )


@pytest.mark.asyncio
async def test_base_agent_runs_and_records_episode(
    settings: Settings, memory: FileMemory, prompt_file: Path
) -> None:
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=_fake_response("hello"))))

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
