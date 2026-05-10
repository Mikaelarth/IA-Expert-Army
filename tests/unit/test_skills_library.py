"""Tests pour src.learning.skills_library."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.learning.skills_library import Skill, SkillsLibrary


@pytest.fixture
def lib(tmp_path: Path) -> SkillsLibrary:
    return SkillsLibrary(tmp_path / "skills")


def test_creates_root_dir(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    SkillsLibrary(root)
    assert root.exists() and root.is_dir()


def test_write_and_read_skill(lib: SkillsLibrary) -> None:
    skill = lib.write_skill(
        agent="software_architect",
        title="FastAPI router pattern",
        body="## Résumé\n\nUse APIRouter + Pydantic models.",
        metadata={"summary": "Pattern stable", "tags": ["fastapi", "pydantic"]},
    )
    assert skill.skill_id
    assert skill.path.exists()
    assert "FastAPI router" in skill.title

    skills = lib.list_skills("software_architect")
    assert len(skills) == 1
    assert skills[0].skill_id == skill.skill_id
    assert "APIRouter" in skills[0].body


def test_list_skills_returns_most_recent_first(lib: SkillsLibrary) -> None:
    import time
    s1 = lib.write_skill("dev", "First skill", "body 1")
    time.sleep(1.05)  # garantit un timestamp différent (slug encodé à la seconde)
    s2 = lib.write_skill("dev", "Second skill", "body 2")
    skills = lib.list_skills("dev")
    assert len(skills) == 2
    assert skills[0].skill_id == s2.skill_id
    assert skills[1].skill_id == s1.skill_id


def test_list_skills_respects_limit(lib: SkillsLibrary) -> None:
    for i in range(5):
        lib.write_skill("dev", f"Skill {i}", f"body {i}")
    skills = lib.list_skills("dev", limit=2)
    assert len(skills) == 2


def test_list_skills_empty_when_no_skills(lib: SkillsLibrary) -> None:
    assert lib.list_skills("nobody") == []


def test_count_per_agent(lib: SkillsLibrary) -> None:
    lib.write_skill("a", "x", "b")
    lib.write_skill("a", "y", "b")
    lib.write_skill("b", "z", "b")
    assert lib.count("a") == 2
    assert lib.count("b") == 1
    assert lib.count() == 3


def test_render_for_prompt_handles_empty() -> None:
    assert SkillsLibrary.render_for_prompt([]) == ""


def test_render_for_prompt_includes_titles_and_truncates() -> None:
    skills = [
        Skill(
            skill_id="s1",
            agent="x",
            title="Pattern A",
            summary="Resume A",
            body="A" * 100,
            metadata={},
            path=Path("/tmp/s1.md"),
        ),
        Skill(
            skill_id="s2",
            agent="x",
            title="Pattern B",
            summary="",
            body="B" * 5000,  # sera tronqué
            metadata={},
            path=Path("/tmp/s2.md"),
        ),
    ]
    rendered = SkillsLibrary.render_for_prompt(skills, max_chars_per_skill=100)
    assert "Pattern A" in rendered
    assert "Pattern B" in rendered
    assert "Resume A" in rendered
    assert "[tronqué]" in rendered


def test_metadata_is_persisted(lib: SkillsLibrary) -> None:
    lib.write_skill(
        "dev",
        "T",
        "B",
        metadata={"summary": "S", "tags": ["x"], "custom": 42},
    )
    skills = lib.list_skills("dev")
    assert skills[0].metadata.get("custom") == 42
    assert skills[0].metadata.get("tags") == ["x"]
    assert skills[0].summary == "S"
