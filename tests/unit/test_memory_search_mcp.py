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
    _handle_get_meta_mission_summary,
    _handle_get_mission_summary,
    _handle_list_recent_meta_missions,
    _handle_list_recent_missions,
    _handle_search_episodes,
    _handle_search_skills,
)
from src.memory.file_memory import FileMemory, MemoryRecord
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


def _episode_match(
    eid: str = "ep1", agent: str = "research_lead", score: float = 0.91
) -> EpisodeMatch:
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
    fake_skills.search_skills.return_value = [
        _skill("sk1", "FastAPI router"),
        _skill("sk2", "Saturation guard"),
    ]

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


# ===== list_recent_missions =====


def _write_mission(memory: FileMemory, mission_id: str, **meta: object) -> None:
    """Helper : écrit un mission summary minimal."""
    base_meta = {
        "mission_id": mission_id,
        "title": meta.get("title", f"Mission {mission_id[:8]}"),
        "guild": meta.get("guild", "engineering"),
        "started_at": meta.get("started_at", "2026-05-10T10:00:00+00:00"),
        "ended_at": meta.get("ended_at", "2026-05-10T10:01:00+00:00"),
        "success": meta.get("success", True),
        "final_verdict": meta.get("final_verdict", "APPROVED"),
        "quality_score": meta.get("quality_score", 0.85),
        "total_cost_usd": meta.get("total_cost_usd", 0.12),
        "total_duration_seconds": meta.get("total_duration_seconds", 60.0),
    }
    memory.write_mission_summary(
        mission_id, MemoryRecord(metadata=base_meta, body=f"# {base_meta['title']}\n\nbody")
    )


@pytest.fixture
def file_memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def test_list_recent_missions_returns_chronological_order(file_memory: FileMemory) -> None:
    """Les missions doivent être triées par started_at décroissant."""
    _write_mission(
        file_memory,
        "11111111-1111-1111-1111-111111111111",
        started_at="2026-05-08T10:00:00+00:00",
        title="Old",
    )
    _write_mission(
        file_memory,
        "22222222-2222-2222-2222-222222222222",
        started_at="2026-05-10T10:00:00+00:00",
        title="Recent",
    )
    _write_mission(
        file_memory,
        "33333333-3333-3333-3333-333333333333",
        started_at="2026-05-09T10:00:00+00:00",
        title="Middle",
    )

    result = _handle_list_recent_missions(file_memory, {"limit": 10})
    payload = json.loads(result[0].text)

    assert payload["n_results"] == 3
    titles = [r["title"] for r in payload["results"]]
    assert titles == ["Recent", "Middle", "Old"]


def test_list_recent_missions_filters_by_guild(file_memory: FileMemory) -> None:
    _write_mission(file_memory, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", guild="engineering")
    _write_mission(file_memory, "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", guild="research")
    _write_mission(file_memory, "cccccccc-cccc-cccc-cccc-cccccccccccc", guild="research")

    result = _handle_list_recent_missions(file_memory, {"guild": "research"})
    payload = json.loads(result[0].text)

    assert payload["guild_filter"] == "research"
    assert payload["n_results"] == 2
    assert all(r["guild"] == "research" for r in payload["results"])


def test_list_recent_missions_clamps_limit(file_memory: FileMemory) -> None:
    """limit clampé à [1, 50]."""
    for i in range(5):
        _write_mission(file_memory, f"{i:08d}-0000-0000-0000-000000000000")

    result = _handle_list_recent_missions(file_memory, {"limit": 200})
    payload = json.loads(result[0].text)
    assert payload["limit"] == 50

    result = _handle_list_recent_missions(file_memory, {"limit": 0})
    payload = json.loads(result[0].text)
    assert payload["limit"] == 1


def test_list_recent_missions_returns_metadata_fields(file_memory: FileMemory) -> None:
    """Le payload doit inclure les champs essentiels (verdict, score, coût)."""
    _write_mission(
        file_memory,
        "deadbeef-dead-beef-dead-beefdeadbeef",
        title="Test",
        guild="creative",
        quality_score=0.92,
        total_cost_usd=0.34,
        final_verdict="APPROVED",
    )

    result = _handle_list_recent_missions(file_memory, {})
    payload = json.loads(result[0].text)

    r = payload["results"][0]
    assert r["mission_id"] == "deadbeef-dead-beef-dead-beefdeadbeef"
    assert r["title"] == "Test"
    assert r["quality_score"] == 0.92
    assert r["total_cost_usd"] == 0.34
    assert r["final_verdict"] == "APPROVED"
    assert "started_at" in r
    assert "ended_at" in r


def test_list_recent_missions_empty_when_no_missions(file_memory: FileMemory) -> None:
    result = _handle_list_recent_missions(file_memory, {})
    payload = json.loads(result[0].text)
    assert payload["n_results"] == 0
    assert payload["results"] == []


# ===== get_mission_summary =====


def test_get_mission_summary_returns_full_record(file_memory: FileMemory) -> None:
    mid = "12345678-1234-1234-1234-123456789012"
    _write_mission(file_memory, mid, title="Détail mission", guild="business")

    result = _handle_get_mission_summary(file_memory, {"mission_id": mid})
    payload = json.loads(result[0].text)

    assert payload["mission_id"] == mid
    assert payload["metadata"]["title"] == "Détail mission"
    assert payload["metadata"]["guild"] == "business"
    assert "Détail mission" in payload["body"]


def test_get_mission_summary_returns_error_when_not_found(file_memory: FileMemory) -> None:
    result = _handle_get_mission_summary(
        file_memory, {"mission_id": "00000000-0000-0000-0000-000000000000"}
    )
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert "not found" in payload["error"]


def test_get_mission_summary_empty_id_returns_error(file_memory: FileMemory) -> None:
    result = _handle_get_mission_summary(file_memory, {"mission_id": "  "})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert "required" in payload["error"]


# ===== list_recent_meta_missions / get_meta_mission_summary (Phase 7) =====


def _write_meta_mission(memory: FileMemory, meta_id: str, **meta: object) -> None:
    """Helper : écrit un meta-mission summary minimal."""
    base_meta = {
        "meta_mission_id": meta_id,
        "title": meta.get("title", f"Meta {meta_id[:8]}"),
        "started_at": meta.get("started_at", "2026-05-11T10:00:00+00:00"),
        "ended_at": meta.get("ended_at", "2026-05-11T10:10:00+00:00"),
        "final_verdict": meta.get("final_verdict", "APPROVED"),
        "overall_quality_score": meta.get("overall_quality_score", 0.91),
        "total_cost_usd": meta.get("total_cost_usd", 2.5),
        "total_duration_seconds": meta.get("total_duration_seconds", 555.0),
        "n_sub_missions": meta.get("n_sub_missions", 3),
        "guilds": meta.get("guilds", ["business", "engineering", "creative"]),
        "sub_mission_ids": meta.get("sub_mission_ids", ["sub-1", "sub-2", "sub-3"]),
    }
    memory.write_meta_mission_summary(
        meta_id, MemoryRecord(metadata=base_meta, body=f"# {base_meta['title']}\n\nbody")
    )


def test_list_recent_meta_missions_chronological_order(file_memory: FileMemory) -> None:
    """Tri par started_at décroissant, comme list_recent_missions."""
    _write_meta_mission(
        file_memory,
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        started_at="2026-05-09T10:00:00+00:00",
        title="Old",
    )
    _write_meta_mission(
        file_memory,
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        started_at="2026-05-11T10:00:00+00:00",
        title="Recent",
    )
    _write_meta_mission(
        file_memory,
        "cccccccc-cccc-cccc-cccc-cccccccccccc",
        started_at="2026-05-10T10:00:00+00:00",
        title="Middle",
    )

    result = _handle_list_recent_meta_missions(file_memory, {"limit": 10})
    payload = json.loads(result[0].text)

    assert payload["n_results"] == 3
    titles = [r["title"] for r in payload["results"]]
    assert titles == ["Recent", "Middle", "Old"]


def test_list_recent_meta_missions_returns_sub_mission_ids(file_memory: FileMemory) -> None:
    """Le payload doit exposer les IDs des sous-missions pour le drill-down."""
    _write_meta_mission(
        file_memory,
        "11111111-2222-3333-4444-555555555555",
        sub_mission_ids=["sm-eng", "sm-cre", "sm-biz"],
        guilds=["engineering", "creative", "business"],
    )
    result = _handle_list_recent_meta_missions(file_memory, {})
    payload = json.loads(result[0].text)
    r = payload["results"][0]
    assert r["sub_mission_ids"] == ["sm-eng", "sm-cre", "sm-biz"]
    assert r["guilds"] == ["engineering", "creative", "business"]
    assert r["n_sub_missions"] == 3


def test_list_recent_meta_missions_clamps_limit(file_memory: FileMemory) -> None:
    for i in range(5):
        _write_meta_mission(file_memory, f"{i:08d}-0000-0000-0000-000000000000")

    result = _handle_list_recent_meta_missions(file_memory, {"limit": 200})
    payload = json.loads(result[0].text)
    assert payload["limit"] == 50

    result = _handle_list_recent_meta_missions(file_memory, {"limit": 0})
    payload = json.loads(result[0].text)
    assert payload["limit"] == 1


def test_list_recent_meta_missions_empty(file_memory: FileMemory) -> None:
    result = _handle_list_recent_meta_missions(file_memory, {})
    payload = json.loads(result[0].text)
    assert payload["n_results"] == 0
    assert payload["results"] == []


def test_get_meta_mission_summary_returns_full_record(file_memory: FileMemory) -> None:
    mid = "98765432-1234-5678-9abc-def012345678"
    _write_meta_mission(file_memory, mid, title="Mini SaaS TVA", final_verdict="APPROVED")

    result = _handle_get_meta_mission_summary(file_memory, {"meta_mission_id": mid})
    payload = json.loads(result[0].text)

    assert payload["meta_mission_id"] == mid
    assert payload["metadata"]["title"] == "Mini SaaS TVA"
    assert payload["metadata"]["final_verdict"] == "APPROVED"
    assert "Mini SaaS TVA" in payload["body"]


def test_get_meta_mission_summary_not_found(file_memory: FileMemory) -> None:
    result = _handle_get_meta_mission_summary(
        file_memory, {"meta_mission_id": "ffffffff-ffff-ffff-ffff-ffffffffffff"}
    )
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert "not found" in payload["error"]


def test_get_meta_mission_summary_empty_id_returns_error(file_memory: FileMemory) -> None:
    result = _handle_get_meta_mission_summary(file_memory, {"meta_mission_id": ""})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert "required" in payload["error"]


# ===== Server construction =====


def test_build_server_with_injected_dependencies(
    fake_vector: MagicMock, fake_skills: MagicMock, file_memory: FileMemory
) -> None:
    """Le serveur doit pouvoir être construit avec des dépendances injectées
    (utile pour les tests d'intégration et les setups custom)."""
    server = _build_server(
        vector_episodes=fake_vector, skills_library=fake_skills, file_memory=file_memory
    )
    assert server is not None
    # Le serveur expose le bon nom
    assert server.name == "ia-expert-army-memory"
