"""checkpoint — sauvegarde incrémentale des sorties d'agents pour resume après crash.

Audit zéro-dette v0.7.0 → v0.8.0 : adresse le pain point « si Ollama crashe ou la
machine reboot au milieu d'une mission, je perds 30 min ».

Modèle : un fichier JSON par agent terminé, organisé par mission_id :

    data/checkpoints/<mission_id>/<step_index>_<agent_name>.json

Format JSON minimal (volontairement pas Pydantic — on doit pouvoir relire un
checkpoint corrompu et récupérer ce qui est lisible) :

    {
        "mission_id": "...",
        "step_index": 0,
        "agent_name": "chief_orchestrator",
        "saved_at": "2026-05-22T14:32:11+00:00",
        "agent_output": {
            "success": true,
            "raw_text": "...",
            "parsed": {...},
            "cost_usd": 0.0,
            ...
        }
    }

Politique :
- save() est appelé après chaque agent réussi (success=True). Pas de save
  sur échec — un échec doit toujours faire échouer la mission.
- load_all() retourne tous les checkpoints d'une mission_id, triés par step.
- clear() est appelé en fin de mission (succès final) pour ne pas accumuler.
- Si le répertoire `data/checkpoints/` est plein/inaccessible, save() émet
  un warning mais ne lève pas — on ne fait pas échouer une mission pour un
  problème de checkpoint.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_log = logging.getLogger("ia_expert.checkpoint")


class CheckpointStore:
    """Gestionnaire fichier des checkpoints d'une mission.

    Une instance gère TOUS les checkpoints du projet ; le `mission_id` est
    passé à chaque méthode pour isoler les missions entre elles.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _mission_dir(self, mission_id: str) -> Path:
        return self.root / str(mission_id)

    def save(
        self,
        mission_id: str,
        step_index: int,
        agent_name: str,
        agent_output: Any,  # AgentOutput — duck-typed pour éviter cycle import
    ) -> Path | None:
        """Persiste un checkpoint après l'exécution réussie d'un agent.

        Retourne le chemin écrit, ou None si échec d'écriture (best-effort).
        """
        try:
            mission_dir = self._mission_dir(mission_id)
            mission_dir.mkdir(parents=True, exist_ok=True)
            path = mission_dir / f"{step_index:02d}_{agent_name}.json"
            payload = {
                "mission_id": str(mission_id),
                "step_index": step_index,
                "agent_name": agent_name,
                "saved_at": datetime.now(UTC).isoformat(),
                "agent_output": self._serialize_agent_output(agent_output),
            }
            path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            return path
        except (OSError, TypeError) as exc:
            _log.warning(
                "checkpoint.save.failed mission=%s step=%d agent=%s error=%s",
                mission_id,
                step_index,
                agent_name,
                exc,
            )
            return None

    @staticmethod
    def _serialize_agent_output(agent_output: Any) -> dict[str, Any]:
        """Sérialise un AgentOutput Pydantic en dict JSON-safe.

        Tolérant : si l'objet n'est pas Pydantic, on tente model_dump puis
        un fallback __dict__.
        """
        if hasattr(agent_output, "model_dump"):
            return agent_output.model_dump(mode="json")
        if hasattr(agent_output, "__dict__"):
            return {k: v for k, v in agent_output.__dict__.items() if not k.startswith("_")}
        return {"raw": str(agent_output)}

    def load_all(self, mission_id: str) -> list[dict[str, Any]]:
        """Retourne tous les checkpoints d'une mission, triés par step_index.

        Tolérant aux fichiers corrompus : un JSON illisible est ignoré (warning),
        les autres sont retournés. Permet de récupérer un état partiel.
        """
        mission_dir = self._mission_dir(mission_id)
        if not mission_dir.exists():
            return []
        checkpoints: list[dict[str, Any]] = []
        for path in sorted(mission_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                _log.warning("checkpoint.load.skip path=%s error=%s", path, exc)
                continue
            checkpoints.append(payload)
        checkpoints.sort(key=lambda c: c.get("step_index", 0))
        return checkpoints

    def list_missions(self) -> list[str]:
        """Liste les mission_ids ayant au moins un checkpoint sur disque.

        Utile pour la commande `--resume` ou la GUI : montre les missions
        interrompues qu'on peut reprendre.
        """
        if not self.root.exists():
            return []
        return sorted(d.name for d in self.root.iterdir() if d.is_dir() and any(d.glob("*.json")))

    def has_checkpoint(self, mission_id: str) -> bool:
        """True si au moins 1 checkpoint existe pour cette mission."""
        return len(self.load_all(mission_id)) > 0

    def clear(self, mission_id: str) -> int:
        """Supprime tous les checkpoints d'une mission (en fin de mission réussie).

        Retourne le nombre de fichiers supprimés. Best-effort : un fichier
        non-supprimable n'interrompt pas le cleanup.
        """
        mission_dir = self._mission_dir(mission_id)
        if not mission_dir.exists():
            return 0
        deleted = 0
        for path in mission_dir.glob("*.json"):
            try:
                path.unlink()
                deleted += 1
            except OSError as exc:
                _log.warning("checkpoint.clear.skip path=%s error=%s", path, exc)
        # Répertoire pas vide (autre fichier) ou problème d'accès — non-bloquant
        import contextlib

        with contextlib.suppress(OSError):
            mission_dir.rmdir()
        return deleted

    def get_resumable_step(self, mission_id: str) -> int:
        """Retourne le step_index du prochain agent à exécuter.

        Si N checkpoints existent (step_index 0..N-1), retourne N (=step suivant).
        Si aucun checkpoint, retourne 0.
        """
        checkpoints = self.load_all(mission_id)
        if not checkpoints:
            return 0
        return max(c.get("step_index", 0) for c in checkpoints) + 1
