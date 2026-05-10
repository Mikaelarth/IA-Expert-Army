"""Test régression pour SkillExtractor max_tokens."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.core.config import Settings
from src.learning.skill_extractor import SkillExtractor
from src.memory.file_memory import FileMemory


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def test_skill_extractor_max_tokens_high_enough_for_full_yaml(
    settings: Settings, memory: FileMemory
) -> None:
    """Régression : extraire une skill depuis 3+ épisodes massifs produit un YAML
    avec N key_patterns + N techniques + N pitfalls + example_template qui
    saturait à 2048 tokens. 2/3 skills perdues sur le mining d'avril 2026
    (research_lead + tech_watch, $0.87 wasted, YAML tronqué non parseable).
    Minimum sûr empirique : 4096."""
    agent = SkillExtractor(memory=memory, settings=settings)
    assert agent.max_tokens >= 4096


def test_skill_extractor_does_not_use_vector_memory(
    settings: Settings, memory: FileMemory
) -> None:
    """Le SkillExtractor ne doit PAS recevoir de VectorMemory pour éviter
    une boucle d'auto-influence (ses propres skills extraites alimenteraient
    ses futures extractions)."""
    agent = SkillExtractor(memory=memory, settings=settings)
    assert agent.vector_memory is None


def test_skill_extractor_does_not_use_skills_library(
    settings: Settings, memory: FileMemory
) -> None:
    """Pareil pour SkillsLibrary : pas d'auto-influence."""
    agent = SkillExtractor(memory=memory, settings=settings)
    assert agent.skills_library is None
