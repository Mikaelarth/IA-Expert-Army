"""Tests pour le helper _compute_meta_stats du daily_digest.

On teste uniquement le pur calcul d'agrégation — le rendu markdown est
visuel et se valide en smoke-run sur de vraies meta-missions du jour
(cf. scripts/daily_digest.py output sur une date avec activity).
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock

# Le daily_digest est un script CLI, pas un package — on l'importe
# explicitement via sys.path comme tests/unit/test_apply_mission_validate.py.
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from daily_digest import _compute_meta_stats  # type: ignore[import-not-found]  # noqa: E402


def _meta(
    cost: float = 2.5,
    duration: float = 555.0,
    score: float | None = 0.91,
    verdict: str = "APPROVED",
    guilds: list[str] | None = None,
    n_sub: int = 3,
) -> MagicMock:
    """Construit un MemoryRecord-like mock avec frontmatter metadata."""
    rec = MagicMock()
    rec.metadata = {
        "total_cost_usd": cost,
        "total_duration_seconds": duration,
        "overall_quality_score": score,
        "final_verdict": verdict,
        "guilds": guilds or ["business", "engineering", "creative"],
        "n_sub_missions": n_sub,
    }
    return rec


def test_compute_meta_stats_empty_list() -> None:
    """Liste vide : tout à 0, pas de crash sur la division avg_score."""
    stats = _compute_meta_stats([])
    assert stats["count"] == 0
    assert stats["total_cost"] == 0.0
    assert stats["total_duration"] == 0.0
    assert stats["avg_score"] is None
    assert stats["avg_n_sub"] == 0.0
    assert stats["verdict_counts"] == Counter()
    assert stats["guilds_counts"] == Counter()


def test_compute_meta_stats_single_mission() -> None:
    metas = [("path1", _meta(cost=2.5, duration=555.0, score=0.91))]
    stats = _compute_meta_stats(metas)
    assert stats["count"] == 1
    assert stats["total_cost"] == 2.5
    assert stats["total_duration"] == 555.0
    assert stats["avg_score"] == 0.91
    assert stats["avg_n_sub"] == 3.0
    assert stats["verdict_counts"]["APPROVED"] == 1


def test_compute_meta_stats_sums_cost_and_duration() -> None:
    metas = [
        ("p1", _meta(cost=2.5, duration=555.0)),
        ("p2", _meta(cost=2.2, duration=394.0)),
        ("p3", _meta(cost=2.4, duration=625.0)),
    ]
    stats = _compute_meta_stats(metas)
    assert stats["count"] == 3
    assert stats["total_cost"] == 7.1
    assert stats["total_duration"] == 1574.0


def test_compute_meta_stats_averages_only_real_scores() -> None:
    """avg_score doit IGNORER les missions sans score (None) sans planter."""
    metas = [
        ("p1", _meta(score=0.91)),
        ("p2", _meta(score=None)),
        ("p3", _meta(score=0.85)),
    ]
    stats = _compute_meta_stats(metas)
    assert stats["avg_score"] == pytest_approx(0.88, abs=0.01)


def test_compute_meta_stats_aggregates_verdicts() -> None:
    metas = [
        ("p1", _meta(verdict="APPROVED")),
        ("p2", _meta(verdict="NEEDS_CHANGES")),
        ("p3", _meta(verdict="APPROVED")),
        ("p4", _meta(verdict="REJECTED")),
    ]
    stats = _compute_meta_stats(metas)
    assert stats["verdict_counts"]["APPROVED"] == 2
    assert stats["verdict_counts"]["NEEDS_CHANGES"] == 1
    assert stats["verdict_counts"]["REJECTED"] == 1


def test_compute_meta_stats_aggregates_guilds() -> None:
    """Une guilde qui apparaît dans plusieurs meta-missions est comptée plusieurs fois."""
    metas = [
        ("p1", _meta(guilds=["business", "engineering"])),
        ("p2", _meta(guilds=["business", "creative"])),
        ("p3", _meta(guilds=["engineering", "creative", "research"])),
    ]
    stats = _compute_meta_stats(metas)
    # business apparaît 2× (p1, p2), engineering 2× (p1, p3), creative 2× (p2, p3), research 1×
    assert stats["guilds_counts"]["business"] == 2
    assert stats["guilds_counts"]["engineering"] == 2
    assert stats["guilds_counts"]["creative"] == 2
    assert stats["guilds_counts"]["research"] == 1


def test_compute_meta_stats_tolerates_missing_fields() -> None:
    """Si une meta-mission a un frontmatter pauvre, on ne crash pas."""
    incomplete = MagicMock()
    incomplete.metadata = {"final_verdict": "APPROVED"}  # tout le reste manquant
    metas = [("p1", incomplete)]
    stats = _compute_meta_stats(metas)
    assert stats["count"] == 1
    assert stats["total_cost"] == 0.0
    assert stats["total_duration"] == 0.0
    assert stats["avg_score"] is None
    assert stats["verdict_counts"]["APPROVED"] == 1


# Helper local — évite d'avoir à importer pytest juste pour approx
def pytest_approx(value: float, abs: float = 0.01):
    class _Approx:
        def __eq__(self, other: object) -> bool:
            return isinstance(other, (int, float)) and abs_diff(other, value) <= abs

    def abs_diff(a: float, b: float) -> float:
        return a - b if a >= b else b - a

    return _Approx()
