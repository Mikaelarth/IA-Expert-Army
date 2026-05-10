"""Tests pour src.mcp_servers.memory_search.

Tests les handlers _handle_search_episodes et _handle_search_skills
directement (sans démarrer un vrai serveur MCP via stdio). On mock les
dépendances VectorMemory et SkillsLibrary."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.learning.skills_library import Skill, SkillsLibrary
from src.mcp_servers.memory_search import (
    _build_server,
    _handle_search_episodes,
    _handle_search_skills,
)
from src.memory.vector_memory import EpisodeMatch, VectorMemory


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")


@pytest.fixture
def fake_vector() -> MagicMock:
    return MagicMock(spec=VectorMemory)


@pytest.fixture
def fake_skills() -> MagicMock:
    return MagicMock(spec=SkillsLibrary)


def _episode_match(eid: str = "ep1", agent: str = "research_lead", score: float = 0.91) -> EpisodeMatch:
    return EpisodeMatch(
        episode_id=eid,
        document="Tâche: faire X\n\nSortie: réussi",
        metadata={
            "agent": agent,
            "mission_id": "mid-abc",
            "mission_title": "Test mission",
            "quality_score": score,
        },
        distance=0.3,
    )


def _skill(skill_id: str = "sk1", title: str = "Test skill") -> Skill:
    return Skill(
        skill_id=skill_id,
        agent="research_lead",
        title=title,
        summary="Résumé de la skill",
        body="## Patterns\n- pattern 1\n- pattern 2",
        metadata={"tags": ["test", "research"], "sources_avg_score": 0.91},
        path=Path("/tmp/sk.md"),
    )


# ===== search_episodes =====


def test_search_episodes_returns_results_as_json(fake_vector: MagicMock) -> None:
    fake_vector.search.return_value = [_episode_match("ep1"), _episode_match("ep2", score=0.88)]

    result = _handle_search_episodes(fake_vector, {"query": "endpoint REST", "n": 2})

    assert len(result) == 1
    payload = json.loads(result[0].text)
    assert payload["query"] == "endpoint REST"
    assert payload["n_results"] == 2
    assert payload["results"][0]["episode_id"] == "ep1"
    assert payload["results"][0]["similarity"] == round(1 - 0.3, 4)
    assert "excerpt" in payload["results"][0]
    fake_vector.search.assert_called_once()
    call_kwargs = fake_vector.search.call_args.kwargs
    assert call_kwargs["query"] == "endpoint REST"
    assert call_kwargs["n_results"] == 2


def test_search_episodes_filters_by_agent(fake_vector: MagicMock) -> None:
    fake_vector.search.return_value = []
    _handle_search_episodes(fake_vector, {"query": "X", "agent": "code_reviewer"})

    call_kwargs = fake_vector.search.call_args.kwargs
    assert call_kwargs["where"] == {"agent": "code_reviewer"}


def test_search_episodes_clamps_n_to_range(fake_vector: MagicMock) -> None:
    """n est clampé à [1, 10] pour éviter les abus."""
    fake_vector.search.return_value = []

    _handle_search_episodes(fake_vector, {"query": "X", "n": 50})
    assert fake_vector.search.call_args.kwargs["n_results"] == 10

    _handle_search_episodes(fake_vector, {"query": "X", "n": 0})
    assert fake_vector.search.call_args.kwargs["n_results"] == 1

    _handle_search_episodes(fake_vector, {"query": "X", "n": -5})
    assert fake_vector.search.call_args.kwargs["n_results"] == 1


def test_search_episodes_empty_query_returns_error(fake_vector: MagicMock) -> None:
    result = _handle_search_episodes(fake_vector, {"query": "  "})
    payload = json.loads(result[0].text)
    assert "error" in payload
    fake_vector.search.assert_not_called()


def test_search_episodes_handles_vector_exception(fake_vector: MagicMock) -> None:
    fake_vector.search.side_effect = RuntimeError("chroma down")
    result = _handle_search_episodes(fake_vector, {"query": "X"})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert "chroma down" in payload["error"]


# ===== search_skills =====


def test_search_skills_returns_results(fake_skills: MagicMock) -> None:
    fake_skills.search_skills.return_value = [_skill("sk1", "FastAPI router"), _skill("sk2", "Saturation guard")]

    result = _handle_search_skills(fake_skills, {"agent": "research_lead", "n": 2})

    payload = json.loads(result[0].text)
    assert payload["agent"] == "research_lead"
    assert payload["n_results"] == 2
    assert payload["results"][0]["title"] == "FastAPI router"
    assert payload["results"][0]["tags"] == ["test", "research"]
    fake_skills.search_skills.assert_called_once()
    call_kwargs = fake_skills.search_skills.call_args.kwargs
    assert call_kwargs["agent"] == "research_lead"
    assert call_kwargs["query"] is None  # pas de query → fallback récence


def test_search_skills_with_query_passes_through(fake_skills: MagicMock) -> None:
    fake_skills.search_skills.return_value = []
    _handle_search_skills(fake_skills, {"agent": "tech_watch", "query": "RAG vs fine-tune"})
    call_kwargs = fake_skills.search_skills.call_args.kwargs
    assert call_kwargs["query"] == "RAG vs fine-tune"


def test_search_skills_clamps_n(fake_skills: MagicMock) -> None:
    fake_skills.search_skills.return_value = []

    _handle_search_skills(fake_skills, {"agent": "x", "n": 100})
    assert fake_skills.search_skills.call_args.kwargs["n_results"] == 5  # max

    _handle_search_skills(fake_skills, {"agent": "x", "n": 0})
    assert fake_skills.search_skills.call_args.kwargs["n_results"] == 1


def test_search_skills_empty_agent_returns_error(fake_skills: MagicMock) -> None:
    result = _handle_search_skills(fake_skills, {"agent": ""})
    payload = json.loads(result[0].text)
    assert "error" in payload
    fake_skills.search_skills.assert_not_called()


def test_search_skills_handles_library_exception(fake_skills: MagicMock) -> None:
    fake_skills.search_skills.side_effect = RuntimeError("disk full")
    result = _handle_search_skills(fake_skills, {"agent": "research_lead"})
    payload = json.loads(result[0].text)
    assert "error" in payload


# ===== Server construction =====


def test_build_server_with_injected_dependencies(
    fake_vector: MagicMock, fake_skills: MagicMock
) -> None:
    """Le serveur doit pouvoir être construit avec des dépendances injectées
    (utile pour les tests d'intégration et les setups custom)."""
    server = _build_server(vector_episodes=fake_vector, skills_library=fake_skills)
    assert server is not None
    # Le serveur expose le bon nom
    assert server.name == "ia-expert-army-memory"
