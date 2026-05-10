"""Tests pour les agents de la Guild Research.

Phase 4 — vérifications structurelles (pas d'appel Claude réel)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.core.config import Settings
from src.guilds.research.agents import (
    DocumentSynthesizer,
    ResearchLead,
    ResearchReviewer,
    TechWatch,
)
from src.memory.file_memory import FileMemory


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def test_research_lead_uses_strategic_model(settings: Settings, memory: FileMemory) -> None:
    agent = ResearchLead(memory=memory, settings=settings)
    assert "opus" in agent.model.lower()


def test_tech_watch_uses_bulk_model(settings: Settings, memory: FileMemory) -> None:
    agent = TechWatch(memory=memory, settings=settings)
    assert "haiku" in agent.model.lower()


def test_tech_watch_max_tokens_high_enough_for_multi_subquestion_plans(
    settings: Settings, memory: FileMemory
) -> None:
    """Régression : un plan à 5-6 sous-questions saturait à max_tokens=4096
    (mission 7b5759b1, coupé à mi-SQ4 → SQ5/SQ6 manquantes → REJECTED).
    Le minimum sûr observé empiriquement est 8192."""
    agent = TechWatch(memory=memory, settings=settings)
    assert agent.max_tokens >= 8192, (
        "Tech Watch a saturé en production avec 4096 tokens. "
        "Ne descends pas en dessous de 8192 sans réviser tech_watch.md "
        "pour réduire la verbosité."
    )


def test_document_synthesizer_uses_operational_model(
    settings: Settings, memory: FileMemory
) -> None:
    agent = DocumentSynthesizer(memory=memory, settings=settings)
    assert "sonnet" in agent.model.lower()


def test_research_reviewer_uses_operational_model(
    settings: Settings, memory: FileMemory
) -> None:
    agent = ResearchReviewer(memory=memory, settings=settings)
    assert "sonnet" in agent.model.lower()


def test_research_reviewer_max_tokens_high_enough_for_detailed_reviews(
    settings: Settings, memory: FileMemory
) -> None:
    """Régression : un YAML reviewer avec 6+ issues détaillées (chacune avec
    severity + category + location + message + suggestion) saturait à 2048
    (mission 359bfa08), tronquait le YAML, faisait échouer le parser et
    retournait verdict default REJECTED. Minimum sûr empirique : 4096."""
    agent = ResearchReviewer(memory=memory, settings=settings)
    assert agent.max_tokens >= 4096


def test_research_lead_max_tokens_high_enough_for_rich_plans(
    settings: Settings, memory: FileMemory
) -> None:
    """Régression préventive : plans riches à 5-6 sous-questions + sources
    + criteria + risks atteignaient ~2048 tokens. Marge à 3072."""
    agent = ResearchLead(memory=memory, settings=settings)
    assert agent.max_tokens >= 3072


def test_all_research_agents_have_distinct_names(
    settings: Settings, memory: FileMemory
) -> None:
    names = {
        ResearchLead(memory=memory, settings=settings).name,
        TechWatch(memory=memory, settings=settings).name,
        DocumentSynthesizer(memory=memory, settings=settings).name,
        ResearchReviewer(memory=memory, settings=settings).name,
    }
    assert len(names) == 4


def test_all_research_agents_load_their_prompts(
    settings: Settings, memory: FileMemory
) -> None:
    """Vérifie que chaque agent trouve bien son fichier prompt et le charge."""
    for agent_class in (ResearchLead, TechWatch, DocumentSynthesizer, ResearchReviewer):
        agent = agent_class(memory=memory, settings=settings)
        # Le system_prompt doit contenir le titre du rôle
        assert agent.system_prompt
        assert len(agent.system_prompt) > 100
