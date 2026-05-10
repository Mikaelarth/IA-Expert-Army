"""Tests pour src.memory.vector_memory.

Note : Chroma télécharge un modèle ONNX la première fois (~30 MB).
Sur CI sans cache, ces tests prennent quelques secondes au premier run.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.memory.vector_memory import EpisodeMatch, VectorMemory


@pytest.fixture
def vmem(tmp_path: Path) -> VectorMemory:
    return VectorMemory(persist_dir=tmp_path / "chroma")


def test_empty_search_returns_empty(vmem: VectorMemory) -> None:
    assert vmem.count() == 0
    assert vmem.search("anything") == []


def test_add_then_search_finds_relevant(vmem: VectorMemory) -> None:
    vmem.add_episode(
        "ep1",
        "Implementation of a FastAPI health endpoint with Pydantic model and uptime tracking",
        {"agent": "software_architect", "success": True, "quality_score": 0.93},
    )
    vmem.add_episode(
        "ep2",
        "Celery worker processing async background jobs from Redis queue",
        {"agent": "software_architect", "success": True, "quality_score": 0.87},
    )
    vmem.add_episode(
        "ep3",
        "React component for user profile editing with form validation",
        {"agent": "frontend_developer", "success": True, "quality_score": 0.90},
    )

    results = vmem.search("design a healthcheck REST endpoint", n_results=2)
    assert len(results) == 2
    # Le résultat le plus pertinent doit être ep1 (l'endpoint health)
    assert results[0].episode_id == "ep1"
    assert results[0].distance < results[1].distance  # ep1 plus proche que ep2


def test_filter_by_metadata(vmem: VectorMemory) -> None:
    vmem.add_episode("ep1", "fastapi endpoint", {"agent": "software_architect"})
    vmem.add_episode("ep2", "fastapi endpoint", {"agent": "code_reviewer"})

    results = vmem.search("endpoint", n_results=5, where={"agent": "software_architect"})
    assert len(results) == 1
    assert results[0].episode_id == "ep1"


def test_max_distance_filter(vmem: VectorMemory) -> None:
    vmem.add_episode("ep1", "completely unrelated content about cooking pasta", {"agent": "x"})

    # Distance énorme attendue → filtrée
    results = vmem.search("design a database schema", max_distance=0.1)
    assert results == []


def test_count_increments(vmem: VectorMemory) -> None:
    assert vmem.count() == 0
    vmem.add_episode("a", "x", {"k": "v"})
    assert vmem.count() == 1
    vmem.add_episode("b", "y", {"k": "v"})
    assert vmem.count() == 2


def test_upsert_is_idempotent(vmem: VectorMemory) -> None:
    """Le même episode_id écrasé deux fois ne double pas le compte."""
    vmem.add_episode("ep1", "first version", {"v": 1})
    vmem.add_episode("ep1", "second version", {"v": 2})
    assert vmem.count() == 1


def test_metadata_flattening_handles_non_scalars(vmem: VectorMemory) -> None:
    """Les valeurs non-scalaires sont converties en str par sécurité Chroma."""
    vmem.add_episode(
        "ep1",
        "test",
        {
            "string_val": "hello",
            "int_val": 42,
            "float_val": 3.14,
            "bool_val": True,
            "none_val": None,  # ignoré
            "list_val": [1, 2, 3],  # str-ifié
            "dict_val": {"k": "v"},  # str-ifié
        },
    )
    results = vmem.search("test", n_results=1)
    assert len(results) == 1
    meta = results[0].metadata
    assert meta["string_val"] == "hello"
    assert meta["int_val"] == 42
    assert meta["float_val"] == 3.14
    assert meta["bool_val"] is True
    assert "none_val" not in meta
    assert isinstance(meta["list_val"], str)
    assert isinstance(meta["dict_val"], str)


def test_episode_match_pydantic_shape() -> None:
    m = EpisodeMatch(episode_id="x", document="d", metadata={"k": "v"}, distance=0.5)
    assert m.episode_id == "x"
    assert m.distance == 0.5
