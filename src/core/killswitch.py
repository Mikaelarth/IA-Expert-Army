"""Killswitch — sentinelle d'arrêt d'urgence.

Garde-fou Phase 6 — le plus simple et le plus fiable :
- Si un fichier sentinelle existe, plus aucune mission ne peut démarrer.
- engage() crée le fichier (avec rationale + timestamp), release() le retire.
- À utiliser quand l'équipe se comporte mal (boucle, dérive, alerte sécurité).

Volontairement file-based plutôt que Redis pubsub : zéro dépendance, fonctionne
même quand l'infrastructure est partiellement down (justement le cas où on en a
le plus besoin).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class KillswitchEngaged(RuntimeError):
    """Levée quand on tente une opération alors que le killswitch est engagé."""


class Killswitch:
    def __init__(self, sentinel_path: Path) -> None:
        self.path = Path(sentinel_path)

    def is_engaged(self) -> bool:
        return self.path.exists()

    def engage(self, reason: str = "manual") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = f"engaged_at: {datetime.now(UTC).isoformat()}\nreason: {reason}\n"
        self.path.write_text(content, encoding="utf-8")

    def release(self) -> bool:
        if not self.path.exists():
            return False
        self.path.unlink()
        return True

    def assert_clear(self) -> None:
        if self.is_engaged():
            raise KillswitchEngaged(
                f"Killswitch engagé ({self.path}). Inspecter, puis "
                "`uv run python scripts/killswitch.py release` pour reprendre."
            )

    def status(self) -> dict[str, Any]:
        if not self.is_engaged():
            return {"engaged": False, "path": str(self.path)}
        return {
            "engaged": True,
            "path": str(self.path),
            "content": self.path.read_text(encoding="utf-8"),
        }
