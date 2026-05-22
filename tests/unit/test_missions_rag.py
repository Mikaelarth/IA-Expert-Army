"""Tests v0.9.0 A1 — MissionsRAG (RAG sur missions archivées)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.learning.missions_rag import (
    MISSIONS_COLLECTION,
    MissionsRAG,
    SimilarMission,
    _extract_summary_from_document,
    _safe_float,
)
from src.memory.file_memory import MemoryRecord
from src.memory.vector_memory import VectorMemory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vector_memory(tmp_path: Path) -> VectorMemory:
    """VectorMemory réelle sur disque tmp pour tests d'intégration."""
    return VectorMemory(persist_dir=tmp_path / "chroma", collection_name=MISSIONS_COLLECTION)


@pytest.fixture
def rag(vector_memory: VectorMemory) -> MissionsRAG:
    return MissionsRAG(vector_memory)


def _approved_summary(
    quality_score: float = 0.92,
    review_summary: str = "Tests verts, architecture propre.",
    guild: str = "engineering",
) -> MemoryRecord:
    """Construit un mission summary APPROVED prêt à indexer."""
    return MemoryRecord(
        metadata={
            "final_verdict": "APPROVED",
            "quality_score": quality_score,
            "review_summary": review_summary,
            "guild": guild,
            "total_cost_usd": 0.0,
            "total_duration_seconds": 120.0,
        },
        body=review_summary,
    )


# ---------------------------------------------------------------------------
# index_mission
# ---------------------------------------------------------------------------


def test_index_mission_approved_returns_true(rag: MissionsRAG) -> None:
    indexed = rag.index_mission(
        mission_id="mission-abc",
        title="Crée endpoint /health",
        description="GET /health retourne 200 OK",
        summary_record=_approved_summary(),
    )
    assert indexed is True
    assert rag.vector_memory.count() == 1


def test_index_mission_skips_needs_changes(rag: MissionsRAG) -> None:
    """Politique : on ne pollue pas le RAG avec des missions NEEDS_CHANGES."""
    rec = MemoryRecord(
        metadata={"final_verdict": "NEEDS_CHANGES", "guild": "engineering"},
        body="non terminée",
    )
    indexed = rag.index_mission("m1", "t", "d", rec)
    assert indexed is False
    assert rag.vector_memory.count() == 0


def test_index_mission_skips_rejected(rag: MissionsRAG) -> None:
    rec = MemoryRecord(
        metadata={"final_verdict": "REJECTED", "guild": "engineering"},
        body="rejetée",
    )
    assert rag.index_mission("m1", "t", "d", rec) is False
    assert rag.vector_memory.count() == 0


def test_index_mission_idempotent(rag: MissionsRAG) -> None:
    """Re-indexer la même mission doit upsert (pas dupliquer)."""
    mid = "mission-dup"
    rag.index_mission(mid, "T", "D", _approved_summary(quality_score=0.91))
    rag.index_mission(mid, "T", "D", _approved_summary(quality_score=0.95))
    assert rag.vector_memory.count() == 1


def test_index_mission_handles_vector_failure_gracefully(
    monkeypatch: pytest.MonkeyPatch, vector_memory: VectorMemory
) -> None:
    """Si add_episode lève, index_mission retourne False sans propager."""

    def boom(*args, **kwargs):
        raise RuntimeError("chroma down")

    monkeypatch.setattr(vector_memory, "add_episode", boom)
    rag = MissionsRAG(vector_memory)
    assert rag.index_mission("m1", "t", "d", _approved_summary()) is False


# ---------------------------------------------------------------------------
# find_similar
# ---------------------------------------------------------------------------


def test_find_similar_returns_relevant_matches(rag: MissionsRAG) -> None:
    """Une recherche par titre+description similaire à une mission indexée
    doit la retrouver en top match."""
    rag.index_mission(
        "mission-1",
        title="Endpoint FastAPI /health avec tests pytest",
        description="Crée un endpoint GET /health qui retourne 200 + JSON status.",
        summary_record=_approved_summary(review_summary="Tests pytest 100% passants"),
    )
    rag.index_mission(
        "mission-2",
        title="Landing page SaaS marketing",
        description="Rédige une landing page pour startup B2B.",
        summary_record=_approved_summary(guild="creative"),
    )

    matches = rag.find_similar(
        title="Crée endpoint FastAPI /version",
        description="GET /version retourne le numéro de version courant.",
        n_results=5,
    )

    assert len(matches) >= 1
    # Le top match doit être mission-1 (technique similaire), pas mission-2 (creative)
    assert matches[0].mission_id == "mission-1"
    assert matches[0].quality_score == 0.92
    assert matches[0].guild == "engineering"
    assert matches[0].relevance > 0


def test_find_similar_filters_by_guild(rag: MissionsRAG) -> None:
    rag.index_mission(
        "m1",
        "Mission engineering",
        "code",
        _approved_summary(guild="engineering"),
    )
    rag.index_mission("m2", "Mission research", "veille", _approved_summary(guild="research"))

    eng_matches = rag.find_similar("query", "desc", guild="engineering", n_results=10)
    assert all(m.guild == "engineering" for m in eng_matches)
    assert any(m.mission_id == "m1" for m in eng_matches)
    assert not any(m.mission_id == "m2" for m in eng_matches)


def test_find_similar_excludes_specified_mission_id(rag: MissionsRAG) -> None:
    rag.index_mission("m1", "Same query", "exact desc", _approved_summary())
    rag.index_mission("m2", "Same query", "exact desc", _approved_summary())

    matches = rag.find_similar("Same query", "exact desc", exclude_mission_id="m1", n_results=5)
    assert all(m.mission_id != "m1" for m in matches)
    assert any(m.mission_id == "m2" for m in matches)


def test_find_similar_filters_by_min_quality_score(rag: MissionsRAG) -> None:
    rag.index_mission("low", "T", "D", _approved_summary(quality_score=0.80))
    rag.index_mission("high", "T", "D", _approved_summary(quality_score=0.95))

    matches = rag.find_similar("T", "D", min_quality_score=0.90, n_results=10)
    ids = {m.mission_id for m in matches}
    assert "high" in ids
    assert "low" not in ids


def test_find_similar_returns_empty_when_no_index(rag: MissionsRAG) -> None:
    assert rag.find_similar("anything", "nothing indexed") == []


def test_find_similar_handles_search_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si search() lève, on retourne [] silencieusement (best-effort RAG)."""
    fake_vm = MagicMock()
    fake_vm.search.side_effect = RuntimeError("chroma boom")
    fake_vm.count.return_value = 0  # not used given the search raises

    rag = MissionsRAG(fake_vm)
    assert rag.find_similar("t", "d") == []


# ---------------------------------------------------------------------------
# render_for_prompt
# ---------------------------------------------------------------------------


def test_render_for_prompt_empty_returns_empty_string() -> None:
    assert MissionsRAG.render_for_prompt([]) == ""


def test_render_for_prompt_includes_key_fields() -> None:
    matches = [
        SimilarMission(
            mission_id="m1",
            title="Test mission 1",
            guild="engineering",
            final_verdict="APPROVED",
            quality_score=0.94,
            summary="Très bonne implémentation, tests verts.",
            distance=0.2,
        ),
        SimilarMission(
            mission_id="m2",
            title="Test mission 2",
            guild="research",
            final_verdict="APPROVED",
            quality_score=0.88,
            summary="Comparatif solide, sources citées.",
            distance=0.4,
        ),
    ]
    rendered = MissionsRAG.render_for_prompt(matches)
    assert "Missions similaires déjà réalisées" in rendered
    assert "Test mission 1" in rendered
    assert "Test mission 2" in rendered
    assert "0.94" in rendered
    assert "engineering" in rendered
    # Relevance affichée en pourcentage (1 - distance)
    assert "80%" in rendered  # 1 - 0.2 = 80%


def test_render_for_prompt_truncates_long_summaries() -> None:
    long_summary = "x" * 1000
    match = SimilarMission(
        mission_id="m",
        title="t",
        guild="engineering",
        final_verdict="APPROVED",
        quality_score=0.9,
        summary=long_summary,
        distance=0.1,
    )
    rendered = MissionsRAG.render_for_prompt([match], max_chars_per_match=200)
    # Doit contenir l'ellipse et NE PAS contenir les 1000 caractères
    assert "…" in rendered
    assert "x" * 1000 not in rendered


# ---------------------------------------------------------------------------
# Helpers privés
# ---------------------------------------------------------------------------


def test_safe_float_handles_various_inputs() -> None:
    assert _safe_float(1.5) == 1.5
    assert _safe_float("0.92") == 0.92
    assert _safe_float(None) is None
    assert _safe_float("not a number") is None
    assert _safe_float([1, 2, 3]) is None


def test_extract_summary_falls_back_to_document_prefix() -> None:
    """Si le marqueur n'est pas dans le document, on retourne le début brut."""
    doc = "Document sans marqueur de résumé attendu"
    extracted = _extract_summary_from_document(doc)
    assert extracted == doc[:500]


def test_extract_summary_returns_section_when_marker_present() -> None:
    doc = "# Titre\n## Description\nblah\n## Résumé du Reviewer\nLe vrai résumé ici."
    extracted = _extract_summary_from_document(doc)
    assert extracted == "Le vrai résumé ici."


# ---------------------------------------------------------------------------
# Intégration Workflow ↔ MissionsRAG (v0.9.0 A1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_indexes_approved_mission_in_rag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Après une mission APPROVED, MissionsRAG doit avoir 1 entrée indexée."""
    from unittest.mock import AsyncMock

    from src.core.config import Settings
    from src.memory.file_memory import FileMemory
    from src.orchestrator.base_agent import AgentOutput
    from src.orchestrator.workflow import Workflow

    vector = VectorMemory(persist_dir=tmp_path / "chroma", collection_name=MISSIONS_COLLECTION)
    rag = MissionsRAG(vector)
    memory = FileMemory(tmp_path / "memory")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    def _fake_out(text: str, parsed: object = None) -> AgentOutput:
        return AgentOutput(
            agent_name="fake",
            success=True,
            raw_text=text,
            parsed=parsed,
            cost_usd=0.0,
            duration_seconds=0.1,
            tokens_in=10,
            tokens_out=20,
        )

    wf = Workflow(memory=memory, settings=settings, missions_rag=rag)
    monkeypatch.setattr(
        wf.orchestrator,
        "run",
        AsyncMock(return_value=_fake_out("o", parsed={"subtasks": [{"task": "T"}]})),
    )
    monkeypatch.setattr(wf.architect, "run", AsyncMock(return_value=_fake_out("a")))
    monkeypatch.setattr(
        wf.developer,
        "run",
        AsyncMock(return_value=_fake_out("d", parsed=[{"path": "src/x.py", "content": "x"}])),
    )
    monkeypatch.setattr(
        wf.reviewer,
        "run",
        AsyncMock(
            return_value=_fake_out(
                "r", parsed={"verdict": "APPROVED", "quality_score": 0.92, "summary": "ok"}
            )
        ),
    )

    assert vector.count() == 0
    await wf.run(title="Test mission RAG", description="Crée un endpoint /ping")
    assert vector.count() == 1


@pytest.mark.asyncio
async def test_workflow_injects_rag_context_into_orchestrator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si le RAG contient une mission similaire, son résumé doit apparaître
    dans le `task` envoyé au Chief Orchestrator."""
    from unittest.mock import AsyncMock

    from src.core.config import Settings
    from src.memory.file_memory import FileMemory
    from src.orchestrator.base_agent import AgentOutput
    from src.orchestrator.workflow import Workflow

    vector = VectorMemory(persist_dir=tmp_path / "chroma", collection_name=MISSIONS_COLLECTION)
    rag = MissionsRAG(vector)
    # Pré-indexation d'une mission antérieure
    rag.index_mission(
        "past-mission",
        title="Endpoint FastAPI /health",
        description="Crée endpoint health 200 OK",
        summary_record=_approved_summary(review_summary="Implémentation propre."),
    )

    memory = FileMemory(tmp_path / "memory")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    def _fake_out(text: str, parsed: object = None) -> AgentOutput:
        return AgentOutput(
            agent_name="fake",
            success=True,
            raw_text=text,
            parsed=parsed,
            cost_usd=0.0,
            duration_seconds=0.1,
            tokens_in=10,
            tokens_out=20,
        )

    wf = Workflow(memory=memory, settings=settings, missions_rag=rag)
    orch_mock = AsyncMock(return_value=_fake_out("o", parsed={"subtasks": [{"task": "T"}]}))
    monkeypatch.setattr(wf.orchestrator, "run", orch_mock)
    monkeypatch.setattr(wf.architect, "run", AsyncMock(return_value=_fake_out("a")))
    monkeypatch.setattr(
        wf.developer,
        "run",
        AsyncMock(return_value=_fake_out("d", parsed=[{"path": "src/x.py", "content": "x"}])),
    )
    monkeypatch.setattr(
        wf.reviewer,
        "run",
        AsyncMock(
            return_value=_fake_out(
                "r", parsed={"verdict": "APPROVED", "quality_score": 0.9, "summary": "ok"}
            )
        ),
    )

    await wf.run(
        title="Endpoint FastAPI /version",
        description="Crée endpoint version retournant le numéro",
    )

    orch_call_input = orch_mock.call_args.args[0]
    assert "Missions similaires déjà réalisées" in orch_call_input.task
    assert "Endpoint FastAPI /health" in orch_call_input.task
