"""Tests pour src.learning.pattern_miner — l'extracteur Claude est mocké."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import Settings
from src.learning.pattern_miner import PatternMiner
from src.learning.skill_extractor import SkillExtractor
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory, MemoryRecord


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


@pytest.fixture
def skills(tmp_path: Path) -> SkillsLibrary:
    return SkillsLibrary(tmp_path / "skills")


def _add_episode(
    memory: FileMemory,
    agent: str,
    success: bool = True,
    quality_score: float = 0.9,
    task: str = "do something",
    output: str = "result",
) -> None:
    record = MemoryRecord(
        metadata={
            "agent": agent,
            "success": success,
            "quality_score": quality_score,
            "mission_id": str(uuid4()),
        },
        body=f"## Tâche\n\n{task}\n\n## Sortie brute\n\n{output}\n",
    )
    memory.write_episode(uuid4(), agent, record)


def test_load_eligible_filters_failures_and_low_quality(
    memory: FileMemory, skills: SkillsLibrary, settings: Settings
) -> None:
    _add_episode(memory, "software_architect", quality_score=0.95)
    _add_episode(memory, "software_architect", quality_score=0.50)  # filtré
    _add_episode(memory, "software_architect", success=False)  # filtré
    _add_episode(memory, "non_whitelisted_agent", quality_score=0.99)  # filtré

    miner = PatternMiner(memory=memory, skills=skills, settings=settings)
    grouped = miner._load_eligible_episodes()
    assert len(grouped["software_architect"]) == 1
    assert "non_whitelisted_agent" not in grouped


def test_select_top_k_orders_by_quality(memory: FileMemory) -> None:
    _add_episode(memory, "backend_developer", quality_score=0.85, output="low")
    _add_episode(memory, "backend_developer", quality_score=0.99, output="high")
    _add_episode(memory, "backend_developer", quality_score=0.92, output="mid")

    eps = [(p, memory.read_episode(p)) for p in memory.list_episodes()]
    selected = PatternMiner._select_top_k(eps, k=2)
    assert len(selected) == 2
    assert selected[0][1].metadata["quality_score"] == 0.99
    assert selected[1][1].metadata["quality_score"] == 0.92


@pytest.mark.asyncio
async def test_mine_creates_skills_for_eligible_agents(
    memory: FileMemory, skills: SkillsLibrary, settings: Settings, tmp_path: Path
) -> None:
    # 2 épisodes pour architect → assez pour miner
    _add_episode(memory, "software_architect", quality_score=0.95, task="design X")
    _add_episode(memory, "software_architect", quality_score=0.91, task="design Y")
    # 1 épisode pour developer → trop peu, sera skip
    _add_episode(memory, "backend_developer", quality_score=0.95)

    fake_yaml = """```yaml
title: Architect router pattern
agent: software_architect
tags: [fastapi, pydantic]
summary: |
  Use APIRouter + response_model on every endpoint.
key_patterns:
  - Always declare a Pydantic model for responses
  - Group endpoints under a single router exposed at module level
techniques:
  - APIRouter()
  - response_model=
pitfalls_avoided:
  - Skipping types for response payloads
  - Coupling business logic to FastAPI internals
example_template: |
  router = APIRouter()
  @router.get("/x", response_model=Resp)
  async def x(): ...
sources_count: 2
```"""

    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=fake_yaml),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=500, completion_tokens=300),
        model="qwen2.5-coder:32b",
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=fake_response)))
    )
    extractor = SkillExtractor(memory=memory, settings=settings, client=fake_client)  # type: ignore[arg-type]

    miner = PatternMiner(
        memory=memory,
        skills=skills,
        settings=settings,
        extractor=extractor,
        min_episodes=2,
        top_k=3,
        min_quality=0.85,
    )
    report = await miner.mine()

    assert report.skills_created == 1
    arch_skills = skills.list_skills("software_architect")
    assert len(arch_skills) == 1
    assert "Architect router pattern" in arch_skills[0].title
    assert arch_skills[0].metadata.get("extracted_from") == 2
    # backend_developer n'avait qu'1 épisode → skip
    assert skills.count("backend_developer") == 0


@pytest.mark.asyncio
async def test_mine_handles_invalid_yaml_gracefully(
    memory: FileMemory, skills: SkillsLibrary, settings: Settings
) -> None:
    _add_episode(memory, "code_reviewer", quality_score=0.95)
    _add_episode(memory, "code_reviewer", quality_score=0.90)

    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="**not yaml at all** %&^@"),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
        model="qwen2.5-coder:32b",
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=fake_response)))
    )
    extractor = SkillExtractor(memory=memory, settings=settings, client=fake_client)  # type: ignore[arg-type]

    miner = PatternMiner(
        memory=memory, skills=skills, settings=settings, extractor=extractor, min_episodes=2
    )
    report = await miner.mine()
    assert report.skills_created == 0
    reviewer_result = next(r for r in report.per_agent if r.agent == "code_reviewer")
    assert "YAML" in (reviewer_result.error or "")


@pytest.mark.asyncio
async def test_mine_reports_per_agent_status(
    memory: FileMemory, skills: SkillsLibrary, settings: Settings
) -> None:
    _add_episode(memory, "chief_orchestrator", quality_score=0.95)
    # Pas d'autres agents → tous les autres devraient être en "skip"

    extractor = SkillExtractor(
        memory=memory,
        settings=settings,
        client=SimpleNamespace(messages=SimpleNamespace(create=AsyncMock())),  # type: ignore[arg-type]
    )
    miner = PatternMiner(
        memory=memory, skills=skills, settings=settings, extractor=extractor, min_episodes=2
    )
    report = await miner.mine()
    assert report.skills_created == 0
    assert len(report.per_agent) == len(PatternMiner.AGENT_WHITELIST)
    # Tous skip car min_episodes=2
    assert all(r.skill_extracted is None for r in report.per_agent)


def test_whitelist_includes_all_research_agents() -> None:
    """Régression : la Research Guild doit être dans le whitelist par défaut.
    Auparavant seuls les agents Engineering étaient minés (oubli Phase 4)."""
    for agent in (
        "research_lead",
        "tech_watch",
        "document_synthesizer",
        "research_reviewer",
    ):
        assert agent in PatternMiner.AGENT_WHITELIST, (
            f"{agent} doit être dans le whitelist pour bénéficier du mining"
        )


def test_whitelist_includes_all_creative_agents() -> None:
    """Régression : la Creative Guild doit être dans le whitelist (oubli répété
    sur Research, ne pas refaire sur les futures guildes Business/etc.)."""
    for agent in ("content_strategist", "copywriter", "editor"):
        assert agent in PatternMiner.AGENT_WHITELIST, (
            f"{agent} doit être dans le whitelist pour bénéficier du mining"
        )


def test_pattern_miner_respects_agents_filter(
    memory: FileMemory, skills: SkillsLibrary, settings: Settings
) -> None:
    """La sous-sélection d'agents doit être respectée (pas miner tout le whitelist)."""
    _add_episode(memory, "research_lead", quality_score=0.90)
    _add_episode(memory, "research_lead", quality_score=0.92)
    _add_episode(memory, "software_architect", quality_score=0.95)
    _add_episode(memory, "software_architect", quality_score=0.93)

    miner = PatternMiner(
        memory=memory,
        skills=skills,
        settings=settings,
        min_episodes=2,
        agents=("research_lead",),  # filtre explicite
    )
    grouped = miner._load_eligible_episodes()
    # Seul research_lead doit être groupé (software_architect filtré)
    assert "research_lead" in grouped
    assert "software_architect" not in grouped


def test_pattern_miner_excludes_rejected_missions(
    memory: FileMemory, skills: SkillsLibrary, settings: Settings
) -> None:
    """Quand final_verdict est propagé : seules les missions APPROVED nourrissent le mining."""
    from uuid import uuid4

    from src.memory.file_memory import MemoryRecord

    rejected = MemoryRecord(
        metadata={
            "agent": "research_lead",
            "success": True,
            "quality_score": None,  # rejet → pas de score
            "final_verdict": "REJECTED",
        },
        body="## Tâche\n\ntest\n\n## Sortie brute\n\nrejeté en aval",
    )
    approved = MemoryRecord(
        metadata={
            "agent": "research_lead",
            "success": True,
            "quality_score": 0.92,
            "final_verdict": "APPROVED",
        },
        body="## Tâche\n\ntest\n\n## Sortie brute\n\nbon",
    )
    memory.write_episode(uuid4(), "research_lead", rejected)
    memory.write_episode(uuid4(), "research_lead", approved)

    miner = PatternMiner(memory=memory, skills=skills, settings=settings, min_episodes=1)
    grouped = miner._load_eligible_episodes()
    # Seul l'approved compte
    assert len(grouped["research_lead"]) == 1
    assert grouped["research_lead"][0][1].metadata["final_verdict"] == "APPROVED"


def test_pattern_miner_legacy_episodes_without_final_verdict_use_quality_score(
    memory: FileMemory, skills: SkillsLibrary, settings: Settings
) -> None:
    """Les épisodes legacy (sans final_verdict propagé) restent éligibles via quality_score seul."""
    from uuid import uuid4

    from src.memory.file_memory import MemoryRecord

    legacy_high = MemoryRecord(
        metadata={"agent": "research_lead", "success": True, "quality_score": 0.95},
        body="## Tâche\n\ntest\n\n## Sortie brute\n\nok",
    )
    legacy_low = MemoryRecord(
        metadata={"agent": "research_lead", "success": True, "quality_score": 0.50},
        body="## Tâche\n\ntest\n\n## Sortie brute\n\nfaible",
    )
    memory.write_episode(uuid4(), "research_lead", legacy_high)
    memory.write_episode(uuid4(), "research_lead", legacy_low)

    miner = PatternMiner(
        memory=memory, skills=skills, settings=settings, min_episodes=1, min_quality=0.85
    )
    grouped = miner._load_eligible_episodes()
    assert len(grouped["research_lead"]) == 1


def test_pattern_miner_excludes_saturated_episodes(
    memory: FileMemory, skills: SkillsLibrary, settings: Settings
) -> None:
    """Les épisodes saturés (sortie tronquée) ne doivent pas alimenter le mining."""
    # Ajout via metadata directe
    from uuid import uuid4

    from src.memory.file_memory import MemoryRecord

    saturated = MemoryRecord(
        metadata={
            "agent": "research_lead",
            "success": True,
            "quality_score": 0.9,
            "saturated": True,
        },
        body="## Tâche\n\ntest\n\n## Sortie brute\n\ntronqué",
    )
    clean = MemoryRecord(
        metadata={
            "agent": "research_lead",
            "success": True,
            "quality_score": 0.9,
            "saturated": False,
        },
        body="## Tâche\n\ntest\n\n## Sortie brute\n\nok",
    )
    memory.write_episode(uuid4(), "research_lead", saturated)
    memory.write_episode(uuid4(), "research_lead", clean)

    miner = PatternMiner(memory=memory, skills=skills, settings=settings, min_episodes=1)
    grouped = miner._load_eligible_episodes()
    assert len(grouped["research_lead"]) == 1  # le saturé filtré
