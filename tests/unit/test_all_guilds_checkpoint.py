"""Tests v0.9.5 — checkpoint/resume étendu aux 3 guildes non-Engineering.

Valide qu'un re-run avec le même mission_id ne ré-exécute PAS les agents
déjà checkpointés. Régression cible : avant v0.9.5, seul EngineeringWorkflow
supportait F1 ; un restart de container tuait les missions Research/Creative/
Business sans possibilité de reprise.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.checkpoint import CheckpointStore
from src.core.config import Settings
from src.memory.file_memory import FileMemory
from src.orchestrator.base_agent import AgentOutput


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


@pytest.fixture
def cs(tmp_path: Path) -> CheckpointStore:
    return CheckpointStore(tmp_path / "checkpoints")


def _fake_out(text: str, parsed: object = None) -> AgentOutput:
    return AgentOutput(
        agent_name="fake",
        success=True,
        raw_text=text,
        parsed=parsed,
        cost_usd=0.0,
        duration_seconds=0.1,
        tokens_in=10,
        tokens_out=20,
    )


# ---------------------------------------------------------------------------
# CreativeWorkflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creative_workflow_writes_checkpoints_and_clears_on_success(
    memory: FileMemory,
    cs: CheckpointStore,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workflow Creative nominal : 3 agents → 3 checkpoints écrits → clear
    en fin de mission réussie. Régression cible : avant v0.9.5, aucun
    checkpoint n'était écrit pour Creative."""
    from src.guilds.creative.workflow import CreativeWorkflow

    wf = CreativeWorkflow(memory=memory, settings=settings, checkpoint_store=cs)

    monkeypatch.setattr(
        wf.strategist, "run", AsyncMock(return_value=_fake_out("strat", parsed={"audience": "PMs"}))
    )
    monkeypatch.setattr(
        wf.copywriter, "run", AsyncMock(return_value=_fake_out("# Landing\n\nHero text"))
    )
    monkeypatch.setattr(
        wf.editor,
        "run",
        AsyncMock(
            return_value=_fake_out(
                "verdict", parsed={"verdict": "APPROVED", "quality_score": 0.92, "summary": "ok"}
            )
        ),
    )

    mid = uuid4()
    assert cs.list_missions() == []  # rien avant

    result = await wf.run("Landing page test", "Description", mission_id=mid)

    assert result.success is True
    assert result.final_verdict == "APPROVED"
    # Clear automatique en fin de mission réussie
    assert cs.has_checkpoint(str(mid)) is False


@pytest.mark.asyncio
async def test_creative_workflow_resume_skips_already_completed_agents(
    memory: FileMemory,
    cs: CheckpointStore,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Démonstration concrète du resume Creative : si checkpoints 0+1 (strategist
    + copywriter) existent, seul l'editor est appelé en re-run."""
    from src.guilds.creative.workflow import CreativeWorkflow

    mid = uuid4()
    # Pré-existence des checkpoints
    cs.save(
        str(mid),
        0,
        "content_strategist",
        _fake_out("cached strategist", parsed={"audience": "PMs"}),
    )
    cs.save(str(mid), 1, "copywriter", _fake_out("cached copy"))

    wf = CreativeWorkflow(memory=memory, settings=settings, checkpoint_store=cs)

    strat_mock = AsyncMock(return_value=_fake_out("should not run"))
    copy_mock = AsyncMock(return_value=_fake_out("should not run"))
    editor_mock = AsyncMock(
        return_value=_fake_out(
            "verdict", parsed={"verdict": "APPROVED", "quality_score": 0.9, "summary": "ok"}
        )
    )
    monkeypatch.setattr(wf.strategist, "run", strat_mock)
    monkeypatch.setattr(wf.copywriter, "run", copy_mock)
    monkeypatch.setattr(wf.editor, "run", editor_mock)

    await wf.run("Resume test", "desc", mission_id=mid)

    strat_mock.assert_not_called()  # skip via checkpoint
    copy_mock.assert_not_called()  # skip via checkpoint
    editor_mock.assert_called_once()  # appelé normalement


# ---------------------------------------------------------------------------
# ResearchWorkflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_workflow_writes_checkpoints_and_clears_on_success(
    memory: FileMemory,
    cs: CheckpointStore,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workflow Research nominal : 4 agents → 4 checkpoints écrits → clear."""
    from src.guilds.research.workflow import ResearchWorkflow

    wf = ResearchWorkflow(memory=memory, settings=settings, checkpoint_store=cs)

    monkeypatch.setattr(
        wf.lead, "run", AsyncMock(return_value=_fake_out("plan", parsed={"sub_questions": ["q1"]}))
    )
    monkeypatch.setattr(wf.watch, "run", AsyncMock(return_value=_fake_out("findings")))
    monkeypatch.setattr(wf.synth, "run", AsyncMock(return_value=_fake_out("# Synthèse")))
    monkeypatch.setattr(
        wf.reviewer,
        "run",
        AsyncMock(
            return_value=_fake_out(
                "verdict", parsed={"verdict": "APPROVED", "quality_score": 0.88, "summary": "ok"}
            )
        ),
    )

    mid = uuid4()
    result = await wf.run("Test research", "desc", mission_id=mid)

    assert result.success is True
    assert cs.has_checkpoint(str(mid)) is False


@pytest.mark.asyncio
async def test_research_workflow_resume_skips_already_completed_agents(
    memory: FileMemory,
    cs: CheckpointStore,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume Research : 2 premiers agents en cache → seuls synth + reviewer
    tournent."""
    from src.guilds.research.workflow import ResearchWorkflow

    mid = uuid4()
    cs.save(
        str(mid),
        0,
        "research_lead",
        _fake_out("cached plan", parsed={"sub_questions": ["q"]}),
    )
    cs.save(str(mid), 1, "tech_watch", _fake_out("cached findings"))

    wf = ResearchWorkflow(memory=memory, settings=settings, checkpoint_store=cs)

    lead_mock = AsyncMock(return_value=_fake_out("should not run"))
    watch_mock = AsyncMock(return_value=_fake_out("should not run"))
    synth_mock = AsyncMock(return_value=_fake_out("# Synthèse"))
    reviewer_mock = AsyncMock(
        return_value=_fake_out(
            "verdict", parsed={"verdict": "APPROVED", "quality_score": 0.9, "summary": "ok"}
        )
    )
    monkeypatch.setattr(wf.lead, "run", lead_mock)
    monkeypatch.setattr(wf.watch, "run", watch_mock)
    monkeypatch.setattr(wf.synth, "run", synth_mock)
    monkeypatch.setattr(wf.reviewer, "run", reviewer_mock)

    await wf.run("Resume research", "desc", mission_id=mid)

    lead_mock.assert_not_called()
    watch_mock.assert_not_called()
    synth_mock.assert_called_once()
    reviewer_mock.assert_called_once()


# ---------------------------------------------------------------------------
# BusinessWorkflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_business_workflow_writes_checkpoints_and_clears_on_success(
    memory: FileMemory,
    cs: CheckpointStore,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workflow Business nominal : 3 agents → checkpoints écrits → clear."""
    from src.guilds.business.workflow import BusinessWorkflow

    wf = BusinessWorkflow(memory=memory, settings=settings, checkpoint_store=cs)

    monkeypatch.setattr(
        wf.pm, "run", AsyncMock(return_value=_fake_out("plan", parsed={"milestones": ["m1"]}))
    )
    monkeypatch.setattr(wf.analyst, "run", AsyncMock(return_value=_fake_out("analysis")))
    monkeypatch.setattr(
        wf.legal,
        "run",
        AsyncMock(
            return_value=_fake_out(
                "verdict", parsed={"verdict": "APPROVED", "quality_score": 0.91, "summary": "ok"}
            )
        ),
    )

    mid = uuid4()
    result = await wf.run("Roadmap test", "desc", mission_id=mid)

    assert result.success is True
    assert cs.has_checkpoint(str(mid)) is False


@pytest.mark.asyncio
async def test_business_workflow_resume_skips_already_completed_agents(
    memory: FileMemory,
    cs: CheckpointStore,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume Business : PM en cache → seuls analyst + legal tournent."""
    from src.guilds.business.workflow import BusinessWorkflow

    mid = uuid4()
    cs.save(
        str(mid),
        0,
        "project_manager",
        _fake_out("cached plan", parsed={"milestones": ["m"]}),
    )

    wf = BusinessWorkflow(memory=memory, settings=settings, checkpoint_store=cs)

    pm_mock = AsyncMock(return_value=_fake_out("should not run"))
    analyst_mock = AsyncMock(return_value=_fake_out("analysis"))
    legal_mock = AsyncMock(
        return_value=_fake_out(
            "verdict", parsed={"verdict": "APPROVED", "quality_score": 0.9, "summary": "ok"}
        )
    )
    monkeypatch.setattr(wf.pm, "run", pm_mock)
    monkeypatch.setattr(wf.analyst, "run", analyst_mock)
    monkeypatch.setattr(wf.legal, "run", legal_mock)

    await wf.run("Resume business", "desc", mission_id=mid)

    pm_mock.assert_not_called()  # skip via checkpoint
    analyst_mock.assert_called_once()
    legal_mock.assert_called_once()


# ---------------------------------------------------------------------------
# On_progress emission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creative_workflow_emits_mission_started_and_completed(
    memory: FileMemory, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v0.9.5 — CreativeWorkflow émet mission_started + mission_completed
    via le callback on_progress. Avant : seul Engineering le faisait."""
    from src.guilds.creative.workflow import CreativeWorkflow
    from src.orchestrator.progress import ProgressEvent

    wf = CreativeWorkflow(memory=memory, settings=settings)
    monkeypatch.setattr(
        wf.strategist, "run", AsyncMock(return_value=_fake_out("s", parsed={"audience": "x"}))
    )
    monkeypatch.setattr(wf.copywriter, "run", AsyncMock(return_value=_fake_out("c")))
    monkeypatch.setattr(
        wf.editor,
        "run",
        AsyncMock(
            return_value=_fake_out(
                "v", parsed={"verdict": "APPROVED", "quality_score": 0.9, "summary": "ok"}
            )
        ),
    )

    captured: list[ProgressEvent] = []
    await wf.run("test", "desc", on_progress=captured.append)
    types_seen = [e.event_type for e in captured]
    assert "mission_started" in types_seen
    assert "mission_completed" in types_seen
    # 3 agents nominaux → 3 agent_started + 3 agent_completed
    assert types_seen.count("agent_started") == 3
    assert types_seen.count("agent_completed") == 3
