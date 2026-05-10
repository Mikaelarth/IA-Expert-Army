"""Tests pour les agents de la Guild Creative + routing creative."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.config import Settings
from src.guilds.creative.agents import ContentStrategist, Copywriter, Editor
from src.memory.file_memory import FileMemory
from src.orchestrator.router import HeuristicGuildClassifier


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def test_content_strategist_uses_strategic_model(settings: Settings, memory: FileMemory) -> None:
    agent = ContentStrategist(memory=memory, settings=settings)
    assert "opus" in agent.model.lower()


def test_copywriter_uses_operational_model(settings: Settings, memory: FileMemory) -> None:
    agent = Copywriter(memory=memory, settings=settings)
    assert "sonnet" in agent.model.lower()


def test_editor_uses_operational_model(settings: Settings, memory: FileMemory) -> None:
    agent = Editor(memory=memory, settings=settings)
    assert "sonnet" in agent.model.lower()


def test_creative_agents_max_tokens_aligned() -> None:
    """Tous les Creative agents partagent les valeurs max_tokens validées en Research."""
    assert ContentStrategist.DEFAULT_MAX_TOKENS >= 3072
    assert Copywriter.DEFAULT_MAX_TOKENS >= 8192  # texte long
    assert Editor.DEFAULT_MAX_TOKENS >= 8192  # verdict avec issues détaillées


def test_creative_agents_load_their_prompts(settings: Settings, memory: FileMemory) -> None:
    for agent_class in (ContentStrategist, Copywriter, Editor):
        agent = agent_class(memory=memory, settings=settings)
        assert agent.system_prompt
        assert len(agent.system_prompt) > 100


# ===== Classifier tests =====


@pytest.mark.parametrize(
    "title,description,expected",
    [
        ("Rédige une landing page", "Pour notre nouveau SaaS", "creative"),
        ("Compose un email marketing", "Cible : early adopters", "creative"),
        ("Écris un blog post sur X", "Audience : devs juniors", "creative"),
        ("Pitch produit en 200 mots", "Pour l'investor day", "creative"),
        # Doit toujours router vers les autres guildes quand approprié
        ("Implémente un endpoint", "FastAPI POST /create-content", "engineering"),
        ("Synthétise les best practices SEO", "État de l'art 2026", "research"),
    ],
)
def test_classifier_routes_to_creative(title: str, description: str, expected: str) -> None:
    clf = HeuristicGuildClassifier()
    assert clf.classify(title, description) == expected


def test_classifier_creative_action_verb_in_title_dominates() -> None:
    """'Rédige' (verbe creative fort) dans le titre l'emporte sur des keywords research dans le body."""
    clf = HeuristicGuildClassifier()
    assert (
        clf.classify(
            "Rédige une newsletter",
            "Synthétise les meilleures pratiques marketing pour la cible",
        )
        == "creative"
    )
