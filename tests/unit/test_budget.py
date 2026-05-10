"""Tests pour src.core.budget."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.core.budget import BudgetController, BudgetExceeded


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "budget_state.json"


def test_initial_state_has_zero_spent(state_path: Path) -> None:
    bc = BudgetController(state_path=state_path, daily_budget_usd=10.0)
    assert bc.spent_today == 0.0
    assert bc.remaining_today() == 10.0
    assert bc.percent_used() == 0.0


def test_record_increments_spent(state_path: Path) -> None:
    bc = BudgetController(state_path=state_path, daily_budget_usd=5.0)
    bc.record(1.5)
    assert bc.spent_today == 1.5
    bc.record(2.0)
    assert bc.spent_today == 3.5
    assert bc.remaining_today() == 1.5
    assert bc.percent_used() == 70.0


def test_record_negative_raises(state_path: Path) -> None:
    bc = BudgetController(state_path=state_path, daily_budget_usd=5.0)
    with pytest.raises(ValueError):
        bc.record(-1.0)


def test_can_proceed_within_budget(state_path: Path) -> None:
    bc = BudgetController(state_path=state_path, daily_budget_usd=10.0)
    bc.record(8.0)
    assert bc.can_proceed(1.0) is True
    assert bc.can_proceed(2.0) is True  # exactement la limite
    assert bc.can_proceed(2.5) is False


def test_assert_can_proceed_raises_when_over(state_path: Path) -> None:
    bc = BudgetController(state_path=state_path, daily_budget_usd=1.0)
    bc.record(1.0)
    with pytest.raises(BudgetExceeded, match="Budget journalier"):
        bc.assert_can_proceed(0.5)


def test_state_persists_across_instances(state_path: Path) -> None:
    bc1 = BudgetController(state_path=state_path, daily_budget_usd=10.0)
    bc1.record(3.14)
    bc2 = BudgetController(state_path=state_path, daily_budget_usd=10.0)
    assert bc2.spent_today == 3.14


def test_auto_reset_on_new_day(state_path: Path) -> None:
    """Si l'état a une date différente d'aujourd'hui, le cumul est réinitialisé."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    state_path.write_text(
        json.dumps({"date": yesterday, "spent_usd": 9.99, "history": []}),
        encoding="utf-8",
    )
    bc = BudgetController(state_path=state_path, daily_budget_usd=10.0)
    assert bc.spent_today == 0.0
    assert bc.remaining_today() == 10.0


def test_old_day_archived_in_history(state_path: Path) -> None:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    state_path.write_text(
        json.dumps({"date": yesterday, "spent_usd": 4.20, "history": []}),
        encoding="utf-8",
    )
    bc = BudgetController(state_path=state_path, daily_budget_usd=10.0)
    bc.record(0.10)  # déclenche persistence
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert raw["date"] == date.today().isoformat()
    assert any(h["date"] == yesterday and h["spent_usd"] == 4.20 for h in raw["history"])


def test_status_returns_full_snapshot(state_path: Path) -> None:
    bc = BudgetController(state_path=state_path, daily_budget_usd=10.0)
    bc.record(2.5)
    st = bc.status()
    assert st["date"] == date.today().isoformat()
    assert st["spent_usd"] == 2.5
    assert st["remaining_usd"] == 7.5
    assert st["percent_used"] == 25.0


def test_handles_corrupted_state(state_path: Path) -> None:
    state_path.write_text("not json at all {{{", encoding="utf-8")
    bc = BudgetController(state_path=state_path, daily_budget_usd=10.0)
    # Doit résister gracieusement
    assert bc.spent_today == 0.0
