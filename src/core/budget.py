"""BudgetController — plafond journalier des dépenses API.

Garde-fou Phase 6 — l'état est persisté dans un JSON simple et auto-reset à minuit
(rotation par date). Toute consommation est enregistrée explicitement par le caller
(Workflow récupère le cost_usd de chaque AgentOutput).

Politique :
- can_proceed(estimate=0) : True si remaining_today >= estimate
- record(amount) : ajoute amount au cumul du jour, persiste
- Si une mission tente de démarrer alors que daily_budget est déjà atteint, on lève
  BudgetExceeded — le caller doit le catcher et retourner un MissionResult abort.

Concurrence (Sprint VV.2) : `record()` est protégé par un lock fichier portable
(`<state>.lock` via `O_CREAT | O_EXCL`). Permet à plusieurs sub-missions en
parallèle (MetaWorkflow) de consommer leur budget sans race read-modify-write.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


class BudgetExceeded(RuntimeError):
    """Levée quand une opération ferait dépasser le plafond journalier."""


def _today_iso() -> str:
    return date.today().isoformat()


@contextmanager
def _file_lock(lock_path: Path, timeout: float = 30.0) -> Iterator[None]:
    """Lock fichier portable via `O_CREAT | O_EXCL` (atomique sur tous les OS).

    Busy-wait avec sleep 50ms entre les tentatives. Si un lock semble bloqué
    > 2× timeout, on le considère stale et on force la prise (pour ne pas
    geler le système après un crash de process).

    Timeout défaut 30s : généreux pour absorber les variations de scheduling
    OS sous charge (test concurrence Sprint VV était flaky à 5s sous full
    pytest suite sur Windows + Python 3.14 async). En prod le lock est tenu
    <10ms, donc ce timeout n'est jamais atteint nominalement.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    fd: int | None = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                # Stale lock detection : un fichier vieux > 2× timeout est probablement
                # orphelin (process crashé sans cleanup).
                try:
                    age = time.time() - lock_path.stat().st_mtime
                    if age > timeout * 2:
                        lock_path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                raise TimeoutError(
                    f"Impossible d'acquérir le lock {lock_path} en {timeout}s"
                ) from None
            time.sleep(0.05)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        lock_path.unlink(missing_ok=True)


class BudgetController:
    def __init__(self, state_path: Path, daily_budget_usd: float) -> None:
        self.state_path = Path(state_path)
        self.daily_budget = float(daily_budget_usd)

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"date": _today_iso(), "spent_usd": 0.0, "history": []}
        try:
            data: dict[str, Any] = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"date": _today_iso(), "spent_usd": 0.0, "history": []}
        if data.get("date") != _today_iso():
            # Rotation : archive l'ancien jour dans l'historique
            history = list(data.get("history", []))
            if data.get("spent_usd", 0.0) > 0 and data.get("date"):
                history.append({"date": data["date"], "spent_usd": data["spent_usd"]})
            return {
                "date": _today_iso(),
                "spent_usd": 0.0,
                "history": history[-30:],
            }  # 30 derniers jours
        data.setdefault("history", [])
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @property
    def spent_today(self) -> float:
        return float(self._load().get("spent_usd", 0.0))

    def remaining_today(self) -> float:
        return max(0.0, self.daily_budget - self.spent_today)

    def percent_used(self) -> float:
        if self.daily_budget <= 0:
            return 0.0
        return round(100.0 * self.spent_today / self.daily_budget, 2)

    # Seuil minimal sous lequel on considère que le budget n'a plus rien à offrir.
    # Évite de laisser passer une mission alors que `remaining == 0` exactement.
    _MIN_HEADROOM_USD = 0.0001

    def can_proceed(self, estimated_cost: float = 0.0) -> bool:
        threshold = max(estimated_cost, self._MIN_HEADROOM_USD)
        return self.remaining_today() >= threshold

    def assert_can_proceed(self, estimated_cost: float = 0.0) -> None:
        if not self.can_proceed(estimated_cost):
            raise BudgetExceeded(
                f"Budget journalier dépassé : {self.spent_today:.4f}/{self.daily_budget:.2f} USD "
                f"déjà dépensés, estimation +{estimated_cost:.4f} non couverte."
            )

    @property
    def _lock_path(self) -> Path:
        return self.state_path.with_suffix(self.state_path.suffix + ".lock")

    def record(self, amount: float) -> dict[str, Any]:
        """Ajoute `amount` au cumul du jour avec verrou portable (Sprint VV.2).

        Le lock fichier élimine la race read-modify-write quand plusieurs
        sub-missions de la même meta-mission consomment leur budget en parallèle.
        """
        if amount < 0:
            raise ValueError("amount doit être >= 0")
        with _file_lock(self._lock_path):
            data = self._load()
            data["spent_usd"] = round(float(data.get("spent_usd", 0.0)) + float(amount), 6)
            data["last_recorded_at"] = datetime.now(UTC).isoformat()
            self._save(data)
        return data

    def status(self) -> dict[str, Any]:
        data = self._load()
        return {
            "date": data["date"],
            "spent_usd": round(float(data.get("spent_usd", 0.0)), 4),
            "daily_budget_usd": self.daily_budget,
            "remaining_usd": round(self.remaining_today(), 4),
            "percent_used": self.percent_used(),
            "history_days_kept": len(data.get("history", [])),
        }
