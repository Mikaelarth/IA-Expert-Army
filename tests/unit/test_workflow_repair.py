"""Tests régression du repair loop Workflow (Engineering).

Couvre la fix Sprint SS (2026-05-11) : quand le Reviewer verdict est
NEEDS_CHANGES, le repair loop doit ré-exécuter Architect + Developer +
Reviewer, pas seulement le Developer comme la v1.

Pattern méta-leçon dérivé de Sprint PP (BusinessWorkflow) : un repair
loop qui ne touche qu'un sous-ensemble des producteurs upstream crée
des conditions d'oscillation. Si le Reviewer flagge un problème
d'architecture (mauvaise abstraction, faille design), le Developer
seul ne peut pas le corriger car sa proposition d'archi est figée.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.config import Settings
from src.memory.file_memory import FileMemory
from src.orchestrator.base_agent import AgentOutput
from src.orchestrator.workflow import Workflow


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def _agent_output(
    agent_name: str,
    raw_text: str = "ok",
    parsed: object = None,
    success: bool = True,
    cost: float = 0.05,
) -> AgentOutput:
    return AgentOutput(
        agent_name=agent_name,
        mission_id=uuid4(),
        success=success,
        raw_text=raw_text,
        parsed=parsed,
        tokens_in=100,
        tokens_out=200,
        cost_usd=cost,
        duration_seconds=1.0,
    )


def _make_workflow(memory: FileMemory, settings: Settings) -> Workflow:
    """Construit un Workflow avec tous les agents remplaçables après-coup."""
    return Workflow(memory=memory, settings=settings)


@pytest.mark.asyncio
async def test_repair_loop_reruns_architect_developer_and_reviewer(
    settings: Settings, memory: FileMemory
) -> None:
    """Le repair loop sur NEEDS_CHANGES doit appeler Architect, Developer et
    Reviewer chacun DEUX fois (run initial + run de repair). C'est la fix
    Sprint SS."""
    wf = _make_workflow(memory, settings)

    orch_mock = MagicMock()
    orch_mock.run = AsyncMock(
        return_value=_agent_output(
            "chief_orchestrator", raw_text="decomp", parsed={"subtasks": [{"title": "X"}]}
        )
    )
    arch_mock = MagicMock()
    arch_mock.run = AsyncMock(
        side_effect=[
            _agent_output("software_architect", raw_text="arch v1"),
            _agent_output("software_architect", raw_text="arch v2"),
        ]
    )
    dev_mock = MagicMock()
    dev_mock.run = AsyncMock(
        side_effect=[
            _agent_output("backend_developer", raw_text="dev v1", parsed=[]),
            _agent_output("backend_developer", raw_text="dev v2", parsed=[]),
        ]
    )
    reviewer_mock = MagicMock()
    reviewer_mock.run = AsyncMock(
        side_effect=[
            _agent_output(
                "code_reviewer",
                raw_text="review v1",
                parsed={"verdict": "NEEDS_CHANGES", "summary": "Archi à revoir"},
            ),
            _agent_output(
                "code_reviewer",
                raw_text="review v2",
                parsed={"verdict": "APPROVED", "summary": "OK", "quality_score": 0.93},
            ),
        ]
    )
    wf.orchestrator = orch_mock
    wf.architect = arch_mock
    wf.developer = dev_mock
    wf.reviewer = reviewer_mock

    result = await wf.run(title="Test repair", description="Build X")

    # Orchestrator appelé 1× (pas dans le repair, c'est figé à la décomposition init)
    assert orch_mock.run.call_count == 1
    # Architect/Dev/Reviewer chacun 2× (1 initial + 1 repair)
    assert arch_mock.run.call_count == 2, (
        "Architect doit être ré-exécuté dans le repair loop (fix Sprint SS)"
    )
    assert dev_mock.run.call_count == 2
    assert reviewer_mock.run.call_count == 2

    assert result.final_verdict == "APPROVED"
    assert result.success is True


@pytest.mark.asyncio
async def test_repair_architect_receives_review_feedback_in_context(
    settings: Settings, memory: FileMemory
) -> None:
    """L'Architect v2 doit recevoir le feedback Reviewer ET l'archi initiale
    dans son contexte, sinon il n'a aucune raison de changer sa proposition."""
    wf = _make_workflow(memory, settings)

    wf.orchestrator = MagicMock()
    wf.orchestrator.run = AsyncMock(
        return_value=_agent_output(
            "chief_orchestrator", parsed={"subtasks": [{"title": "X"}]}, raw_text="d"
        )
    )
    arch_mock = MagicMock()
    arch_mock.run = AsyncMock(
        side_effect=[
            _agent_output("software_architect", raw_text="ARCH_V1_INITIAL"),
            _agent_output("software_architect", raw_text="arch v2"),
        ]
    )
    wf.architect = arch_mock
    wf.developer = MagicMock()
    wf.developer.run = AsyncMock(
        side_effect=[
            _agent_output("backend_developer", raw_text="d v1", parsed=[]),
            _agent_output("backend_developer", raw_text="d v2", parsed=[]),
        ]
    )
    wf.reviewer = MagicMock()
    wf.reviewer.run = AsyncMock(
        side_effect=[
            _agent_output(
                "code_reviewer",
                raw_text="REVIEW_FLAGS_BAD_ABSTRACTION",
                parsed={"verdict": "NEEDS_CHANGES"},
            ),
            _agent_output(
                "code_reviewer", parsed={"verdict": "APPROVED", "quality_score": 0.9}
            ),
        ]
    )

    await wf.run(title="X", description="y")

    arch_v2_call = arch_mock.run.call_args_list[1]
    arch_v2_input = arch_v2_call.args[0] if arch_v2_call.args else arch_v2_call.kwargs.get("agent_input")
    ctx = arch_v2_input.context
    assert "REVIEW_FLAGS_BAD_ABSTRACTION" in ctx.get("review_feedback_yaml", ""), (
        "Architect v2 doit recevoir le feedback Reviewer pour pouvoir réviser"
    )
    assert ctx.get("previous_architecture_yaml") == "ARCH_V1_INITIAL", (
        "Architect v2 doit voir sa propre proposition initiale pour pouvoir l'amender"
    )
    assert "previous_implementation_md" in ctx, (
        "Architect v2 doit aussi voir l'implémentation du dev v1 (contexte sur ce qui a été construit)"
    )


@pytest.mark.asyncio
async def test_repair_developer_v2_uses_updated_architecture(
    settings: Settings, memory: FileMemory
) -> None:
    """Developer v2 doit coder sur l'archi MISE À JOUR (pas l'initiale)."""
    wf = _make_workflow(memory, settings)

    wf.orchestrator = MagicMock()
    wf.orchestrator.run = AsyncMock(
        return_value=_agent_output(
            "chief_orchestrator", parsed={"subtasks": [{"title": "X"}]}, raw_text="d"
        )
    )
    wf.architect = MagicMock()
    wf.architect.run = AsyncMock(
        side_effect=[
            _agent_output("software_architect", raw_text="ARCH_V1"),
            _agent_output("software_architect", raw_text="ARCH_V2_REVISED"),
        ]
    )
    dev_mock = MagicMock()
    dev_mock.run = AsyncMock(
        side_effect=[
            _agent_output("backend_developer", raw_text="d v1", parsed=[]),
            _agent_output("backend_developer", raw_text="d v2", parsed=[]),
        ]
    )
    wf.developer = dev_mock
    wf.reviewer = MagicMock()
    wf.reviewer.run = AsyncMock(
        side_effect=[
            _agent_output("code_reviewer", parsed={"verdict": "NEEDS_CHANGES"}),
            _agent_output("code_reviewer", parsed={"verdict": "APPROVED", "quality_score": 0.9}),
        ]
    )

    await wf.run(title="X", description="y")

    dev_v2_call = dev_mock.run.call_args_list[1]
    dev_v2_input = dev_v2_call.args[0] if dev_v2_call.args else dev_v2_call.kwargs.get("agent_input")
    assert dev_v2_input.context["architecture_proposal_yaml"] == "ARCH_V2_REVISED", (
        "Developer v2 doit lire l'archi v2, pas l'initiale — sinon le repair architect ne sert à rien"
    )


@pytest.mark.asyncio
async def test_no_repair_when_initial_reviewer_approved(
    settings: Settings, memory: FileMemory
) -> None:
    """Si Reviewer APPROUVE du premier coup, AUCUN agent ne doit être ré-exécuté."""
    wf = _make_workflow(memory, settings)

    wf.orchestrator = MagicMock()
    wf.orchestrator.run = AsyncMock(
        return_value=_agent_output(
            "chief_orchestrator", parsed={"subtasks": [{"title": "X"}]}, raw_text="d"
        )
    )
    arch_mock = MagicMock()
    arch_mock.run = AsyncMock(return_value=_agent_output("software_architect"))
    wf.architect = arch_mock
    dev_mock = MagicMock()
    dev_mock.run = AsyncMock(return_value=_agent_output("backend_developer", parsed=[]))
    wf.developer = dev_mock
    reviewer_mock = MagicMock()
    reviewer_mock.run = AsyncMock(
        return_value=_agent_output(
            "code_reviewer", parsed={"verdict": "APPROVED", "quality_score": 0.95}
        )
    )
    wf.reviewer = reviewer_mock

    result = await wf.run(title="X", description="y")

    assert arch_mock.run.call_count == 1, "Architect ne doit PAS être ré-exécuté si Reviewer APPROUVE direct"
    assert dev_mock.run.call_count == 1
    assert reviewer_mock.run.call_count == 1
    assert result.final_verdict == "APPROVED"


@pytest.mark.asyncio
async def test_repair_handles_architect_v2_failure_gracefully(
    settings: Settings, memory: FileMemory
) -> None:
    """Si Architect v2 plante, le repair continue avec l'archi v1 pour le Developer
    (fallback). Le repair ne crash pas la mission entière."""
    wf = _make_workflow(memory, settings)

    wf.orchestrator = MagicMock()
    wf.orchestrator.run = AsyncMock(
        return_value=_agent_output(
            "chief_orchestrator", parsed={"subtasks": [{"title": "X"}]}, raw_text="d"
        )
    )
    wf.architect = MagicMock()
    wf.architect.run = AsyncMock(
        side_effect=[
            _agent_output("software_architect", raw_text="ARCH_V1_OK"),
            _agent_output("software_architect", raw_text="", success=False),
        ]
    )
    dev_mock = MagicMock()
    dev_mock.run = AsyncMock(
        side_effect=[
            _agent_output("backend_developer", raw_text="d v1", parsed=[]),
            _agent_output("backend_developer", raw_text="d v2", parsed=[]),
        ]
    )
    wf.developer = dev_mock
    wf.reviewer = MagicMock()
    wf.reviewer.run = AsyncMock(
        side_effect=[
            _agent_output("code_reviewer", parsed={"verdict": "NEEDS_CHANGES"}),
            _agent_output(
                "code_reviewer", parsed={"verdict": "NEEDS_CHANGES", "quality_score": 0.7}
            ),
        ]
    )

    result = await wf.run(title="X", description="y")

    # La mission ne crash pas
    assert result.final_verdict in ("APPROVED", "NEEDS_CHANGES", "REJECTED")
    # Developer v2 doit recevoir l'archi v1 (fallback) puisque arch v2 a fail
    dev_v2_call = dev_mock.run.call_args_list[1]
    dev_v2_input = dev_v2_call.args[0] if dev_v2_call.args else dev_v2_call.kwargs.get("agent_input")
    assert dev_v2_input.context["architecture_proposal_yaml"] == "ARCH_V1_OK"
