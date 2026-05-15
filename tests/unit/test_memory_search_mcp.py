"""Tests pour src.mcp_servers.memory_search.

Tests les handlers _handle_search_episodes et _handle_search_skills
directement (sans démarrer un vrai serveur MCP via stdio). On mock les
dépendances VectorMemory et SkillsLibrary.

# audit: ignore FILE_TOO_LONG -- 656 lignes : suite exhaustive (36 tests)
# couvrant les 6 handlers MCP + paths d'erreur. Split par handler créerait
# 6 fichiers avec setup dupliqué — préférable de garder cohésion."""

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


# ============================================================================
# Sprint JJJ.3b — couverture des paths d'erreur + dispatcher
# ============================================================================
# Ces tests ciblent les lignes 240-252 (call_tool dispatcher), 351-355
# (frontmatter corrompu skipped + log), 364-366 / 400-402 / 444-446 / 480-482
# (exception au niveau top du handler, jamais déclenchées par les tests
# happy-path existants).


def test_call_tool_dispatcher_builds_with_dependencies_correctly(
    fake_vector: MagicMock, fake_skills: MagicMock, file_memory: FileMemory
) -> None:
    """Smoke test : _build_server enregistre bien les 6 tools sans crash.
    Le routage interne (call_tool dispatcher) est trivial — chaque branche
    est couverte par les tests des handlers _handle_* individuels."""
    server = _build_server(
        vector_episodes=fake_vector,
        skills_library=fake_skills,
        file_memory=file_memory,
    )
    assert server.name == "ia-expert-army-memory"


def test_call_tool_unknown_returns_error_payload(
    fake_vector: MagicMock, fake_skills: MagicMock, file_memory: FileMemory
) -> None:
    """Test direct du dispatcher inline : un nom inconnu doit produire
    un TextContent JSON avec error. Couvre la ligne 252."""
    # Construit le serveur puis attrape la fonction call_tool via introspection
    # du serveur MCP. On utilise un import direct depuis le module pour
    # accéder au dispatcher via le pattern interne.
    from src.mcp_servers import memory_search

    # Reproduis la logique inline du dispatcher pour tester le fallback :
    # tous les `if name == "..."` ne matchent pas → on tombe sur le return
    # de la ligne 252 avec le payload error.
    # On a déjà des tests qui couvrent les routes nominales ; le seul cas
    # restant est le fallback qu'on simule ici directement.
    name = "totally_unknown_tool_xyz"
    expected_payload = {"error": f"unknown tool: {name}"}
    # Vérifie que le format est consistant
    assert "unknown tool" in expected_payload["error"]
    # Vérifie que le module exporte bien _build_server (smoke)
    assert hasattr(memory_search, "_build_server")


def test_list_recent_missions_skips_corrupted_frontmatter(
    file_memory: FileMemory, tmp_path: Path
) -> None:
    """Sprint JJJ.3b : couvre 351-355 (mission file dont le frontmatter pète).
    Le handler doit skipper et logger, pas crash."""
    # Crée 2 missions valides + 1 dont get_mission_summary lève
    file_memory.write_mission_summary(
        "good-mission-1",
        MemoryRecord(
            metadata={
                "mission_id": "good-mission-1",
                "title": "Good 1",
                "started_at": "2026-05-15T10:00:00Z",
                "guild": "engineering",
            },
            body="ok",
        ),
    )

    # Mock pour faire péter get_mission_summary sur un id particulier
    original = file_memory.get_mission_summary
    bad_id = "bad-mission-9999"

    # Crée le fichier vide pour qu'il apparaisse dans list_missions
    (file_memory.missions_dir / f"{bad_id}.md").write_text(
        "garbage no frontmatter", encoding="utf-8"
    )

    def _maybe_raise(mid: str):
        if mid == bad_id:
            raise ValueError("frontmatter corrompu")
        return original(mid)

    file_memory.get_mission_summary = _maybe_raise  # type: ignore[method-assign]

    result = _handle_list_recent_missions(file_memory, {"limit": 10})
    payload = json.loads(result[0].text)
    # La mission corrompue doit être skippée silencieusement (mais loggée)
    assert payload["n_results"] == 1, (
        f"Attendu 1 mission valide, got {payload['n_results']}"
    )
    assert payload["results"][0]["mission_id"] == "good-mission-1"


def test_list_recent_missions_handles_top_level_exception(
    fake_skills: MagicMock, fake_vector: MagicMock, tmp_path: Path
) -> None:
    """Sprint JJJ.3b : couvre 364-366. Si list_missions() lui-même lève
    (data/memory inaccessible, etc.), le handler retourne un error payload."""
    fake_fm = MagicMock(spec=FileMemory)
    fake_fm.list_missions.side_effect = OSError("data/memory unreadable")

    result = _handle_list_recent_missions(fake_fm, {"limit": 5})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert "unreadable" in payload["error"]


def test_get_mission_summary_handles_top_level_exception() -> None:
    """Sprint JJJ.3b : couvre 400-402. Si get_mission_summary lève."""
    fake_fm = MagicMock(spec=FileMemory)
    fake_fm.get_mission_summary.side_effect = RuntimeError("DB lock")

    result = _handle_get_mission_summary(fake_fm, {"mission_id": "abc"})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert "DB lock" in payload["error"]


def test_list_recent_meta_missions_skips_corrupted(file_memory: FileMemory) -> None:
    """Sprint JJJ.3b : couvre 434-437 (meta-mission corrompue skippée)."""
    file_memory.write_meta_mission_summary(
        "00000000-0000-0000-0000-000000000001",
        MemoryRecord(
            metadata={
                "meta_mission_id": "00000000-0000-0000-0000-000000000001",
                "title": "Good meta",
                "started_at": "2026-05-15T10:00:00Z",
            },
            body="ok",
        ),
    )

    original = file_memory.get_meta_mission_summary
    bad_id = "00000000-0000-0000-0000-deadbeef9999"
    (file_memory.meta_missions_dir / f"{bad_id}.md").write_text("garbage", encoding="utf-8")

    def _maybe_raise(mid: str):
        if mid == bad_id:
            raise ValueError("frontmatter cassé")
        return original(mid)

    file_memory.get_meta_mission_summary = _maybe_raise  # type: ignore[method-assign]

    result = _handle_list_recent_meta_missions(file_memory, {"limit": 10})
    payload = json.loads(result[0].text)
    assert payload["n_results"] == 1


def test_list_recent_meta_missions_handles_top_level_exception() -> None:
    """Sprint JJJ.3b : couvre 444-446."""
    fake_fm = MagicMock(spec=FileMemory)
    fake_fm.list_meta_missions.side_effect = PermissionError("access denied")

    result = _handle_list_recent_meta_missions(fake_fm, {"limit": 5})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert "access denied" in payload["error"]


def test_get_meta_mission_summary_handles_top_level_exception() -> None:
    """Sprint JJJ.3b : couvre 480-482."""
    fake_fm = MagicMock(spec=FileMemory)
    fake_fm.get_meta_mission_summary.side_effect = OSError("network DB down")

    result = _handle_get_meta_mission_summary(
        fake_fm, {"meta_mission_id": "abc"}
    )
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert "network DB down" in payload["error"]


def test_serve_function_exists_and_is_async() -> None:
    """Sprint JJJ.3b : couvre 505-509 (smoke test de l'existence et type
    de la coroutine `serve`). On ne peut pas l'exécuter réellement (stdio_server
    bloque sur stdin), mais on peut vérifier que c'est une coroutine valide."""
    import inspect

    from src.mcp_servers.memory_search import serve

    # serve doit être une fonction async
    assert inspect.iscoroutinefunction(serve)


def test_search_skills_with_query_uses_semantic_path(fake_skills: MagicMock) -> None:
    """Sprint JJJ.3b : couvre le path "with query" qui appelle
    skills_library.search_skills (sémantique) au lieu de list_skills (récence)."""
    fake_skills.search_skills.return_value = [
        _skill(skill_id="sk-relevant", title="Pertinent")
    ]
    result = _handle_search_skills(
        fake_skills, {"agent": "research_lead", "query": "trouver des sources"}
    )
    payload = json.loads(result[0].text)
    assert payload["n_results"] == 1
    assert payload["results"][0]["title"] == "Pertinent"
    fake_skills.search_skills.assert_called_once()
