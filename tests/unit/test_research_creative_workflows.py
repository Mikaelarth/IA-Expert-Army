"""Tests des workflows Research et Creative — coverage boost (Sprint UU.4).

Avant Sprint UU.4, `research/workflow.py` et `creative/workflow.py` étaient à
30-31% de couverture alors que `business/workflow.py` était à 81% et
`orchestrator/workflow.py` à 89%. Asymétrie réelle de qualité.

Tests symétriques aux suites Business/Engineering existantes :
- happy path (4 agents appelés, APPROVED retourné)
- chaque agent peut planter → workflow retourne FAILED:<stage>
- repair loop sur NEEDS_CHANGES → Synthesizer/Editor re-runs
- killswitch / budget → FAILED early
- score propagation aux épisodes
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.config import Settings
from src.core.killswitch import Killswitch
from src.guilds.creative.workflow import CreativeWorkflow
from src.guilds.research.workflow import ResearchWorkflow
from src.memory.file_memory import FileMemory, MemoryRecord
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
    parsed: object = None,
    success: bool = True,
    cost: float = 0.05,
    error: str | None = None,
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
        error=error,
    )


# ===== RESEARCH WORKFLOW =====


@pytest.mark.asyncio
async def test_research_workflow_happy_path(settings: Settings, memory: FileMemory) -> None:
    """Les 4 agents (lead → watch → synth → reviewer) sont appelés dans l'ordre
    et le verdict APPROVED est propagé."""
    wf = ResearchWorkflow(memory=memory, settings=settings)
    wf.lead = MagicMock()
    wf.lead.run = AsyncMock(return_value=_agent_output("research_lead", raw_text="plan"))
    wf.watch = MagicMock()
    wf.watch.run = AsyncMock(return_value=_agent_output("tech_watch", raw_text="findings"))
    wf.synth = MagicMock()
    wf.synth.run = AsyncMock(
        return_value=_agent_output("document_synthesizer", raw_text="synthèse")
    )
    wf.reviewer = MagicMock()
    wf.reviewer.run = AsyncMock(
        return_value=_agent_output(
            "research_reviewer",
            parsed={"verdict": "APPROVED", "summary": "Bien", "quality_score": 0.92},
        )
    )

    result = await wf.run(title="Compare A vs B", description="x")

    assert result.success is True
    assert result.final_verdict == "APPROVED"
    assert result.quality_score == 0.92
    assert result.synthesis_markdown == "synthèse"
    assert "Bien" in result.review_summary
    # Pas de repair → 4 agents appelés une seule fois
    wf.lead.run.assert_awaited_once()
    wf.watch.run.assert_awaited_once()
    wf.synth.run.assert_awaited_once()
    wf.reviewer.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_research_workflow_persists_summary_file(
    settings: Settings, memory: FileMemory
) -> None:
    """À la fin de la mission, un fichier `data/memory/missions/<uuid>.md` est écrit."""
    wf = ResearchWorkflow(memory=memory, settings=settings)
    wf.lead = MagicMock()
    wf.lead.run = AsyncMock(return_value=_agent_output("research_lead"))
    wf.watch = MagicMock()
    wf.watch.run = AsyncMock(return_value=_agent_output("tech_watch"))
    wf.synth = MagicMock()
    wf.synth.run = AsyncMock(return_value=_agent_output("document_synthesizer", raw_text="md"))
    wf.reviewer = MagicMock()
    wf.reviewer.run = AsyncMock(
        return_value=_agent_output(
            "research_reviewer", parsed={"verdict": "APPROVED", "quality_score": 0.9}
        )
    )

    result = await wf.run(title="X", description="y")

    summary = memory.get_mission_summary(result.mission_id)
    assert summary is not None
    assert summary.metadata["final_verdict"] == "APPROVED"
    assert summary.metadata["guild"] == "research"
    assert "Guilde :** Research" in summary.body


@pytest.mark.asyncio
async def test_research_workflow_fails_when_lead_fails(
    settings: Settings, memory: FileMemory
) -> None:
    wf = ResearchWorkflow(memory=memory, settings=settings)
    wf.lead = MagicMock()
    wf.lead.run = AsyncMock(
        return_value=_agent_output("research_lead", success=False, error="API timeout")
    )
    wf.watch = MagicMock()
    wf.watch.run = AsyncMock()  # ne doit pas être appelé
    wf.synth = MagicMock()
    wf.synth.run = AsyncMock()
    wf.reviewer = MagicMock()
    wf.reviewer.run = AsyncMock()

    result = await wf.run(title="X", description="y")

    assert result.success is False
    assert result.final_verdict == "FAILED:research_lead.failed"
    assert "API timeout" in result.review_summary
    wf.watch.run.assert_not_called()
    wf.synth.run.assert_not_called()
    wf.reviewer.run.assert_not_called()


@pytest.mark.asyncio
async def test_research_workflow_fails_when_watch_fails(
    settings: Settings, memory: FileMemory
) -> None:
    wf = ResearchWorkflow(memory=memory, settings=settings)
    wf.lead = MagicMock()
    wf.lead.run = AsyncMock(return_value=_agent_output("research_lead"))
    wf.watch = MagicMock()
    wf.watch.run = AsyncMock(return_value=_agent_output("tech_watch", success=False, error="x"))
    wf.synth = MagicMock()
    wf.synth.run = AsyncMock()
    wf.reviewer = MagicMock()
    wf.reviewer.run = AsyncMock()

    result = await wf.run(title="X", description="y")

    assert result.final_verdict == "FAILED:tech_watch.failed"


@pytest.mark.asyncio
async def test_research_workflow_repair_loop_reruns_synth_and_reviewer(
    settings: Settings, memory: FileMemory
) -> None:
    """Le repair loop sur NEEDS_CHANGES doit ré-exécuter le Synthesizer puis le Reviewer."""
    wf = ResearchWorkflow(memory=memory, settings=settings)
    wf.lead = MagicMock()
    wf.lead.run = AsyncMock(return_value=_agent_output("research_lead"))
    wf.watch = MagicMock()
    wf.watch.run = AsyncMock(return_value=_agent_output("tech_watch"))
    wf.synth = MagicMock()
    wf.synth.run = AsyncMock(
        side_effect=[
            _agent_output("document_synthesizer", raw_text="synthèse v1"),
            _agent_output("document_synthesizer", raw_text="synthèse v2"),
        ]
    )
    wf.reviewer = MagicMock()
    wf.reviewer.run = AsyncMock(
        side_effect=[
            _agent_output("research_reviewer", parsed={"verdict": "NEEDS_CHANGES"}),
            _agent_output(
                "research_reviewer",
                parsed={"verdict": "APPROVED", "quality_score": 0.9},
            ),
        ]
    )

    result = await wf.run(title="X", description="y")

    assert result.final_verdict == "APPROVED"
    assert wf.synth.run.call_count == 2
    assert wf.reviewer.run.call_count == 2
    assert result.synthesis_markdown == "synthèse v2"


@pytest.mark.asyncio
async def test_research_workflow_killswitch_engaged_fails_early(
    settings: Settings, memory: FileMemory, tmp_path: Path
) -> None:
    ks = Killswitch(tmp_path / ".ks")
    ks.engage(reason="test")
    wf = ResearchWorkflow(memory=memory, settings=settings, killswitch=ks)
    wf.lead = MagicMock()
    wf.lead.run = AsyncMock()

    result = await wf.run(title="X", description="y")
    assert result.final_verdict == "FAILED:killswitch.engaged"
    wf.lead.run.assert_not_called()


@pytest.mark.asyncio
async def test_research_workflow_score_propagation(settings: Settings, memory: FileMemory) -> None:
    """Après APPROVED, chaque épisode de la mission doit avoir quality_score
    et final_verdict dans son frontmatter (utile pour PatternMiner)."""
    wf = ResearchWorkflow(memory=memory, settings=settings)
    mid = uuid4()

    # On simule 4 épisodes déjà écrits par les agents (BaseAgent.run le fait
    # normalement, mais on les mocke ici)
    for agent_name in ("research_lead", "tech_watch", "document_synthesizer", "research_reviewer"):
        memory.write_episode(mid, agent_name, MemoryRecord(metadata={"agent": agent_name}, body=""))

    wf.lead = MagicMock()
    wf.lead.run = AsyncMock(return_value=_agent_output("research_lead"))
    wf.watch = MagicMock()
    wf.watch.run = AsyncMock(return_value=_agent_output("tech_watch"))
    wf.synth = MagicMock()
    wf.synth.run = AsyncMock(return_value=_agent_output("document_synthesizer"))
    wf.reviewer = MagicMock()
    wf.reviewer.run = AsyncMock(
        return_value=_agent_output(
            "research_reviewer", parsed={"verdict": "APPROVED", "quality_score": 0.93}
        )
    )

    await wf.run(title="X", description="y", mission_id=mid)

    for ep_path in memory.list_episodes(mid):
        rec = memory.read_episode(ep_path)
        assert rec.metadata.get("final_verdict") == "APPROVED"
        assert rec.metadata.get("quality_score") == 0.93
        assert rec.metadata.get("guild") == "research"


# ===== CREATIVE WORKFLOW =====


@pytest.mark.asyncio
async def test_creative_workflow_happy_path(settings: Settings, memory: FileMemory) -> None:
    """Les 3 agents (strategist → copywriter → editor) sont appelés et APPROVED
    est propagé."""
    wf = CreativeWorkflow(memory=memory, settings=settings)
    wf.strategist = MagicMock()
    wf.strategist.run = AsyncMock(
        return_value=_agent_output("content_strategist", raw_text="brief")
    )
    wf.copywriter = MagicMock()
    wf.copywriter.run = AsyncMock(return_value=_agent_output("copywriter", raw_text="texte"))
    wf.editor = MagicMock()
    wf.editor.run = AsyncMock(
        return_value=_agent_output(
            "editor", parsed={"verdict": "APPROVED", "summary": "Bon ton", "quality_score": 0.93}
        )
    )

    result = await wf.run(title="Post LinkedIn", description="x")

    assert result.success is True
    assert result.final_verdict == "APPROVED"
    assert result.quality_score == 0.93
    wf.strategist.run.assert_awaited_once()
    wf.copywriter.run.assert_awaited_once()
    wf.editor.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_creative_workflow_persists_summary(settings: Settings, memory: FileMemory) -> None:
    wf = CreativeWorkflow(memory=memory, settings=settings)
    wf.strategist = MagicMock()
    wf.strategist.run = AsyncMock(return_value=_agent_output("content_strategist"))
    wf.copywriter = MagicMock()
    wf.copywriter.run = AsyncMock(return_value=_agent_output("copywriter", raw_text="texte final"))
    wf.editor = MagicMock()
    wf.editor.run = AsyncMock(
        return_value=_agent_output("editor", parsed={"verdict": "APPROVED", "quality_score": 0.9})
    )

    result = await wf.run(title="X", description="y")

    summary = memory.get_mission_summary(result.mission_id)
    assert summary is not None
    assert summary.metadata["guild"] == "creative"
    assert summary.metadata["final_verdict"] == "APPROVED"


@pytest.mark.asyncio
async def test_creative_workflow_fails_when_strategist_fails(
    settings: Settings, memory: FileMemory
) -> None:
    wf = CreativeWorkflow(memory=memory, settings=settings)
    wf.strategist = MagicMock()
    wf.strategist.run = AsyncMock(
        return_value=_agent_output("content_strategist", success=False, error="boom")
    )
    wf.copywriter = MagicMock()
    wf.copywriter.run = AsyncMock()
    wf.editor = MagicMock()
    wf.editor.run = AsyncMock()

    result = await wf.run(title="X", description="y")

    assert result.success is False
    assert result.final_verdict.startswith("FAILED")
    wf.copywriter.run.assert_not_called()


@pytest.mark.asyncio
async def test_creative_workflow_repair_loop_reruns_copywriter_and_editor(
    settings: Settings, memory: FileMemory
) -> None:
    wf = CreativeWorkflow(memory=memory, settings=settings)
    wf.strategist = MagicMock()
    wf.strategist.run = AsyncMock(return_value=_agent_output("content_strategist"))
    wf.copywriter = MagicMock()
    wf.copywriter.run = AsyncMock(
        side_effect=[
            _agent_output("copywriter", raw_text="texte v1"),
            _agent_output("copywriter", raw_text="texte v2"),
        ]
    )
    wf.editor = MagicMock()
    wf.editor.run = AsyncMock(
        side_effect=[
            _agent_output("editor", parsed={"verdict": "NEEDS_CHANGES"}),
            _agent_output("editor", parsed={"verdict": "APPROVED", "quality_score": 0.92}),
        ]
    )

    result = await wf.run(title="X", description="y")

    assert result.final_verdict == "APPROVED"
    assert wf.copywriter.run.call_count == 2
    assert wf.editor.run.call_count == 2


@pytest.mark.asyncio
async def test_creative_workflow_killswitch_fails_early(
    settings: Settings, memory: FileMemory, tmp_path: Path
) -> None:
    ks = Killswitch(tmp_path / ".ks")
    ks.engage(reason="test creative")
    wf = CreativeWorkflow(memory=memory, settings=settings, killswitch=ks)
    wf.strategist = MagicMock()
    wf.strategist.run = AsyncMock()

    result = await wf.run(title="X", description="y")
    assert "killswitch" in result.final_verdict.lower()
    wf.strategist.run.assert_not_called()


@pytest.mark.asyncio
async def test_creative_workflow_score_propagation(settings: Settings, memory: FileMemory) -> None:
    wf = CreativeWorkflow(memory=memory, settings=settings)
    mid = uuid4()
    for agent_name in ("content_strategist", "copywriter", "editor"):
        memory.write_episode(mid, agent_name, MemoryRecord(metadata={"agent": agent_name}, body=""))

    wf.strategist = MagicMock()
    wf.strategist.run = AsyncMock(return_value=_agent_output("content_strategist"))
    wf.copywriter = MagicMock()
    wf.copywriter.run = AsyncMock(return_value=_agent_output("copywriter"))
    wf.editor = MagicMock()
    wf.editor.run = AsyncMock(
        return_value=_agent_output("editor", parsed={"verdict": "APPROVED", "quality_score": 0.88})
    )

    await wf.run(title="X", description="y", mission_id=mid)

    for ep_path in memory.list_episodes(mid):
        rec = memory.read_episode(ep_path)
        assert rec.metadata.get("quality_score") == 0.88
        assert rec.metadata.get("guild") == "creative"
