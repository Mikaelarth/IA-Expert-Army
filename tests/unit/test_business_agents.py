"""Tests pour les agents de la Guild Business + routing business."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.config import Settings
from src.guilds.business.agents import BusinessAnalyst, LegalReviewer, ProjectManager
from src.learning.pattern_miner import PatternMiner
from src.memory.file_memory import FileMemory
from src.orchestrator.router import HeuristicGuildClassifier


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def test_project_manager_uses_operational_model(settings: Settings, memory: FileMemory) -> None:
    agent = ProjectManager(memory=memory, settings=settings)
    assert "sonnet" in agent.model.lower()


def test_business_analyst_uses_strategic_model(settings: Settings, memory: FileMemory) -> None:
    agent = BusinessAnalyst(memory=memory, settings=settings)
    assert "opus" in agent.model.lower()


def test_legal_reviewer_uses_operational_model(settings: Settings, memory: FileMemory) -> None:
    agent = LegalReviewer(memory=memory, settings=settings)
    assert "sonnet" in agent.model.lower()


def test_business_agents_max_tokens_aligned() -> None:
    """max_tokens calibrés sur les leçons Research/Creative — pas de saturation surprise."""
    assert ProjectManager.DEFAULT_MAX_TOKENS >= 4096
    assert BusinessAnalyst.DEFAULT_MAX_TOKENS >= 6144
    assert LegalReviewer.DEFAULT_MAX_TOKENS >= 8192  # reviewer = aligné sur les autres


def test_business_agents_load_their_prompts(settings: Settings, memory: FileMemory) -> None:
    for agent_class in (ProjectManager, BusinessAnalyst, LegalReviewer):
        agent = agent_class(memory=memory, settings=settings)
        assert agent.system_prompt
        assert len(agent.system_prompt) > 100


def test_pattern_miner_whitelist_includes_business_agents() -> None:
    """Régression : la Business Guild doit être dans le whitelist.
    Ne pas refaire l'oubli observé sur Research et Creative."""
    for agent in ("project_manager", "business_analyst", "legal_reviewer"):
        assert agent in PatternMiner.AGENT_WHITELIST, (
            f"{agent} doit être dans le whitelist pour bénéficier du mining"
        )


# ===== Classifier tests =====


@pytest.mark.parametrize(
    "title,description,expected",
    [
        ("Roadmap MVP product launch", "3 mois, 2 devs, budget €50k", "business"),
        ("Business plan IA-Expert-Army", "Modèle économique freemium", "business"),
        ("Conformité RGPD du logging", "Audit des données collectées", "business"),
        ("Plan go-to-market", "Cible early adopters tech leads", "business"),
        # Doit toujours router vers les autres guildes quand approprié
        ("Implémente un endpoint", "FastAPI POST /create-content", "engineering"),
        ("Synthétise les patterns SEO", "État de l'art 2026", "research"),
        ("Rédige une landing page", "Pour notre nouveau SaaS", "creative"),
    ],
)
def test_classifier_routes_to_business(title: str, description: str, expected: str) -> None:
    clf = HeuristicGuildClassifier()
    assert clf.classify(title, description) == expected


def test_classifier_business_does_not_steal_engineering_intent() -> None:
    """Régression préventive : 'plan' isolé ne doit pas voler une mission engineering."""
    clf = HeuristicGuildClassifier()
    # Mission clairement Engineering (implémente + endpoint + test) avec mention de "plan"
    assert (
        clf.classify(
            "Implémente l'endpoint /plan",
            "Code FastAPI pour exposer le plan de roadmap stocké en SQL. Inclus pytest.",
        )
        == "engineering"
    )
