"""Tests max_tokens pour les agents Engineering — fix préventif aligné Research."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.config import Settings
from src.memory.file_memory import FileMemory
from src.orchestrator.agents import BackendDeveloper, CodeReviewer


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def test_code_reviewer_max_tokens_aligned_with_research_reviewer(
    settings: Settings, memory: FileMemory
) -> None:
    """Le CodeReviewer doit avoir au moins autant de marge que le ResearchReviewer.
    Fix préventif aligné après les 2 incidents research (359bfa08 puis 38fd387d).
    Minimum : 8192."""
    agent = CodeReviewer(memory=memory, settings=settings)
    assert agent.max_tokens >= 8192


def test_backend_developer_max_tokens_high_enough_for_multi_file_missions(
    settings: Settings, memory: FileMemory
) -> None:
    """Régression Sprint DDD : mission FastAPI étalon (mission 70652f89,
    2026-05-14) saturait SYSTÉMATIQUEMENT sur 4096 max_tokens (2 itérations
    du repair loop, conftest tronqué + tests manquants + Dockerfile absent).
    16384 donne la marge pour ~500 lignes de code idiomatique multi-fichiers.
    Cf. ADR-005 incident 8 et ADR-015."""
    agent = BackendDeveloper(memory=memory, settings=settings)
    assert agent.max_tokens >= 16384
