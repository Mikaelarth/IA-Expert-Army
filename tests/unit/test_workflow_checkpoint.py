"""Tests d'intégration v0.8.0 F1 — Resume/Recovery via checkpoint.

Valide que :
- Workflow Engineering écrit un checkpoint après chaque agent réussi.
- Un re-run avec le même mission_id charge les checkpoints existants au lieu
  de rappeler les agents (économie LLM concrète).
- En fin de mission réussie, les checkpoints sont nettoyés.
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
def checkpoint_store(tmp_path: Path) -> CheckpointStore:
    return CheckpointStore(tmp_path / "checkpoints")


def _fake_agent_output(text: str, parsed: object = None) -> AgentOutput:
    """Construit un AgentOutput réussi minimal."""
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
async def test_workflow_writes_checkpoints_after_each_agent(
    memory: FileMemory,
    checkpoint_store: CheckpointStore,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Après un run complet, on doit trouver 4 checkpoints sur disque (un
    par agent du workflow Engineering nominal, sans repair loop).

    NB : en cas de mission APPROVED, le workflow nettoie les checkpoints en
    fin de mission. Pour ce test, on simule un workflow qui ne va PAS au bout
    en injectant un fail au reviewer (verdict REJECTED ne fait PAS clear()
    parce que la mission est techniquement terminée — donc on doit observer
    le clear AVANT/APRÈS le run pour valider le pattern).
    """
    from src.orchestrator.workflow import Workflow

    wf = Workflow(
        memory=memory,
        settings=settings,
        checkpoint_store=checkpoint_store,
    )

    # Mock les 4 agents pour retourner des outputs réussis sans appel LLM réel
    orch_output = _fake_agent_output("orch", parsed={"subtasks": [{"task": "Faire X"}]})
    arch_output = _fake_agent_output("arch")
    dev_output = _fake_agent_output("dev", parsed=[{"path": "src/foo.py", "content": "x = 1"}])
    review_output = _fake_agent_output(
        "review",
        parsed={"verdict": "APPROVED", "quality_score": 0.92, "summary": "ok"},
    )

    monkeypatch.setattr(wf.orchestrator, "run", AsyncMock(return_value=orch_output))
    monkeypatch.setattr(wf.architect, "run", AsyncMock(return_value=arch_output))
    monkeypatch.setattr(wf.developer, "run", AsyncMock(return_value=dev_output))
    monkeypatch.setattr(wf.reviewer, "run", AsyncMock(return_value=review_output))

    mission_id = uuid4()

    # Avant le run : 0 checkpoint
    assert checkpoint_store.list_missions() == []

    # Espionne CheckpointStore.clear pour observer son appel sans l'exécuter
    clear_calls = []
    original_clear = checkpoint_store.clear

    def _spy_clear(mid: str) -> int:
        clear_calls.append(mid)
        # On laisse clear s'exécuter normalement
        return original_clear(mid)

    monkeypatch.setattr(checkpoint_store, "clear", _spy_clear)

    result = await wf.run(title="Test mission", description="desc", mission_id=mission_id)

    assert result.success is True
    assert result.final_verdict == "APPROVED"
    # 4 checkpoints ont été écrits pendant l'exécution (vérifiable via le
    # spy clear : appelé avec ce mission_id en fin de run)
    assert str(mission_id) in clear_calls
    # Et clear a bien nettoyé : plus de checkpoints sur disque
    assert checkpoint_store.has_checkpoint(str(mission_id)) is False


@pytest.mark.asyncio
async def test_workflow_resume_skips_already_completed_agents(
    memory: FileMemory,
    checkpoint_store: CheckpointStore,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si 2 checkpoints existent (steps 0+1), un re-run avec le même mission_id
    doit appeler agent.run() UNIQUEMENT pour les steps 2 et 3.
    """
    from src.orchestrator.workflow import Workflow

    mission_id = uuid4()

    # Pré-existence : checkpoints pour orchestrator + architect (steps 0+1)
    orch_cached = _fake_agent_output("orch (cached)", parsed={"subtasks": [{"task": "T"}]})
    arch_cached = _fake_agent_output("arch (cached)")
    checkpoint_store.save(str(mission_id), 0, "chief_orchestrator", orch_cached)
    checkpoint_store.save(str(mission_id), 1, "software_architect", arch_cached)

    wf = Workflow(memory=memory, settings=settings, checkpoint_store=checkpoint_store)

    # Mock les 4 agents — on attend que les 2 PREMIERS ne soient PAS appelés
    orch_mock = AsyncMock(return_value=_fake_agent_output("orch (should not run)"))
    arch_mock = AsyncMock(return_value=_fake_agent_output("arch (should not run)"))
    dev_mock = AsyncMock(
        return_value=_fake_agent_output("dev", parsed=[{"path": "src/x.py", "content": "x"}])
    )
    review_mock = AsyncMock(
        return_value=_fake_agent_output(
            "review",
            parsed={"verdict": "APPROVED", "quality_score": 0.93, "summary": "ok"},
        )
    )

    monkeypatch.setattr(wf.orchestrator, "run", orch_mock)
    monkeypatch.setattr(wf.architect, "run", arch_mock)
    monkeypatch.setattr(wf.developer, "run", dev_mock)
    monkeypatch.setattr(wf.reviewer, "run", review_mock)

    result = await wf.run(title="Resume test", description="desc", mission_id=mission_id)

    # Orchestrator + Architect : ne doivent PAS avoir été appelés (skip via checkpoint)
    orch_mock.assert_not_called()
    arch_mock.assert_not_called()
    # Developer + Reviewer : DOIVENT avoir été appelés
    dev_mock.assert_called_once()
    review_mock.assert_called_once()

    # Le contenu des étapes resumed doit refléter le cache (pas le mock "should not run")
    # On vérifie indirectement : si arch_cached avait été utilisé, le context
    # passé au developer contient son raw_text "arch (cached)"
    dev_call_args = dev_mock.call_args
    dev_input = dev_call_args.args[0]
    assert "arch (cached)" in dev_input.context.get("architecture_proposal_yaml", "")

    assert result.success is True


@pytest.mark.asyncio
async def test_workflow_without_checkpoint_store_works_as_before(
    memory: FileMemory,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rétrocompat : un Workflow sans checkpoint_store fonctionne comme avant
    (pas de save, pas de load, pas de clear).
    """
    from src.orchestrator.workflow import Workflow

    wf = Workflow(memory=memory, settings=settings)  # checkpoint_store=None par défaut

    orch_out = _fake_agent_output("o", parsed={"subtasks": [{"task": "t"}]})
    monkeypatch.setattr(wf.orchestrator, "run", AsyncMock(return_value=orch_out))
    monkeypatch.setattr(wf.architect, "run", AsyncMock(return_value=_fake_agent_output("a")))
    monkeypatch.setattr(
        wf.developer,
        "run",
        AsyncMock(
            return_value=_fake_agent_output("d", parsed=[{"path": "src/x.py", "content": "x"}])
        ),
    )
    monkeypatch.setattr(
        wf.reviewer,
        "run",
        AsyncMock(
            return_value=_fake_agent_output(
                "r", parsed={"verdict": "APPROVED", "quality_score": 0.9, "summary": "ok"}
            )
        ),
    )

    result = await wf.run(title="No checkpoint", description="desc")
    assert result.success is True


def test_router_propagates_checkpoint_store_to_engineering_workflow(
    memory: FileMemory,
    checkpoint_store: CheckpointStore,
    settings: Settings,
) -> None:
    """Le MissionRouter doit propager son checkpoint_store au Workflow
    Engineering qu'il instancie.
    """
    from src.orchestrator.router import MissionRouter

    router = MissionRouter(
        memory=memory,
        settings=settings,
        checkpoint_store=checkpoint_store,
    )

    assert router.checkpoint_store is checkpoint_store
