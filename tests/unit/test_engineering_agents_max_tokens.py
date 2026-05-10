"""Tests max_tokens pour les agents Engineering — fix préventif aligné Research."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.core.config import Settings
from src.memory.file_memory import FileMemory
from src.orchestrator.agents import CodeReviewer


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
