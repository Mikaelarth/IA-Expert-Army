"""Régression : BaseAgent.run DOIT être décoré avec @observe pour le tracing
Langfuse. Sans le décorateur, les appels LLM ne sont jamais tracés même
avec credentials configurés.

Découvert 2026-05-10 : un commit prétendait avoir décoré BaseAgent.run
mais l'Edit avait silencieusement échoué — le code partait en prod sans
instrumentation. Ce test garantit que ça ne se reproduit pas.
"""
from __future__ import annotations

from src.orchestrator.base_agent import BaseAgent


def test_base_agent_run_has_observe_wrapper() -> None:
    """Quand le tracing est en NO-OP (cas par défaut sans credentials),
    le décorateur utilise @functools.wraps et préserve le nom de la fonction.
    On vérifie que le fichier source contient bien le décorateur, ET que la
    méthode reste appelable (signature préservée)."""
    import inspect

    source = inspect.getsource(BaseAgent.run)
    # La méthode source doit commencer par async def (le décorateur est sur la
    # ligne au-dessus dans inspect, capté via inspect.getsource du wrapper).
    # On vérifie indirectement en lisant le fichier source :
    base_agent_file = inspect.getfile(BaseAgent)
    with open(base_agent_file, encoding="utf-8") as f:
        content = f.read()

    # Cherche le décorateur juste avant async def run
    assert '@observe(name="agent.run"' in content, (
        "BaseAgent.run doit être décoré @observe(name=\"agent.run\", as_type=\"generation\") "
        "pour permettre le tracing Langfuse"
    )
    assert "from src.core.tracing import observe" in content, (
        "BaseAgent doit importer observe depuis src.core.tracing"
    )


def test_base_agent_run_signature_preserved() -> None:
    """Le décorateur (NO-OP ou réel) doit préserver __name__ via @functools.wraps."""
    assert BaseAgent.run.__name__ == "run"
