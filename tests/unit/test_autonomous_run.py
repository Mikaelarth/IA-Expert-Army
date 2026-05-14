"""Tests pour scripts/autonomous_run.py — focus sur les pures fonctions.

`evaluate_guardrails`, `parse_queue` et `render_report` sont des pure
functions qui se testent sans I/O. Le `run_autonomous` lui-même
(le loop) est trop intégré pour un test unit — il est validé en
smoke run avec une queue de 3 missions réelles (cf. ADR-010).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from autonomous_run import (  # type: ignore[import-not-found]  # noqa: E402
    DEFAULTS,
    QueueItem,
    RunRecord,
    evaluate_guardrails,
    parse_queue,
    render_report,
)

from src.core.killswitch import Killswitch, KillswitchEngaged


# ===== Fixtures =====


@pytest.fixture
def clear_killswitch(tmp_path: Path) -> Killswitch:
    return Killswitch(tmp_path / ".killswitch")


@pytest.fixture
def engaged_killswitch(tmp_path: Path) -> Killswitch:
    ks = Killswitch(tmp_path / ".killswitch")
    ks.engage(reason="test")
    return ks


def _record(
    success: bool = True,
    quality: float | None = 0.85,
    saturated: bool = False,
    errored: bool = False,
) -> RunRecord:
    now = datetime.now(UTC)
    return RunRecord(
        started_at=now,
        ended_at=now + timedelta(seconds=10),
        title="t",
        guild="engineering",
        verdict="APPROVED" if success and not errored else ("FAILED:x" if errored else "NEEDS_CHANGES"),
        quality=quality,
        cost=0.1,
        duration=10.0,
        saturated=saturated,
        error="boom" if errored else None,
    )


# ===== parse_queue =====


def test_parse_queue_minimal_valid() -> None:
    yml = """
missions:
  - title: "Build API"
    description: "Crée un endpoint"
"""
    items = parse_queue(yml)
    assert len(items) == 1
    assert items[0].title == "Build API"
    assert items[0].force_guild is None


def test_parse_queue_with_guild() -> None:
    yml = """
missions:
  - title: "Roadmap"
    description: "Plan 3 jalons"
    guild: Business
"""
    items = parse_queue(yml)
    assert items[0].force_guild == "business"


def test_parse_queue_rejects_missing_description() -> None:
    yml = """
missions:
  - title: "Incomplete"
"""
    with pytest.raises(ValueError, match="description requis"):
        parse_queue(yml)


def test_parse_queue_rejects_non_list() -> None:
    yml = "missions: not_a_list"
    with pytest.raises(ValueError, match="liste"):
        parse_queue(yml)


def test_parse_queue_empty_missions_is_ok() -> None:
    """Un fichier sans missions retourne une liste vide (pas d'erreur)."""
    assert parse_queue("missions: []") == []
    assert parse_queue("{}") == []


def test_parse_queue_multiline_description() -> None:
    yml = """
missions:
  - title: "Multi"
    description: |
      Première ligne.
      Deuxième ligne.
"""
    items = parse_queue(yml)
    assert "Première" in items[0].description
    assert "Deuxième" in items[0].description


# ===== evaluate_guardrails =====


def test_guardrails_pass_with_empty_history(clear_killswitch: Killswitch) -> None:
    ok, reason = evaluate_guardrails([], 50.0, clear_killswitch, DEFAULTS)
    assert ok
    assert reason is None


def test_guardrails_fail_when_budget_below_floor(clear_killswitch: Killswitch) -> None:
    ok, reason = evaluate_guardrails([], 1.0, clear_killswitch, DEFAULTS)
    assert not ok
    assert reason is not None
    assert "budget" in reason.lower()


def test_guardrails_fail_when_killswitch_engaged(engaged_killswitch: Killswitch) -> None:
    ok, reason = evaluate_guardrails([], 50.0, engaged_killswitch, DEFAULTS)
    assert not ok
    assert reason is not None
    assert "killswitch" in reason.lower()


def test_guardrails_fail_when_error_rate_too_high(clear_killswitch: Killswitch) -> None:
    # 3 errored / 5 = 60% > 30%
    hist = [_record(errored=True) for _ in range(3)] + [_record() for _ in range(2)]
    ok, reason = evaluate_guardrails(hist, 50.0, clear_killswitch, DEFAULTS)
    assert not ok
    assert reason is not None
    assert "error rate" in reason


def test_guardrails_fail_when_saturation_rate_too_high(clear_killswitch: Killswitch) -> None:
    # 2 saturated / 5 = 40% > 20%
    hist = [_record(saturated=True) for _ in range(2)] + [_record() for _ in range(3)]
    ok, reason = evaluate_guardrails(hist, 50.0, clear_killswitch, DEFAULTS)
    assert not ok
    assert reason is not None
    assert "saturation" in reason


def test_guardrails_fail_on_quality_drift(clear_killswitch: Killswitch) -> None:
    """Moving avg quality des N dernières < seuil → STOP."""
    hist = [_record(quality=0.50) for _ in range(5)]
    ok, reason = evaluate_guardrails(hist, 50.0, clear_killswitch, DEFAULTS)
    assert not ok
    assert reason is not None
    assert "quality" in reason or "dérive" in reason


def test_guardrails_pass_when_all_metrics_healthy(clear_killswitch: Killswitch) -> None:
    hist = [_record(quality=0.9) for _ in range(5)]
    ok, reason = evaluate_guardrails(hist, 50.0, clear_killswitch, DEFAULTS)
    assert ok
    assert reason is None


def test_guardrails_only_considers_window(clear_killswitch: Killswitch) -> None:
    """Une vieille mauvaise mission hors fenêtre ne doit pas faire échouer."""
    # 10 vieilles errored, 5 récentes good → la fenêtre = 5 récentes → OK
    hist = [_record(errored=True) for _ in range(10)] + [_record(quality=0.9) for _ in range(5)]
    ok, _ = evaluate_guardrails(hist, 50.0, clear_killswitch, DEFAULTS)
    assert ok


# ===== render_report =====


def test_render_report_empty_history() -> None:
    started = datetime(2026, 5, 11, 10, 0, tzinfo=UTC)
    ended = started + timedelta(minutes=1)
    report = render_report(started, ended, [], "queue épuisée", 50.0, 50.0)
    assert "Missions exécutées :** 0" in report
    assert "aucune mission" in report.lower()


def test_render_report_includes_timeline_rows() -> None:
    started = datetime(2026, 5, 11, 10, 0, tzinfo=UTC)
    hist = [_record(), _record(success=False)]
    report = render_report(started, started + timedelta(minutes=2), hist, "queue épuisée", 50.0, 49.8)
    assert "APPROVED" in report
    assert "NEEDS_CHANGES" in report
    assert "50%" in report  # 1 success / 2


def test_render_report_shows_stop_reason() -> None:
    started = datetime(2026, 5, 11, 10, 0, tzinfo=UTC)
    report = render_report(
        started, started + timedelta(minutes=1), [], "budget seuil atteint", 50.0, 4.5
    )
    assert "budget seuil atteint" in report


def test_render_report_marks_saturation() -> None:
    started = datetime(2026, 5, 11, 10, 0, tzinfo=UTC)
    hist = [_record(saturated=True)]
    report = render_report(started, started + timedelta(minutes=1), hist, "queue épuisée", 50.0, 49.9)
    assert "⚠" in report  # marker saturation dans la table


# ===== RunRecord behaviour =====


def test_run_record_success_property() -> None:
    r = _record(success=True)
    assert r.success is True
    r2 = _record(success=False)
    assert r2.success is False


def test_run_record_errored_property_on_exception() -> None:
    r = _record(errored=True)
    assert r.errored is True


def test_run_record_errored_property_on_failed_verdict() -> None:
    """Un verdict 'FAILED:...' compte comme errored même sans exception levée."""
    now = datetime.now(UTC)
    r = RunRecord(
        started_at=now,
        ended_at=now,
        title="t",
        guild="x",
        verdict="FAILED:budget",
        quality=None,
        cost=0,
        duration=0,
        saturated=False,
    )
    assert r.errored is True
