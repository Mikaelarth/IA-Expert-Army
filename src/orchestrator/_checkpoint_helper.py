"""Helper interne pour appliquer le checkpoint pattern aux 4 workflows guildes.

Pattern (v0.8.0 F1 Resume/Recovery) :
- Avant `agent.run()`, vérifier si un checkpoint existe pour ce step.
  - Si oui : désérialiser l'`AgentOutput` et retourner sans appeler le LLM.
  - Si non : appeler `agent.run()` normalement, puis save le résultat.
- En fin de mission réussie, le caller doit `clear()` les checkpoints.

Le helper est transparent : depuis le point de vue du Workflow, c'est juste
un wrap de `await agent.run(input)` avec un `step_index`. Si checkpoint_store
est `None`, comportement identique à un `await agent.run(input)` direct.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from src.core.checkpoint import CheckpointStore
from src.core.logging import get_logger
from src.orchestrator.base_agent import AgentInput, AgentOutput
from src.orchestrator.progress import ProgressCallback, emit, make_event

_log = get_logger("checkpoint_helper")


async def run_with_checkpoint(
    agent: Any,  # BaseAgent — duck-typed pour éviter cycle import
    agent_input: AgentInput,
    *,
    step_index: int,
    agent_name: str,
    checkpoint_store: CheckpointStore | None,
    mission_id: UUID,
    on_progress: ProgressCallback | None = None,
) -> AgentOutput:
    """Wrap un appel `await agent.run(input)` avec save/load checkpoint.

    - Si `checkpoint_store` est None → pas de checkpoint, appel direct.
    - Si un checkpoint existe pour (mission_id, step_index) → désérialisé
      et retourné sans appel LLM (économie de 30 sec à 5 min selon l'agent).
    - Sinon → appel normal, save si success.

    v0.8.0 F2 — émet des `ProgressEvent` (agent_started/resumed/completed/failed)
    si `on_progress` est fourni. Best-effort : exceptions silencieuses.
    """
    # Try resume from checkpoint (avant d'émettre agent_started)
    if checkpoint_store is not None:
        existing = _try_load(checkpoint_store, mission_id, step_index, agent_name)
        if existing is not None:
            _log.info(
                "checkpoint.resume",
                mission=str(mission_id),
                step=step_index,
                agent=agent_name,
                cached_cost_usd=existing.cost_usd,
            )
            emit(
                on_progress,
                make_event(
                    "agent_resumed",
                    f"{agent_name} restauré depuis checkpoint (skip LLM)",
                    step_index=step_index,
                    agent_name=agent_name,
                ),
            )
            return existing

    # Pas de cache → appel normal
    emit(
        on_progress,
        make_event(
            "agent_started",
            f"{agent_name} démarre",
            step_index=step_index,
            agent_name=agent_name,
        ),
    )
    output = await agent.run(agent_input)

    if output.success:
        emit(
            on_progress,
            make_event(
                "agent_completed",
                f"{agent_name} terminé ({output.tokens_out} tokens, ${output.cost_usd:.4f})",
                step_index=step_index,
                agent_name=agent_name,
                tokens_in=output.tokens_in,
                tokens_out=output.tokens_out,
                cost_usd=output.cost_usd,
                duration_seconds=output.duration_seconds,
                saturated=output.saturated,
            ),
        )
        if checkpoint_store is not None:
            checkpoint_store.save(
                mission_id=str(mission_id),
                step_index=step_index,
                agent_name=agent_name,
                agent_output=output,
            )
    else:
        emit(
            on_progress,
            make_event(
                "agent_failed",
                f"{agent_name} a échoué : {output.error or 'erreur inconnue'}",
                step_index=step_index,
                agent_name=agent_name,
                error=output.error,
            ),
        )
    return output


def _try_load(
    store: CheckpointStore,
    mission_id: UUID,
    step_index: int,
    agent_name: str,
) -> AgentOutput | None:
    """Cherche un checkpoint pour (mission_id, step_index) et le désérialise.

    Tolérant : si la désérialisation échoue (format ancien, champ manquant),
    retourne None et le caller fera l'appel LLM normalement.
    """
    checkpoints = store.load_all(str(mission_id))
    for cp in checkpoints:
        if cp.get("step_index") == step_index and cp.get("agent_name") == agent_name:
            data = cp.get("agent_output")
            if not isinstance(data, dict):
                return None
            try:
                return AgentOutput.model_validate(data)
            except Exception as exc:
                _log.warning(
                    "checkpoint.deserialize.failed",
                    mission=str(mission_id),
                    step=step_index,
                    agent=agent_name,
                    error=str(exc),
                )
                return None
    return None
