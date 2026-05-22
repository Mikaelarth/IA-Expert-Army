"""Tests v0.8.0 F2 — ProgressEvent + streaming live des missions.

Valide :
- L'émission des events via `emit()` (best-effort, exceptions silencieuses).
- Le workflow Engineering émet les bons events à chaque étape.
- `run_mission_streaming` retourne bien des events puis le MissionRunOutcome
  final, sans deadlock entre thread worker et main thread.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import Settings
from src.memory.file_memory import FileMemory
from src.orchestrator.base_agent import AgentOutput
from src.orchestrator.progress import ProgressEvent, emit, make_event

# ----------------------------------------------------------------------------
# Émetteur de base
# ----------------------------------------------------------------------------


def test_emit_with_none_callback_is_noop() -> None:
    """Un callback None ne doit pas lever — emit() retourne None silencieusement."""
    result = emit(None, make_event("mission_started", "test"))
    assert result is None


def test_emit_swallows_callback_exceptions() -> None:
    """Si le callback lève, emit() doit avaler — le streaming ne doit JAMAIS
    casser la mission. On valide en exécutant 3× sur un callback crashant."""

    n_calls = []

    def broken_callback(_event: ProgressEvent) -> None:
        n_calls.append(1)
        raise RuntimeError("callback crashed")

    for _ in range(3):
        emit(broken_callback, make_event("mission_started", "test"))

    # Le callback a bien été appelé 3 fois, et emit() n'a pas levé
    assert len(n_calls) == 3


def test_emit_calls_callback_with_event() -> None:
    received: list[ProgressEvent] = []
    emit(received.append, make_event("agent_started", "hello", step_index=2, agent_name="dev"))

    assert len(received) == 1
    assert received[0].event_type == "agent_started"
    assert received[0].message == "hello"
    assert received[0].data == {"step_index": 2, "agent_name": "dev"}


# ----------------------------------------------------------------------------
# Workflow émission événements
# ----------------------------------------------------------------------------


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def _fake_output(text: str, parsed: object = None) -> AgentOutput:
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


@pytest.mark.asyncio
async def test_workflow_emits_progress_events(
    memory: FileMemory,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un workflow nominal (4 agents APPROVED) doit émettre dans l'ordre :
    mission_started, 4×(agent_started, agent_completed), mission_completed.
    """
    from src.orchestrator.workflow import Workflow

    wf = Workflow(memory=memory, settings=settings)

    monkeypatch.setattr(
        wf.orchestrator,
        "run",
        AsyncMock(return_value=_fake_output("o", parsed={"subtasks": [{"task": "t"}]})),
    )
    monkeypatch.setattr(wf.architect, "run", AsyncMock(return_value=_fake_output("a")))
    monkeypatch.setattr(
        wf.developer,
        "run",
        AsyncMock(return_value=_fake_output("d", parsed=[{"path": "src/x.py", "content": "x"}])),
    )
    monkeypatch.setattr(
        wf.reviewer,
        "run",
        AsyncMock(
            return_value=_fake_output(
                "r", parsed={"verdict": "APPROVED", "quality_score": 0.91, "summary": "ok"}
            )
        ),
    )

    captured: list[ProgressEvent] = []
    await wf.run(title="test", description="desc", on_progress=captured.append)

    types_seen = [e.event_type for e in captured]
    assert types_seen[0] == "mission_started"
    assert types_seen[-1] == "mission_completed"
    # Au moins 4 paires (agent_started, agent_completed)
    assert types_seen.count("agent_started") == 4
    assert types_seen.count("agent_completed") == 4


@pytest.mark.asyncio
async def test_workflow_emits_agent_resumed_when_checkpoint_exists(
    memory: FileMemory,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si un agent est restauré depuis checkpoint, on émet `agent_resumed`
    (et pas `agent_started`)."""
    from src.core.checkpoint import CheckpointStore
    from src.orchestrator.workflow import Workflow

    cs = CheckpointStore(tmp_path / "checkpoints")
    mission_id = uuid4()

    # Pré-existence : orchestrator + architect dans cache
    cs.save(
        str(mission_id),
        0,
        "chief_orchestrator",
        _fake_output("orch cached", parsed={"subtasks": [{"task": "t"}]}),
    )
    cs.save(str(mission_id), 1, "software_architect", _fake_output("arch cached"))

    wf = Workflow(memory=memory, settings=settings, checkpoint_store=cs)

    monkeypatch.setattr(wf.orchestrator, "run", AsyncMock(return_value=_fake_output("nope")))
    monkeypatch.setattr(wf.architect, "run", AsyncMock(return_value=_fake_output("nope")))
    monkeypatch.setattr(
        wf.developer,
        "run",
        AsyncMock(return_value=_fake_output("d", parsed=[{"path": "src/x.py", "content": "x"}])),
    )
    monkeypatch.setattr(
        wf.reviewer,
        "run",
        AsyncMock(
            return_value=_fake_output(
                "r", parsed={"verdict": "APPROVED", "quality_score": 0.9, "summary": "ok"}
            )
        ),
    )

    captured: list[ProgressEvent] = []
    await wf.run(
        title="resume test",
        description="desc",
        mission_id=mission_id,
        on_progress=captured.append,
    )

    types_seen = [e.event_type for e in captured]
    # Exactement 2 agent_resumed (orchestrator + architect) et 2 agent_started (dev + reviewer)
    assert types_seen.count("agent_resumed") == 2
    assert types_seen.count("agent_started") == 2
    assert types_seen.count("agent_completed") == 2  # uniquement les vraiment exécutés


# ----------------------------------------------------------------------------
# Streaming via thread + queue
# ----------------------------------------------------------------------------


def test_run_mission_streaming_yields_events_then_outcome(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`run_mission_streaming` doit retourner d'abord des ProgressEvents,
    puis terminer par un MissionRunOutcome. Le worker thread doit cleanly
    terminer sans deadlock.
    """
    from src.gui.services.mission_runner import (
        MissionRunOutcome,
        MissionRunRequest,
        run_mission_streaming,
    )
    from src.orchestrator.router import UnifiedMissionResult

    # Mock le router pour éviter tout vrai appel Ollama
    fake_result = UnifiedMissionResult(
        mission_id=str(uuid4()),
        title="test",
        guild="engineering",
        success=True,
        final_verdict="APPROVED",
        quality_score=0.92,
        total_cost_usd=0.0,
        total_duration_seconds=0.1,
        summary="ok",
        raw_result={"files_produced": []},
    )

    async def fake_router_run(
        self, title, description, force_guild=None, *, mission_id=None, on_progress=None
    ):
        # Émet 2 events simulés
        if on_progress is not None:
            on_progress(make_event("mission_started", "demo", title=title))
            on_progress(make_event("agent_completed", "fake done", agent_name="x"))
        return fake_result

    from src.orchestrator.router import MissionRouter

    monkeypatch.setattr(MissionRouter, "run", fake_router_run)

    req = MissionRunRequest(title="streaming test", description="desc")

    items = list(run_mission_streaming(req, poll_interval_s=0.1))

    # Doit contenir au moins 2 ProgressEvent + 1 MissionRunOutcome
    events = [i for i in items if isinstance(i, ProgressEvent)]
    outcomes = [i for i in items if isinstance(i, MissionRunOutcome)]

    assert len(events) >= 2
    assert len(outcomes) == 1
    assert outcomes[0].result.final_verdict == "APPROVED"
    # L'outcome doit être en dernière position
    assert isinstance(items[-1], MissionRunOutcome)


def test_run_mission_streaming_handles_worker_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si le router crashe, le streaming doit yield un MissionRunOutcome
    avec verdict='CRASH' au lieu de figer le caller."""
    from src.gui.services.mission_runner import (
        MissionRunOutcome,
        MissionRunRequest,
        run_mission_streaming,
    )
    from src.orchestrator.router import MissionRouter

    async def crashing_run(self, *args, **kwargs):
        raise RuntimeError("router boom")

    monkeypatch.setattr(MissionRouter, "run", crashing_run)

    req = MissionRunRequest(title="crash test", description="desc")
    items = list(run_mission_streaming(req, poll_interval_s=0.1))

    outcomes = [i for i in items if isinstance(i, MissionRunOutcome)]
    assert len(outcomes) == 1
    assert outcomes[0].result.final_verdict == "CRASH"
    assert "RuntimeError" in outcomes[0].result.summary
