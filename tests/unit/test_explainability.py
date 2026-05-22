"""Tests v0.9.0 C1 — services explainability."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from src.gui.services.explainability import (
    ClassificationExplanation,
    compute_agent_metrics,
    explain_guild_classification,
    explain_mission_verdict,
)
from src.memory.file_memory import FileMemory, MemoryRecord

# ---------------------------------------------------------------------------
# explain_guild_classification
# ---------------------------------------------------------------------------


def test_explain_engineering_clear_winner() -> None:
    expl = explain_guild_classification(
        title="Crée endpoint FastAPI /health",
        description="GET /health retourne 200 OK avec router et tests pytest.",
    )
    assert isinstance(expl, ClassificationExplanation)
    assert expl.winner == "engineering"
    assert expl.is_tie is False
    # Scores triés desc — engineering doit être premier
    assert expl.scores[0].guild == "engineering"
    assert expl.scores[0].total_score > 0
    # Mots-clés engineering matchés visibles
    matched_kws = {m.keyword for m in expl.scores[0].matches}
    assert "fastapi" in matched_kws or "endpoint" in matched_kws


def test_explain_research_clear_winner() -> None:
    expl = explain_guild_classification(
        title="Synthétise les bonnes pratiques 2026 pour FastAPI",
        description="Comparatif des approches modernes, état de l'art.",
    )
    assert expl.winner == "research"


def test_explain_creative_clear_winner() -> None:
    expl = explain_guild_classification(
        title="Rédige une landing page SaaS",
        description="Copywriting marketing pour startup B2B.",
    )
    assert expl.winner == "creative"


def test_explain_business_clear_winner() -> None:
    expl = explain_guild_classification(
        title="Roadmap projet open-source",
        description="Plan business avec milestones et go-to-market.",
    )
    assert expl.winner == "business"


def test_explain_returns_all_four_guilds() -> None:
    """Même quand un seul mot-clé matche, toutes les guildes sont dans scores."""
    expl = explain_guild_classification("Mission vide", "Sans mot-clé spécifique.")
    assert {s.guild for s in expl.scores} == {
        "engineering",
        "research",
        "creative",
        "business",
    }


def test_explain_tie_resolved_by_engineering_first() -> None:
    """Tie 0-0 sur titre/desc neutres → engineering gagne par tie-break."""
    expl = explain_guild_classification("Mission neutre", "Texte sans mot-clé.")
    assert expl.scores[0].total_score == 0
    assert expl.is_tie is True
    assert expl.winner == "engineering"  # premier dans tie_break_order


def test_explain_keyword_match_attributes() -> None:
    """Les KeywordMatch exposent in_title, is_strong_verb, weight."""
    expl = explain_guild_classification(
        title="Implémente une fonction Python",
        description="Code la fonction.",
    )
    eng = next(s for s in expl.scores if s.guild == "engineering")
    impl_matches = [m for m in eng.matches if m.keyword.startswith("impl")]
    assert impl_matches, "implémente devrait être détecté"
    assert impl_matches[0].in_title is True
    assert impl_matches[0].weight > 0


# ---------------------------------------------------------------------------
# compute_agent_metrics
# ---------------------------------------------------------------------------


def _add_episode(
    memory: FileMemory,
    agent: str,
    success: bool = True,
    duration: float = 1.0,
    cost: float = 0.0,
    tokens_out: int = 100,
    saturated: bool = False,
    quality_score: float | None = None,
) -> None:
    meta = {
        "agent": agent,
        "success": success,
        "duration_seconds": duration,
        "cost_usd": cost,
        "tokens_out": tokens_out,
        "saturated": saturated,
    }
    if quality_score is not None:
        meta["quality_score"] = quality_score
    record = MemoryRecord(metadata=meta, body=f"## Sortie\n\nepisode {agent}")
    memory.write_episode(uuid4(), agent, record)


def test_compute_agent_metrics_empty_memory(tmp_path: Path) -> None:
    memory = FileMemory(tmp_path / "memory")
    assert compute_agent_metrics(memory) == []


def test_compute_agent_metrics_aggregates_per_agent(tmp_path: Path) -> None:
    memory = FileMemory(tmp_path / "memory")
    # 3 épisodes architect (1 fail), 2 développer
    _add_episode(memory, "software_architect", success=True, duration=10, cost=0.01)
    _add_episode(memory, "software_architect", success=True, duration=20, cost=0.02)
    _add_episode(memory, "software_architect", success=False, duration=5, cost=0.0)
    _add_episode(memory, "backend_developer", success=True, duration=15, cost=0.015, tokens_out=200)
    _add_episode(memory, "backend_developer", success=True, duration=25, cost=0.025, tokens_out=400)

    metrics = compute_agent_metrics(memory)
    by_agent = {m.agent_name: m for m in metrics}

    assert by_agent["software_architect"].n_episodes == 3
    assert by_agent["software_architect"].n_success == 2
    assert by_agent["software_architect"].success_rate == pytest.approx(2 / 3)
    # avg_duration : (10 + 20 + 5) / 3 = 11.67
    assert by_agent["software_architect"].avg_duration_seconds == pytest.approx(11.67, rel=1e-2)
    assert by_agent["software_architect"].total_cost_usd == pytest.approx(0.03, rel=1e-3)

    assert by_agent["backend_developer"].n_episodes == 2
    assert by_agent["backend_developer"].success_rate == 1.0
    assert by_agent["backend_developer"].avg_tokens_out == 300.0


def test_compute_agent_metrics_sorted_by_n_episodes_desc(tmp_path: Path) -> None:
    memory = FileMemory(tmp_path / "memory")
    for _ in range(5):
        _add_episode(memory, "popular_agent")
    _add_episode(memory, "rare_agent")

    metrics = compute_agent_metrics(memory)
    assert metrics[0].agent_name == "popular_agent"
    assert metrics[-1].agent_name == "rare_agent"


def test_compute_agent_metrics_includes_quality_score_when_present(tmp_path: Path) -> None:
    memory = FileMemory(tmp_path / "memory")
    _add_episode(memory, "reviewer", quality_score=0.90)
    _add_episode(memory, "reviewer", quality_score=0.95)
    _add_episode(memory, "reviewer")  # sans score

    metrics = compute_agent_metrics(memory)
    rev = next(m for m in metrics if m.agent_name == "reviewer")
    # avg sur les 2 épisodes scorés uniquement
    assert rev.avg_quality_score == pytest.approx(0.925, abs=1e-3)


def test_compute_agent_metrics_saturation_rate(tmp_path: Path) -> None:
    memory = FileMemory(tmp_path / "memory")
    _add_episode(memory, "tech_watch", saturated=True)
    _add_episode(memory, "tech_watch", saturated=False)
    _add_episode(memory, "tech_watch", saturated=False)

    metrics = compute_agent_metrics(memory)
    tw = next(m for m in metrics if m.agent_name == "tech_watch")
    assert tw.n_saturated == 1
    assert tw.saturation_rate == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# explain_mission_verdict
# ---------------------------------------------------------------------------


def test_explain_mission_verdict_missing_returns_none(tmp_path: Path) -> None:
    memory = FileMemory(tmp_path / "memory")
    assert explain_mission_verdict(memory, "nonexistent-mission-id") is None


def test_explain_mission_verdict_returns_summary_fields(tmp_path: Path) -> None:
    memory = FileMemory(tmp_path / "memory")
    mid = uuid4()
    memory.write_mission_summary(
        mid,
        MemoryRecord(
            metadata={
                "title": "T",
                "final_verdict": "APPROVED",
                "quality_score": 0.88,
                "review_summary": "Tests verts, doc claire.",
                "guild": "engineering",
            },
            body="body",
        ),
    )

    expl = explain_mission_verdict(memory, str(mid))
    assert expl is not None
    assert expl.final_verdict == "APPROVED"
    assert expl.quality_score == 0.88
    assert "Tests verts" in expl.review_summary


def test_explain_mission_verdict_attaches_reviewer_episode_when_present(tmp_path: Path) -> None:
    """Si l'épisode du code_reviewer existe pour la mission, on l'attache."""
    memory = FileMemory(tmp_path / "memory")
    mid = uuid4()

    # Crée le summary
    memory.write_mission_summary(
        mid,
        MemoryRecord(
            metadata={"title": "T", "final_verdict": "APPROVED", "quality_score": 0.9},
            body="body",
        ),
    )

    # Crée un épisode reviewer pour cette mission
    reviewer_record = MemoryRecord(
        metadata={"agent": "code_reviewer", "mission_id": str(mid), "success": True},
        body="verdict: APPROVED\nquality_score: 0.9\nrationale: pertinent\n",
    )
    memory.write_episode(mid, "code_reviewer", reviewer_record)

    expl = explain_mission_verdict(memory, str(mid))
    assert expl is not None
    assert expl.review_raw_yaml is not None
    assert "rationale: pertinent" in expl.review_raw_yaml
    assert expl.reviewer_episode_path is not None
