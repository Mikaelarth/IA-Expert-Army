"""Tests Quality Guardian (Sprint YY).

Couvre :
- QGVerdict properties (accepted, needs_rework)
- review_mission : happy path ACCEPT / NEEDS_REWORK / ESCALATE
- review_mission : skip si REJECTED (validation sans appel)
- review_mission : fallback None si parsing échoue
- MissionRouter avec enable_quality_guardian=True / False (intégration)
- L'override de verdict guilde n'est JAMAIS automatique (politique de design)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.config import Settings
from src.memory.file_memory import FileMemory
from src.orchestrator.base_agent import AgentOutput
from src.orchestrator.quality_guardian import (
    VERDICT_QG_ACCEPT,
    VERDICT_QG_ESCALATE,
    VERDICT_QG_NEEDS_REWORK,
    QGVerdict,
    QualityGuardian,
    review_mission,
)
from src.orchestrator.router import MissionRouter


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def _qg_agent_output(parsed: dict, success: bool = True) -> AgentOutput:
    return AgentOutput(
        agent_name="quality_guardian",
        mission_id=uuid4(),
        success=success,
        raw_text="...",
        parsed=parsed,
        tokens_in=200,
        tokens_out=300,
        cost_usd=0.15,
        duration_seconds=8.0,
    )


# ===== QGVerdict properties =====


def test_qg_verdict_accepted_property() -> None:
    v = QGVerdict(verdict_qg=VERDICT_QG_ACCEPT, final_score=0.9)
    assert v.accepted is True
    assert v.needs_rework is False


def test_qg_verdict_needs_rework_property() -> None:
    v = QGVerdict(verdict_qg=VERDICT_QG_NEEDS_REWORK, final_score=0.6)
    assert v.accepted is False
    assert v.needs_rework is True


def test_qg_verdict_escalate_is_not_accepted_nor_needs_rework() -> None:
    v = QGVerdict(verdict_qg=VERDICT_QG_ESCALATE)
    assert v.accepted is False
    assert v.needs_rework is False


# ===== review_mission =====


@pytest.mark.asyncio
async def test_review_mission_accept_happy_path(settings: Settings, memory: FileMemory) -> None:
    """Verdict guilde APPROVED, QG ACCEPT : retourne un QGVerdict propre."""
    qg = QualityGuardian(memory=memory, settings=settings)
    qg.run = AsyncMock(  # type: ignore[method-assign]
        return_value=_qg_agent_output(
            {
                "verdict_qg": "ACCEPT",
                "final_score": 0.92,
                "alignment_check": "Aligné avec la demande.",
                "scope_check": "Scope bien cadré.",
                "verdict_calibration": "Score guilde défendable.",
                "meta_concerns": [],
                "rationale": "Tout est aligné.",
            }
        )
    )

    verdict = await review_mission(
        qg=qg,
        mission_title="Endpoint /ping",
        mission_description="Crée un endpoint GET /ping qui retourne {status: ok}",
        guild="engineering",
        guild_verdict="APPROVED",
        guild_score=0.91,
        guild_summary="Code propre, tests OK.",
        raw_result_excerpt="@app.get('/ping') ...",
    )

    assert verdict is not None
    assert verdict.verdict_qg == "ACCEPT"
    assert verdict.accepted is True
    assert verdict.final_score == 0.92
    assert "aligné" in verdict.alignment_check.lower()


@pytest.mark.asyncio
async def test_review_mission_needs_rework_with_concerns(
    settings: Settings, memory: FileMemory
) -> None:
    """QG détecte une dérive de scope : NEEDS_REWORK avec meta_concerns."""
    qg = QualityGuardian(memory=memory, settings=settings)
    qg.run = AsyncMock(  # type: ignore[method-assign]
        return_value=_qg_agent_output(
            {
                "verdict_qg": "NEEDS_REWORK",
                "final_score": 0.6,
                "meta_concerns": [
                    "Le brief demandait V1 minimal, la guilde a livré V1 + V2",
                    "L'endpoint /admin n'était pas dans la demande",
                ],
                "rationale": "Scope drift majeur.",
            }
        )
    )

    verdict = await review_mission(
        qg=qg,
        mission_title="Endpoint /ping minimal",
        mission_description="Juste /ping, rien d'autre",
        guild="engineering",
        guild_verdict="APPROVED",
        guild_score=0.93,
        guild_summary="Tests OK",
    )

    assert verdict is not None
    assert verdict.needs_rework is True
    assert len(verdict.meta_concerns) == 2
    assert "scope drift" in verdict.rationale.lower()


@pytest.mark.asyncio
async def test_review_mission_escalate(settings: Settings, memory: FileMemory) -> None:
    """Cas ambigu : QG escalade plutôt que de statuer."""
    qg = QualityGuardian(memory=memory, settings=settings)
    qg.run = AsyncMock(  # type: ignore[method-assign]
        return_value=_qg_agent_output(
            {
                "verdict_qg": "ESCALATE",
                "rationale": "Brief flou, je ne peux pas juger l'alignement.",
            }
        )
    )

    verdict = await review_mission(
        qg=qg,
        mission_title="Un truc",
        mission_description="Fais quelque chose de bien",
        guild="creative",
        guild_verdict="APPROVED",
        guild_score=0.85,
        guild_summary="Texte OK",
    )

    assert verdict is not None
    assert verdict.verdict_qg == "ESCALATE"
    assert verdict.accepted is False
    assert verdict.needs_rework is False


@pytest.mark.asyncio
async def test_review_mission_skips_rejected_verdict(
    settings: Settings, memory: FileMemory
) -> None:
    """Si la guilde a déjà REJECTED, le QG valide sans appel API."""
    qg = QualityGuardian(memory=memory, settings=settings)
    qg.run = AsyncMock()  # type: ignore[method-assign]  # ne doit PAS être appelé

    verdict = await review_mission(
        qg=qg,
        mission_title="X",
        mission_description="y",
        guild="engineering",
        guild_verdict="REJECTED",
        guild_score=0.2,
        guild_summary="Failed code",
    )

    assert verdict is not None
    assert verdict.verdict_qg == "ACCEPT"
    assert "REJECTED" in verdict.rationale
    qg.run.assert_not_called()


@pytest.mark.asyncio
async def test_review_mission_returns_none_on_parse_failure(
    settings: Settings, memory: FileMemory
) -> None:
    """Si le QG retourne un YAML invalide, on retourne None (fallback caller)."""
    qg = QualityGuardian(memory=memory, settings=settings)
    qg.run = AsyncMock(return_value=_qg_agent_output({}, success=False))  # type: ignore[method-assign]

    verdict = await review_mission(
        qg=qg,
        mission_title="X",
        mission_description="y",
        guild="engineering",
        guild_verdict="APPROVED",
        guild_score=0.9,
        guild_summary="ok",
    )

    assert verdict is None


@pytest.mark.asyncio
async def test_review_mission_rejects_invalid_verdict_label(
    settings: Settings, memory: FileMemory
) -> None:
    """Si le QG produit un verdict hors {ACCEPT, NEEDS_REWORK, ESCALATE}, fallback None."""
    qg = QualityGuardian(memory=memory, settings=settings)
    qg.run = AsyncMock(  # type: ignore[method-assign]
        return_value=_qg_agent_output({"verdict_qg": "MAYBE", "rationale": "..."})
    )

    verdict = await review_mission(
        qg=qg,
        mission_title="X",
        mission_description="y",
        guild="engineering",
        guild_verdict="APPROVED",
        guild_score=0.9,
        guild_summary="ok",
    )

    assert verdict is None


@pytest.mark.asyncio
async def test_review_mission_caps_concerns_at_three(
    settings: Settings, memory: FileMemory
) -> None:
    """meta_concerns plafonné à 3 (conformément au prompt)."""
    qg = QualityGuardian(memory=memory, settings=settings)
    qg.run = AsyncMock(  # type: ignore[method-assign]
        return_value=_qg_agent_output(
            {
                "verdict_qg": "NEEDS_REWORK",
                "meta_concerns": ["c1", "c2", "c3", "c4", "c5"],
                "rationale": "Multi-issues",
            }
        )
    )
    verdict = await review_mission(
        qg=qg,
        mission_title="X",
        mission_description="y",
        guild="engineering",
        guild_verdict="APPROVED",
        guild_score=0.9,
        guild_summary="ok",
    )
    assert verdict is not None
    assert len(verdict.meta_concerns) == 3


# ===== Settings flag =====


def test_settings_enable_qg_defaults_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Par défaut le QG est désactivé (opt-in)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.enable_quality_guardian is False


def test_settings_enable_qg_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ENABLE_QUALITY_GUARDIAN", "true")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.enable_quality_guardian is True


# ===== MissionRouter intégration =====


@pytest.mark.asyncio
async def test_router_does_not_call_qg_when_disabled(
    settings: Settings, memory: FileMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """enable_quality_guardian=False (défaut) → pas d'appel QG, qg_verdict reste None."""
    router = MissionRouter(memory=memory, settings=settings)
    # Mock la guilde engineering
    fake_workflow_result = MagicMock()
    fake_workflow_result.mission_id = uuid4()
    fake_workflow_result.title = "X"
    fake_workflow_result.success = True
    fake_workflow_result.final_verdict = "APPROVED"
    fake_workflow_result.quality_score = 0.9
    fake_workflow_result.total_cost_usd = 0.5
    fake_workflow_result.total_duration_seconds = 100.0
    fake_workflow_result.review_summary = "ok"
    fake_workflow_result.model_dump = MagicMock(return_value={"foo": "bar"})

    workflow_mock = MagicMock()
    workflow_mock.run = AsyncMock(return_value=fake_workflow_result)
    monkeypatch.setattr("src.orchestrator.router.Workflow", MagicMock(return_value=workflow_mock))

    # Spy sur _apply_quality_guardian pour confirmer qu'il n'est pas appelé
    apply_spy = MagicMock(wraps=router._apply_quality_guardian)
    monkeypatch.setattr(router, "_apply_quality_guardian", apply_spy)

    result = await router.run(title="X", description="y", force_guild="engineering")

    assert result.qg_verdict is None
    apply_spy.assert_not_called()


@pytest.mark.asyncio
async def test_router_calls_qg_when_enabled(
    memory: FileMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """enable_quality_guardian=True → QG appelé, champs qg_* enrichis."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ENABLE_QUALITY_GUARDIAN", "true")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    router = MissionRouter(memory=memory, settings=settings)

    # Mock la guilde
    fake_workflow_result = MagicMock()
    fake_workflow_result.mission_id = uuid4()
    fake_workflow_result.title = "X"
    fake_workflow_result.success = True
    fake_workflow_result.final_verdict = "APPROVED"
    fake_workflow_result.quality_score = 0.9
    fake_workflow_result.total_cost_usd = 0.5
    fake_workflow_result.total_duration_seconds = 100.0
    fake_workflow_result.review_summary = "ok"
    fake_workflow_result.model_dump = MagicMock(return_value={"foo": "bar"})

    workflow_mock = MagicMock()
    workflow_mock.run = AsyncMock(return_value=fake_workflow_result)
    monkeypatch.setattr("src.orchestrator.router.Workflow", MagicMock(return_value=workflow_mock))

    # Mock le QG via review_mission
    async def fake_review(**kwargs):
        return QGVerdict(
            verdict_qg=VERDICT_QG_ACCEPT,
            final_score=0.91,
            meta_concerns=["minor concern"],
            rationale="OK",
        )

    monkeypatch.setattr("src.orchestrator.quality_guardian.review_mission", fake_review)

    # On évite l'instantiation réelle de QualityGuardian qui tente d'ouvrir le prompt
    monkeypatch.setattr("src.orchestrator.quality_guardian.QualityGuardian", MagicMock())

    result = await router.run(title="X", description="y", force_guild="engineering")

    assert result.qg_verdict == "ACCEPT"
    assert result.qg_final_score == 0.91
    assert result.qg_concerns == ["minor concern"]
    assert result.qg_rationale == "OK"
    # Le verdict guilde est PRÉSERVÉ — pas d'override automatique
    assert result.final_verdict == "APPROVED"


@pytest.mark.asyncio
async def test_router_preserves_guild_verdict_even_when_qg_needs_rework(
    memory: FileMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Politique explicite : le QG ne fait JAMAIS un override automatique du
    verdict guilde. Il informe via qg_verdict. C'est au caller de décider."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ENABLE_QUALITY_GUARDIAN", "true")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    router = MissionRouter(memory=memory, settings=settings)

    fake_workflow_result = MagicMock()
    fake_workflow_result.mission_id = uuid4()
    fake_workflow_result.title = "X"
    fake_workflow_result.success = True
    fake_workflow_result.final_verdict = "APPROVED"  # Guilde approuve
    fake_workflow_result.quality_score = 0.95
    fake_workflow_result.total_cost_usd = 0.5
    fake_workflow_result.total_duration_seconds = 100.0
    fake_workflow_result.review_summary = "ok"
    fake_workflow_result.model_dump = MagicMock(return_value={"foo": "bar"})

    workflow_mock = MagicMock()
    workflow_mock.run = AsyncMock(return_value=fake_workflow_result)
    monkeypatch.setattr("src.orchestrator.router.Workflow", MagicMock(return_value=workflow_mock))

    async def fake_review(**kwargs):
        # Mais le QG dit NEEDS_REWORK (dérive de scope p.ex.)
        return QGVerdict(
            verdict_qg=VERDICT_QG_NEEDS_REWORK,
            final_score=0.55,
            meta_concerns=["scope drift major"],
            rationale="Over-delivery non demandée",
        )

    monkeypatch.setattr("src.orchestrator.quality_guardian.review_mission", fake_review)
    monkeypatch.setattr("src.orchestrator.quality_guardian.QualityGuardian", MagicMock())

    result = await router.run(title="X", description="y", force_guild="engineering")

    # Le verdict guilde APPROVED est CONSERVÉ
    assert result.final_verdict == "APPROVED"
    assert result.quality_score == 0.95
    # Le QG informe en parallèle — c'est au caller de filtrer
    assert result.qg_verdict == "NEEDS_REWORK"
    assert result.qg_final_score == 0.55
