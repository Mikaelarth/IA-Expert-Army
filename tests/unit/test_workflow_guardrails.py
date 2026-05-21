"""Tests d'intégration des garde-fous Phase 6 dans Workflow."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.budget import BudgetController
from src.core.config import Settings
from src.core.killswitch import Killswitch
from src.memory.file_memory import FileMemory
from src.orchestrator.workflow import Workflow


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def _silent_llm_should_not_be_called():
    raise AssertionError("Le LLM ne devrait PAS être appelé quand un garde-fou refuse")


def _make_fake_openai_client(create_mock: AsyncMock) -> SimpleNamespace:
    """Construit un faux AsyncOpenAI : client.chat.completions.create(...)."""
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
    )


def test_workflow_aborts_when_killswitch_engaged(
    settings: Settings, memory: FileMemory, tmp_path: Path
) -> None:
    ks = Killswitch(tmp_path / ".killswitch")
    ks.engage(reason="test")

    wf = Workflow(memory=memory, settings=settings, killswitch=ks)
    # Sabote tous les agents pour vérifier qu'ils ne sont JAMAIS appelés
    for agent in (wf.orchestrator, wf.architect, wf.developer, wf.reviewer):
        agent.client = _make_fake_openai_client(  # type: ignore[assignment]
            AsyncMock(side_effect=_silent_llm_should_not_be_called)
        )

    result = asyncio.run(wf.run(title="t", description="d"))
    assert result.success is False
    assert "killswitch" in result.final_verdict.lower()
    assert result.episodes_count == 0


def test_workflow_aborts_when_budget_exceeded(
    settings: Settings, memory: FileMemory, tmp_path: Path
) -> None:
    state = tmp_path / "budget.json"
    bc = BudgetController(state_path=state, daily_budget_usd=1.0)
    bc.record(1.0)  # plein

    wf = Workflow(memory=memory, settings=settings, budget=bc)
    for agent in (wf.orchestrator, wf.architect, wf.developer, wf.reviewer):
        agent.client = _make_fake_openai_client(  # type: ignore[assignment]
            AsyncMock(side_effect=_silent_llm_should_not_be_called)
        )

    result = asyncio.run(wf.run(title="t", description="d"))
    assert result.success is False
    assert "budget" in result.final_verdict.lower()


def test_workflow_completes_successfully_with_zero_cost_local(
    settings: Settings, memory: FileMemory, tmp_path: Path
) -> None:
    """Bascule Ollama (ADR-025) : un workflow réussi a un cost_usd = 0 (local).
    Le BudgetController existe toujours mais ne récolte rien (workflow.py ligne
    303 ne record() que si total_cost > 0). Le test vérifie qu'un succès complet
    reste fonctionnel en cost-zero — le garde-fou budget n'est pas neutralisé
    structurellement, juste non sollicité."""
    state = tmp_path / "budget.json"
    bc = BudgetController(state_path=state, daily_budget_usd=10.0)

    wf = Workflow(memory=memory, settings=settings, budget=bc)

    # Mock chaque agent pour retourner des sorties qui font progresser le workflow
    fake_orch = _fake_response("decomposition: []", in_tokens=100, out_tokens=50)
    fake_arch = _fake_response("understanding: ok", in_tokens=200, out_tokens=100)
    fake_dev = _fake_response("## Approche\nfini", in_tokens=300, out_tokens=150)
    fake_review = _fake_response(
        "```yaml\nverdict: APPROVED\nquality_score: 0.95\nsummary: OK\n```",
        in_tokens=400,
        out_tokens=200,
    )

    wf.orchestrator.client = _make_fake_openai_client(AsyncMock(return_value=fake_orch))  # type: ignore[assignment]
    wf.architect.client = _make_fake_openai_client(AsyncMock(return_value=fake_arch))  # type: ignore[assignment]
    wf.developer.client = _make_fake_openai_client(AsyncMock(return_value=fake_dev))  # type: ignore[assignment]
    wf.reviewer.client = _make_fake_openai_client(AsyncMock(return_value=fake_review))  # type: ignore[assignment]

    result = asyncio.run(wf.run(title="test mission", description="test"))
    assert result.success is True
    # Backend local : cost USD = 0 (estimate_cost retourne toujours 0 - ADR-025)
    assert result.total_cost_usd == 0.0
    # Donc le BudgetController n'est pas sollicité (ligne 303 du workflow)
    assert bc.spent_today == 0.0


def _fake_response(text: str, in_tokens: int, out_tokens: int):
    """Shape OpenAI/Ollama : chat.completions.create response."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=in_tokens, completion_tokens=out_tokens),
        model="qwen2.5-coder:32b",
    )
