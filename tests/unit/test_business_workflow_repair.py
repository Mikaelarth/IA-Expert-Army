"""Tests régression du repair loop BusinessWorkflow.

Couvre la fix Sprint PP (2026-05-11) : quand le Legal verdict est
NEEDS_CHANGES, le repair loop doit ré-exécuter les 3 agents (PM puis BA
puis Legal), pas seulement le BA comme la v1.

Rationale : sur la mission water-tracker (cf. ADR-009), le Legal demandait
que les livrables conformité (CGU/Privacy/DPA) soient gravés dans les
Definition of Done du plan PM, pas juste recommandés en analyse BA. Avec
la v1 (BA-only repair), le plan PM restait figé → NEEDS_CHANGES éternel.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.config import Settings
from src.guilds.business.workflow import BusinessWorkflow
from src.memory.file_memory import FileMemory
from src.orchestrator.base_agent import AgentOutput


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
    parsed: dict | None = None,
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


@pytest.mark.asyncio
async def test_repair_loop_reruns_pm_and_ba_and_legal(
    settings: Settings, memory: FileMemory
) -> None:
    """Le repair loop sur NEEDS_CHANGES doit appeler PM, BA et Legal chacun
    DEUX fois (run initial + run de repair). C'est la fix Sprint PP."""
    wf = BusinessWorkflow(memory=memory, settings=settings)

    pm_mock = MagicMock()
    pm_mock.run = AsyncMock(
        side_effect=[
            _agent_output("project_manager", raw_text="plan v1", parsed={"plan": "v1"}),
            _agent_output("project_manager", raw_text="plan v2", parsed={"plan": "v2"}),
        ]
    )
    analyst_mock = MagicMock()
    analyst_mock.run = AsyncMock(
        side_effect=[
            _agent_output("business_analyst", raw_text="analysis v1"),
            _agent_output("business_analyst", raw_text="analysis v2"),
        ]
    )
    # Legal NEEDS_CHANGES la 1ère fois → déclenche repair → APPROVED la 2ème
    legal_mock = MagicMock()
    legal_mock.run = AsyncMock(
        side_effect=[
            _agent_output(
                "legal_reviewer",
                raw_text="legal v1",
                parsed={"verdict": "NEEDS_CHANGES", "summary": "Conformité à graver"},
            ),
            _agent_output(
                "legal_reviewer",
                raw_text="legal v2",
                parsed={"verdict": "APPROVED", "summary": "OK", "quality_score": 0.92},
            ),
        ]
    )
    wf.pm = pm_mock
    wf.analyst = analyst_mock
    wf.legal = legal_mock

    result = await wf.run(title="Test repair", description="x")

    # Chaque agent appelé exactement 2× (1 initial + 1 repair)
    assert pm_mock.run.call_count == 2, "PM doit être ré-exécuté dans le repair loop (fix Sprint PP)"
    assert analyst_mock.run.call_count == 2
    assert legal_mock.run.call_count == 2

    # Verdict final = APPROVED (repair a réussi)
    assert result.final_verdict == "APPROVED"
    assert result.success is True
    # Le résultat doit refléter les versions v2
    assert result.project_plan_yaml == "plan v2"
    assert result.business_analysis_yaml == "analysis v2"


@pytest.mark.asyncio
async def test_repair_pm_receives_legal_feedback_in_context(
    settings: Settings, memory: FileMemory
) -> None:
    """Le PM v2 doit recevoir le feedback Legal dans son contexte, sinon il
    n'a aucune raison de modifier son plan."""
    wf = BusinessWorkflow(memory=memory, settings=settings)

    pm_mock = MagicMock()
    pm_mock.run = AsyncMock(
        side_effect=[
            _agent_output("project_manager", raw_text="plan v1"),
            _agent_output("project_manager", raw_text="plan v2"),
        ]
    )
    analyst_mock = MagicMock()
    analyst_mock.run = AsyncMock(
        side_effect=[
            _agent_output("business_analyst", raw_text="analysis v1"),
            _agent_output("business_analyst", raw_text="analysis v2"),
        ]
    )
    legal_mock = MagicMock()
    legal_mock.run = AsyncMock(
        side_effect=[
            _agent_output(
                "legal_reviewer",
                raw_text="LEGAL_FEEDBACK_VERY_SPECIFIC",
                parsed={"verdict": "NEEDS_CHANGES"},
            ),
            _agent_output(
                "legal_reviewer",
                raw_text="legal v2",
                parsed={"verdict": "APPROVED", "quality_score": 0.9},
            ),
        ]
    )
    wf.pm = pm_mock
    wf.analyst = analyst_mock
    wf.legal = legal_mock

    await wf.run(title="X", description="y")

    # 2ème appel au PM doit contenir le legal_feedback_yaml dans context
    pm_v2_call = pm_mock.run.call_args_list[1]
    pm_v2_input = pm_v2_call.args[0] if pm_v2_call.args else pm_v2_call.kwargs.get("agent_input")
    assert "LEGAL_FEEDBACK_VERY_SPECIFIC" in pm_v2_input.context.get("legal_feedback_yaml", ""), (
        "PM v2 doit recevoir le feedback Legal en contexte pour pouvoir mettre à jour son plan"
    )
    assert "business_analysis_yaml" in pm_v2_input.context, (
        "PM v2 doit aussi voir l'analyse BA initiale pour ne pas régresser sur la viabilité"
    )


@pytest.mark.asyncio
async def test_repair_ba_v2_receives_updated_pm_plan(
    settings: Settings, memory: FileMemory
) -> None:
    """BA v2 doit voir le plan PM MIS À JOUR (pas l'initial), sinon le
    chaînage du repair n'a pas de sens."""
    wf = BusinessWorkflow(memory=memory, settings=settings)

    pm_mock = MagicMock()
    pm_mock.run = AsyncMock(
        side_effect=[
            _agent_output("project_manager", raw_text="PLAN_V1"),
            _agent_output("project_manager", raw_text="PLAN_V2_UPDATED"),
        ]
    )
    analyst_mock = MagicMock()
    analyst_mock.run = AsyncMock(
        side_effect=[
            _agent_output("business_analyst", raw_text="analysis v1"),
            _agent_output("business_analyst", raw_text="analysis v2"),
        ]
    )
    legal_mock = MagicMock()
    legal_mock.run = AsyncMock(
        side_effect=[
            _agent_output("legal_reviewer", parsed={"verdict": "NEEDS_CHANGES"}),
            _agent_output("legal_reviewer", parsed={"verdict": "APPROVED", "quality_score": 0.9}),
        ]
    )
    wf.pm = pm_mock
    wf.analyst = analyst_mock
    wf.legal = legal_mock

    await wf.run(title="X", description="y")

    ba_v2_call = analyst_mock.run.call_args_list[1]
    ba_v2_input = ba_v2_call.args[0] if ba_v2_call.args else ba_v2_call.kwargs.get("agent_input")
    assert ba_v2_input.context["project_plan_yaml"] == "PLAN_V2_UPDATED", (
        "BA v2 doit lire le plan PM v2, pas l'initial — sinon le chaînage du repair ne sert à rien"
    )


@pytest.mark.asyncio
async def test_no_repair_when_initial_legal_approved(
    settings: Settings, memory: FileMemory
) -> None:
    """Si Legal APPROUVE du premier coup, AUCUN agent ne doit être ré-exécuté."""
    wf = BusinessWorkflow(memory=memory, settings=settings)

    pm_mock = MagicMock()
    pm_mock.run = AsyncMock(return_value=_agent_output("project_manager"))
    analyst_mock = MagicMock()
    analyst_mock.run = AsyncMock(return_value=_agent_output("business_analyst"))
    legal_mock = MagicMock()
    legal_mock.run = AsyncMock(
        return_value=_agent_output(
            "legal_reviewer", parsed={"verdict": "APPROVED", "quality_score": 0.95}
        )
    )
    wf.pm = pm_mock
    wf.analyst = analyst_mock
    wf.legal = legal_mock

    result = await wf.run(title="X", description="y")

    assert pm_mock.run.call_count == 1, "PM ne doit PAS être ré-exécuté si Legal APPROUVE direct"
    assert analyst_mock.run.call_count == 1
    assert legal_mock.run.call_count == 1
    assert result.final_verdict == "APPROVED"


@pytest.mark.asyncio
async def test_repair_handles_pm_v2_failure_gracefully(
    settings: Settings, memory: FileMemory
) -> None:
    """Si PM v2 plante (API timeout p.ex.), le repair continue avec le plan v1
    pour le BA (fallback). Le repair ne doit pas crasher la mission entière."""
    wf = BusinessWorkflow(memory=memory, settings=settings)

    pm_mock = MagicMock()
    pm_mock.run = AsyncMock(
        side_effect=[
            _agent_output("project_manager", raw_text="PLAN_V1_OK"),
            _agent_output("project_manager", raw_text="", success=False),
        ]
    )
    analyst_mock = MagicMock()
    analyst_mock.run = AsyncMock(
        side_effect=[
            _agent_output("business_analyst", raw_text="analysis v1"),
            _agent_output("business_analyst", raw_text="analysis v2"),
        ]
    )
    legal_mock = MagicMock()
    legal_mock.run = AsyncMock(
        side_effect=[
            _agent_output("legal_reviewer", parsed={"verdict": "NEEDS_CHANGES"}),
            _agent_output(
                "legal_reviewer",
                parsed={"verdict": "NEEDS_CHANGES", "quality_score": 0.7},
            ),
        ]
    )
    wf.pm = pm_mock
    wf.analyst = analyst_mock
    wf.legal = legal_mock

    result = await wf.run(title="X", description="y")

    # La mission ne crashe pas
    assert result.final_verdict in ("NEEDS_CHANGES", "APPROVED", "REJECTED")
    # BA v2 doit avoir reçu le plan v1 (fallback) puisque pm v2 a fail
    ba_v2_call = analyst_mock.run.call_args_list[1]
    ba_v2_input = ba_v2_call.args[0] if ba_v2_call.args else ba_v2_call.kwargs.get("agent_input")
    assert ba_v2_input.context["project_plan_yaml"] == "PLAN_V1_OK"
