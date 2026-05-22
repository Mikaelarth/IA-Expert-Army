"""Progress events — flux d'observation pour suivre une mission en direct.

v0.8.0 F2 — adresse le pain point "spinner aveugle 20-40 min" : pendant
qu'une mission tourne, on veut voir quel agent travaille, combien de tokens
ont été générés, à quelle étape on est.

Architecture minimaliste : un Callable injecté dans Workflow/Router qui est
appelé synchroniquement à chaque évènement notable. Le caller (GUI Streamlit,
CLI, tests) implémente la consommation (queue, log, print, st.status…).

Pas de dépendance asyncio dans ce module — c'est un simple Callable
synchrone (best-effort, non-bloquant). Si le callback lève, on l'avale
silencieusement pour ne pas casser la mission.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

# Types d'évènements émis pendant une mission. Volontairement plat (pas de
# hiérarchie de classes) pour faciliter la sérialisation JSON et le matching
# côté GUI.
EventType = Literal[
    "mission_started",  # début de la mission, avant routing
    "mission_routed",  # router a tranché la guilde
    "agent_started",  # agent N va commencer
    "agent_resumed",  # agent N restauré depuis checkpoint (skip LLM)
    "agent_completed",  # agent N a terminé avec succès
    "agent_failed",  # agent N a échoué
    "repair_loop_started",  # entrée dans le repair loop Engineering
    "mission_completed",  # mission terminée (succès ou échec final)
]


@dataclass
class ProgressEvent:
    """Un évènement émis pendant l'exécution d'une mission.

    `data` est volontairement libre — chaque caller met ce qui est pertinent
    (agent_name, step_index, tokens, cost_usd, verdict, etc.). La GUI sait
    formater chaque event_type spécifiquement.
    """

    event_type: EventType
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


# Type alias for the callback that consumers register
ProgressCallback = Callable[[ProgressEvent], None]


def emit(callback: ProgressCallback | None, event: ProgressEvent) -> None:
    """Wrap un appel callback en best-effort : si callback est None, no-op ;
    si callback lève, on avale (le streaming ne doit jamais casser la mission).
    """
    if callback is None:
        return
    # Best-effort : si le callback lève, on avale silencieusement — le streaming
    # ne doit JAMAIS casser la mission. Pas de log noisy.
    with contextlib.suppress(Exception):
        callback(event)


def make_event(
    event_type: EventType,
    message: str = "",
    **data: Any,
) -> ProgressEvent:
    """Helper court pour construire un ProgressEvent.

    Usage : ``emit(cb, make_event("agent_started", "Architect démarre", step_index=1))``
    """
    return ProgressEvent(event_type=event_type, message=message, data=data)
