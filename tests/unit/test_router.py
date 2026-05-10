"""Tests pour src.orchestrator.router — classifieur + dispatch."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.config import Settings
from src.memory.file_memory import FileMemory
from src.orchestrator.router import (
    HeuristicGuildClassifier,
    MissionRouter,
    RoutingDecision,
)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


# ===== Classifier tests =====


@pytest.mark.parametrize(
    "title,description,expected",
    [
        ("Endpoint /health", "Crée un endpoint FastAPI", "engineering"),
        ("Refactor auth module", "Implémente la nouvelle classe AuthService", "engineering"),
        ("Add pytest tests", "Couvre le module foo avec pytest", "engineering"),
        ("Compare frameworks Python", "Quelles sont les options 2026 ?", "research"),
        ("Synthétise les best practices REST", "Veille sur l'état de l'art", "research"),
        ("Rapport benchmark vector DBs", "Analyse comparatif", "research"),
        ("État de l'art multi-agents", "Veille tech 2026", "research"),
        ("Plain query", "Hello world", "engineering"),  # default
    ],
)
def test_classifier_categorizes_correctly(title: str, description: str, expected: str) -> None:
    clf = HeuristicGuildClassifier()
    assert clf.classify(title, description) == expected


def test_classifier_engineering_priority_on_tie() -> None:
    """Engineering wins en cas d'égalité PARFAITE (ADR-001 : guilde la plus mature).

    Note : avec les verbes d'action forts (compare, synthétise, implémente…) qui
    surpondèrent (+2), construire un vrai tie est plus subtil. Cas non-ambigu :
    aucun keyword nulle part → eng par défaut.
    """
    clf = HeuristicGuildClassifier()
    # Aucun keyword nulle part → eng par défaut
    assert clf.classify("hello", "world") == "engineering"
    # Tie parfait : 1 mot-clé "weak" research + 1 mot-clé "weak" eng dans le body
    # ("guide" weak research, "module" weak eng) → 1 vs 1 → eng wins
    assert clf.classify("Mission neutre", "guide pour le module") == "engineering"


def test_classifier_strong_action_verb_beats_noun_keyword() -> None:
    """Régression mission 7c98893b (observabilité) : 'synthétise' (verbe action forte)
    doit l'emporter sur 'code' (nom commun) malgré le tie-break engineering."""
    clf = HeuristicGuildClassifier()
    title = "Patterns d'observabilité pour équipe d'agents IA en production"
    desc = (
        "Synthétise les patterns d'observabilité éprouvés en 2026. "
        "Mentionne aussi les anti-patterns dans le code applicatif."
    )
    assert clf.classify(title, desc) == "research"


def test_classifier_engineering_action_verb_wins_over_research_noun() -> None:
    """Symétrie : 'implémente' verbe action engineering forte > nom 'comparaison' research."""
    clf = HeuristicGuildClassifier()
    assert clf.classify("Mission", "implémente une comparaison rapide") == "engineering"


def test_classifier_word_boundary_avoids_false_positives() -> None:
    """`api` ne doit PAS matcher `rapide`."""
    clf = HeuristicGuildClassifier()
    # "rapide" contient "api" en substring mais pas comme mot
    assert clf.classify("Mission rapide", "Compare deux options") == "research"


def test_classifier_unique_keywords_prevents_repetition_bias() -> None:
    """Régression : une mission research mentionnant 'test' 5 fois ne doit pas
    être classée engineering juste à cause de la répétition du mot."""
    clf = HeuristicGuildClassifier()
    title = "Synthétise les meilleures pratiques de test"
    description = (
        "Couvre : stratégies de test, organisation des tests, mocks pour test, "
        "fixtures de test, intégration continue des tests."
    )
    assert clf.classify(title, description) == "research"


def test_classifier_meta_software_mission_routes_to_research() -> None:
    """Régression du bug initial : titre 'Structurer un projet Python multi-agents'
    avec description évoquant des concepts logiciels doit rester Research."""
    clf = HeuristicGuildClassifier()
    title = "Structurer un projet Python multi-agents"
    description = (
        "Synthétise les meilleures pratiques 2026 pour structurer un projet "
        "Python d'agents IA. Couvre : organisation des modules, gestion de la "
        "mémoire, patterns d'orchestration, stratégies de test, observabilité."
    )
    assert clf.classify(title, description) == "research"


def test_classifier_title_keywords_weighted_double() -> None:
    """Un mot-clé research dans le titre doit peser plus qu'un mot-clé eng dans le body."""
    clf = HeuristicGuildClassifier()
    # Titre research, body engineering — research doit gagner grâce au poids du titre
    assert clf.classify("Compare two options", "module foo with test cases") == "research"
    # Titre engineering, body research — engineering doit gagner
    assert (
        clf.classify("Implement a function", "compare with research alternatives") == "engineering"
    )


# ===== Router decide() =====


def test_router_decide_returns_routing_decision(memory: FileMemory, settings: Settings) -> None:
    router = MissionRouter(memory=memory, settings=settings)
    d = router.decide("Compare frameworks", "Quels options ?")
    assert isinstance(d, RoutingDecision)
    assert d.guild == "research"
    assert "heuristic" in d.reason


def test_router_decide_respects_force_guild(memory: FileMemory, settings: Settings) -> None:
    router = MissionRouter(memory=memory, settings=settings)
    d = router.decide("Endpoint", "Crée un endpoint", force_guild="research")
    assert d.guild == "research"
    assert "forced" in d.reason


# ===== Router dispatch (mocked workflows) =====


def _patch_engineering(monkeypatch: pytest.MonkeyPatch, fake_result) -> None:
    """Remplace EngineeringWorkflow par un fake qui retourne fake_result."""

    class FakeWf:
        def __init__(self, **kwargs):
            self.captured = kwargs

        async def run(self, title: str, description: str):
            return fake_result

    monkeypatch.setattr("src.orchestrator.router.Workflow", FakeWf)


def _patch_research(monkeypatch: pytest.MonkeyPatch, fake_result) -> None:
    class FakeWf:
        def __init__(self, **kwargs):
            self.captured = kwargs

        async def run(self, title: str, description: str, mission_id=None):
            return fake_result

    monkeypatch.setattr("src.orchestrator.router.ResearchWorkflow", FakeWf)


def test_router_dispatches_to_engineering(
    monkeypatch: pytest.MonkeyPatch, memory: FileMemory, settings: Settings
) -> None:
    from src.orchestrator.workflow import MissionResult

    fake = MissionResult(
        mission_id=uuid4(),
        title="t",
        success=True,
        final_verdict="APPROVED",
        quality_score=0.9,
        total_cost_usd=0.1,
        total_duration_seconds=1.0,
        files_produced=[{"path": "src/x.py", "language": "python", "content": "ok"}],
        review_summary="ok",
        episodes_count=4,
    )
    _patch_engineering(monkeypatch, fake)
    router = MissionRouter(memory=memory, settings=settings)
    result = asyncio.run(router.run("Endpoint /health", "Crée un endpoint FastAPI"))
    assert result.guild == "engineering"
    assert result.success is True
    assert result.raw_result["files_produced"][0]["path"] == "src/x.py"


def test_router_dispatches_to_research(
    monkeypatch: pytest.MonkeyPatch, memory: FileMemory, settings: Settings
) -> None:
    from src.guilds.research.workflow import ResearchMissionResult

    fake = ResearchMissionResult(
        mission_id=uuid4(),
        title="t",
        success=True,
        final_verdict="APPROVED",
        quality_score=0.88,
        total_cost_usd=0.15,
        total_duration_seconds=2.0,
        synthesis_markdown="# TL;DR\n\nResult.",
        review_summary="ok",
        episodes_count=4,
    )
    _patch_research(monkeypatch, fake)
    router = MissionRouter(memory=memory, settings=settings)
    result = asyncio.run(router.run("Compare frameworks Python", "Synthétise les options 2026"))
    assert result.guild == "research"
    assert "TL;DR" in result.raw_result["synthesis_markdown"]
