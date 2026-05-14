"""Tests Sprint ZZ — opérationnalisation du Quality Guardian.

Couvre les 3 hooks qui rendent le QG actionnable :
- ZZ.0 : FileMemory.update_mission_summary_metadata persiste les champs qg_*
- ZZ.2 : PatternMiner filtre les épisodes des missions où qg_verdict ∈ {NEEDS_REWORK, ESCALATE}
- ZZ.3 : daily_digest._compute_qg_stats agrège les métriques QG correctement
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

from src.memory.file_memory import FileMemory, MemoryRecord

# ===== ZZ.0 — Persistence qg_* dans mission summary =====


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def test_update_mission_summary_metadata_patches_existing(memory: FileMemory) -> None:
    """L'update doit injecter les champs sans toucher au body ou aux champs existants."""
    mid = str(uuid4())
    initial = MemoryRecord(
        metadata={"title": "Test", "final_verdict": "APPROVED", "quality_score": 0.9},
        body="# Test\n\nbody original",
    )
    memory.write_mission_summary(mid, initial)

    updated = memory.update_mission_summary_metadata(
        mid,
        qg_verdict="ACCEPT",
        qg_final_score=0.85,
        qg_concerns=["c1"],
        qg_rationale="OK",
    )

    assert updated is not None
    assert updated.metadata["qg_verdict"] == "ACCEPT"
    assert updated.metadata["qg_final_score"] == 0.85
    assert updated.metadata["qg_concerns"] == ["c1"]
    # Les champs existants sont préservés
    assert updated.metadata["title"] == "Test"
    assert updated.metadata["final_verdict"] == "APPROVED"
    assert updated.body == "# Test\n\nbody original"

    # Vérifier qu'on relit bien les champs après réécriture sur disque
    re_read = memory.get_mission_summary(mid)
    assert re_read is not None
    assert re_read.metadata["qg_verdict"] == "ACCEPT"


def test_update_mission_summary_metadata_returns_none_when_not_found(
    memory: FileMemory,
) -> None:
    """Mission absente → None (silent fail, pas critique pour le run)."""
    result = memory.update_mission_summary_metadata(
        "00000000-0000-0000-0000-000000000000", qg_verdict="ACCEPT"
    )
    assert result is None


# ===== ZZ.2 — PatternMiner filtre les missions NEEDS_REWORK / ESCALATE =====


def _write_mission_and_episode(
    memory: FileMemory,
    mission_id: str,
    agent: str,
    qg_verdict: str | None = None,
    final_verdict: str = "APPROVED",
    quality_score: float = 0.9,
) -> None:
    """Helper : écrit une paire mission summary + 1 épisode pour cet agent."""
    mission_meta = {
        "mission_id": mission_id,
        "title": f"Mission {mission_id[:8]}",
        "final_verdict": final_verdict,
        "quality_score": quality_score,
    }
    if qg_verdict is not None:
        mission_meta["qg_verdict"] = qg_verdict
    memory.write_mission_summary(
        mission_id, MemoryRecord(metadata=mission_meta, body=f"# {mission_id}")
    )
    memory.write_episode(
        mission_id,
        agent,
        MemoryRecord(
            metadata={
                "mission_id": mission_id,
                "agent": agent,
                "success": True,
                "final_verdict": final_verdict,
                "quality_score": quality_score,
                "saturated": False,
            },
            body=f"## Sortie\nÉpisode de {agent}",
        ),
    )


def test_pattern_miner_filters_episodes_when_qg_needs_rework(
    memory: FileMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sprint ZZ.2 : un épisode d'une mission QG NEEDS_REWORK est exclu du mining."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    from src.learning.pattern_miner import PatternMiner
    from src.learning.skills_library import SkillsLibrary

    skills = SkillsLibrary(memory.root.parent / "skills")
    miner = PatternMiner(memory=memory, skills=skills, min_episodes=1, top_k=3, min_quality=0.5)

    # Mission 1 : QG ACCEPT → épisode minable
    mid_ok = str(uuid4())
    _write_mission_and_episode(memory, mid_ok, "backend_developer", qg_verdict="ACCEPT")
    # Mission 2 : QG NEEDS_REWORK → épisode FILTRÉ
    mid_rework = str(uuid4())
    _write_mission_and_episode(memory, mid_rework, "backend_developer", qg_verdict="NEEDS_REWORK")
    # Mission 3 : QG ESCALATE → épisode FILTRÉ aussi
    mid_escalate = str(uuid4())
    _write_mission_and_episode(memory, mid_escalate, "backend_developer", qg_verdict="ESCALATE")
    # Mission 4 : pas de QG (legacy) → mineable (no signal = no penalty)
    mid_legacy = str(uuid4())
    _write_mission_and_episode(memory, mid_legacy, "backend_developer", qg_verdict=None)

    grouped = miner._load_eligible_episodes()

    dev_eps = grouped.get("backend_developer", [])
    mission_ids_kept = {ep[1].metadata["mission_id"] for ep in dev_eps}
    assert mid_ok in mission_ids_kept, "Mission QG ACCEPT doit être conservée"
    assert mid_legacy in mission_ids_kept, "Mission sans QG (legacy) doit être conservée"
    assert mid_rework not in mission_ids_kept, "Mission QG NEEDS_REWORK doit être filtrée"
    assert mid_escalate not in mission_ids_kept, "Mission QG ESCALATE doit être filtrée"


def test_pattern_miner_does_not_filter_when_no_qg_data(
    memory: FileMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Régression : missions legacy sans qg_verdict → mining inchangé (pas de pénalité)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    from src.learning.pattern_miner import PatternMiner
    from src.learning.skills_library import SkillsLibrary

    skills = SkillsLibrary(memory.root.parent / "skills")
    miner = PatternMiner(memory=memory, skills=skills, min_episodes=1, top_k=3, min_quality=0.5)

    # Toutes les missions sans qg_verdict (cas avant Sprint YY)
    for _ in range(3):
        _write_mission_and_episode(memory, str(uuid4()), "backend_developer", qg_verdict=None)

    grouped = miner._load_eligible_episodes()
    assert len(grouped.get("backend_developer", [])) == 3


# ===== ZZ.3 — Métriques QG dans daily_digest =====

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from daily_digest import _compute_qg_stats  # type: ignore[import-not-found]  # noqa: E402


def _mission_with_qg(
    qg_verdict: str | None = "ACCEPT",
    qg_final_score: float | None = 0.9,
    guild_score: float = 0.9,
    guild_verdict: str = "APPROVED",
) -> tuple[Path, MemoryRecord]:
    """Helper : tuple (path, record) imitant ce que _missions_for_date retourne."""
    meta: dict = {
        "title": "Test",
        "final_verdict": guild_verdict,
        "quality_score": guild_score,
    }
    if qg_verdict is not None:
        meta["qg_verdict"] = qg_verdict
    if qg_final_score is not None:
        meta["qg_final_score"] = qg_final_score
    rec = MemoryRecord(metadata=meta, body="")
    # Le path est juste un placeholder — _compute_qg_stats n'y touche pas
    return (Path("fake.md"), rec)


def test_compute_qg_stats_empty_missions() -> None:
    stats = _compute_qg_stats([])
    assert stats["count_with_qg"] == 0
    assert stats["divergence_count"] == 0
    assert stats["score_diff_significant"] == 0


def test_compute_qg_stats_counts_missions_with_qg() -> None:
    """Seules les missions avec qg_verdict sont comptées."""
    missions = [
        _mission_with_qg(qg_verdict="ACCEPT"),
        _mission_with_qg(qg_verdict=None),  # legacy, pas compté
        _mission_with_qg(qg_verdict="NEEDS_REWORK"),
    ]
    stats = _compute_qg_stats(missions)
    assert stats["count_with_qg"] == 2
    assert stats["verdict_counts"]["ACCEPT"] == 1
    assert stats["verdict_counts"]["NEEDS_REWORK"] == 1


def test_compute_qg_stats_detects_divergence() -> None:
    """Une mission APPROVED par la guilde mais NON ACCEPT par QG = divergence."""
    missions = [
        _mission_with_qg(qg_verdict="ACCEPT", guild_verdict="APPROVED"),  # OK
        _mission_with_qg(qg_verdict="NEEDS_REWORK", guild_verdict="APPROVED"),  # divergence
        _mission_with_qg(qg_verdict="ESCALATE", guild_verdict="APPROVED"),  # divergence aussi
        _mission_with_qg(qg_verdict="ACCEPT", guild_verdict="NEEDS_CHANGES"),  # pas de divergence
    ]
    stats = _compute_qg_stats(missions)
    assert stats["divergence_count"] == 2


def test_compute_qg_stats_detects_significant_score_diff() -> None:
    """|qg_final_score - guild_score| > 0.10 → compté comme drift de calibration."""
    missions = [
        _mission_with_qg(qg_final_score=0.95, guild_score=0.92),  # diff 0.03, pas significant
        _mission_with_qg(qg_final_score=0.70, guild_score=0.90),  # diff 0.20, significant
        _mission_with_qg(qg_final_score=0.80, guild_score=0.85),  # diff 0.05, pas significant
        _mission_with_qg(qg_final_score=0.95, guild_score=0.70),  # diff 0.25, significant
    ]
    stats = _compute_qg_stats(missions)
    assert stats["score_diff_significant"] == 2


def test_compute_qg_stats_ignores_missing_scores() -> None:
    """Si qg_final_score ou guild_score manque, on n'inclut pas dans score_diff."""
    missions = [
        _mission_with_qg(qg_final_score=None, guild_score=0.9),
        _mission_with_qg(qg_final_score=0.9, guild_score=None),
    ]
    # Patch manuel pour mettre guild_score à None
    missions[1][1].metadata["quality_score"] = None  # type: ignore[assignment]
    stats = _compute_qg_stats(missions)
    # count_with_qg = 2 (le qg_verdict est présent dans les 2)
    assert stats["count_with_qg"] == 2
    # Mais aucune n'a les 2 scores → 0 dans score_diff_significant
    assert stats["score_diff_significant"] == 0
