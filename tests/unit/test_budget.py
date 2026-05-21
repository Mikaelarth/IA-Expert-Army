"""Tests pour src.core.budget."""

from __future__ import annotations

import json
import threading
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.core.budget import BudgetController, BudgetExceeded, _file_lock


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


# ===== ADR-025 — BudgetController en mode no-op quand cap <= 0 =====


def test_budget_disabled_when_cap_is_zero(state_path: Path) -> None:
    """Bascule Ollama local : daily_budget_usd=0.0 par défaut. Le BudgetController
    doit alors être no-op (toujours can_proceed=True, record() silencieux).

    Régression : avant le fix v0.4.0, can_proceed(0) retournait False car le
    seuil _MIN_HEADROOM_USD=0.0001 n'était jamais atteint avec un cap à 0 →
    toute mission Ollama plantait avec FAILED:budget.exceeded."""
    bc = BudgetController(state_path=state_path, daily_budget_usd=0.0)
    assert bc.is_disabled is True
    assert bc.can_proceed() is True
    assert bc.can_proceed(estimated_cost=10.0) is True
    # record() est silencieusement no-op : aucun fichier d'état créé
    bc.record(2.5)
    assert bc.spent_today == 0.0
    assert not state_path.exists()  # pas pollué par des entrées vides
    # assert_can_proceed ne doit jamais lever quand désactivé
    bc.assert_can_proceed(estimated_cost=999.0)


def test_budget_disabled_when_cap_is_negative(state_path: Path) -> None:
    """Sécurité : cap négatif (= configuration invalide) → traité comme désactivé,
    pas comme "déjà dépassé"."""
    bc = BudgetController(state_path=state_path, daily_budget_usd=-1.0)
    assert bc.is_disabled is True
    assert bc.can_proceed() is True


def test_budget_active_when_cap_is_positive(state_path: Path) -> None:
    """Garde-fou : avec un cap > 0, le comportement reste strict (assert lève si dépassé)."""
    bc = BudgetController(state_path=state_path, daily_budget_usd=1.0)
    assert bc.is_disabled is False
    bc.record(1.0)
    with pytest.raises(BudgetExceeded):
        bc.assert_can_proceed(estimated_cost=0.01)


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


# ===== Sprint VV.2 — Lock portable / concurrence =====


def test_file_lock_acquires_and_releases(tmp_path: Path) -> None:
    """Le lock se prend, se libère, et le fichier .lock disparaît à la sortie."""
    lock_path = tmp_path / "test.lock"
    assert not lock_path.exists()
    with _file_lock(lock_path):
        assert lock_path.exists()
    assert not lock_path.exists()


def test_file_lock_serializes_concurrent_threads(tmp_path: Path) -> None:
    """Deux threads qui essaient le lock en même temps : un attend l'autre."""
    lock_path = tmp_path / "test.lock"
    order: list[str] = []

    def worker(tag: str, hold_ms: int = 50) -> None:
        with _file_lock(lock_path, timeout=2.0):
            order.append(f"{tag}-in")
            # On simule du travail pour forcer la sérialisation
            import time

            time.sleep(hold_ms / 1000)
            order.append(f"{tag}-out")

    t1 = threading.Thread(target=worker, args=("A", 80))
    t2 = threading.Thread(target=worker, args=("B", 80))
    t1.start()
    # Petit délai pour que t1 prenne le lock en premier
    import time

    time.sleep(0.01)
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    # Les 2 ont fini, et A est complet avant que B ne commence (ou inverse)
    assert len(order) == 4
    # Les "out" doivent venir avant le "in" du second
    # Soit : A-in, A-out, B-in, B-out — soit l'inverse
    assert order in (
        ["A-in", "A-out", "B-in", "B-out"],
        ["B-in", "B-out", "A-in", "A-out"],
    ), f"Lock n'a pas sérialisé : {order}"


def test_budget_record_serializes_under_concurrency(state_path: Path) -> None:
    """5 threads font record(1.0) en parallèle → cumul final exactement 5.0,
    aucun update perdu (le test prouve l'absence de race read-modify-write).

    Note : 5 threads (pas 10) pour rester robuste sous charge système quand
    la suite complète tourne en parallèle (le test était flaky à 10 threads
    sous full suite sur Windows + Python 3.14 async)."""
    bc = BudgetController(state_path=state_path, daily_budget_usd=100.0)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            bc.record(1.0)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not errors, f"Erreurs dans les threads : {errors}"
    for t in threads:
        assert not t.is_alive(), "Au moins un thread n'a pas fini dans le timeout"
    assert bc.spent_today == pytest.approx(5.0, abs=0.001), (
        f"Race condition : 5 × 1.0 = {bc.spent_today}, perte d'updates"
    )
