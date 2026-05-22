"""Tests pour src/core/checkpoint.py — CheckpointStore (v0.8.0 F1).

Valide :
- save() écrit un JSON correctement formaté par mission/step
- load_all() retourne les checkpoints triés par step_index
- has_checkpoint / list_missions reflètent l'état disque
- clear() supprime tous les checkpoints d'une mission
- get_resumable_step() retourne l'index du prochain agent à jouer
- Tolérance : corruption JSON ignorée, save sans crash sur disque RO
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from src.core.checkpoint import CheckpointStore


class _FakeAgentOutput(BaseModel):
    """AgentOutput minimal pour tester la sérialisation sans cycle d'import."""

    success: bool
    raw_text: str
    parsed: dict | None = None
    cost_usd: float = 0.0
    duration_seconds: float = 0.0


def test_save_creates_json_in_mission_dir(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints")
    mission_id = str(uuid4())
    output = _FakeAgentOutput(success=True, raw_text="hello", cost_usd=0.0)

    path = store.save(
        mission_id, step_index=0, agent_name="chief_orchestrator", agent_output=output
    )
    assert path is not None
    assert path.exists()
    assert path.name == "00_chief_orchestrator.json"
    assert path.parent.name == mission_id

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["mission_id"] == mission_id
    assert payload["step_index"] == 0
    assert payload["agent_name"] == "chief_orchestrator"
    assert payload["agent_output"]["success"] is True
    assert payload["agent_output"]["raw_text"] == "hello"
    assert "saved_at" in payload


def test_load_all_returns_sorted_by_step_index(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints")
    mission_id = str(uuid4())

    # Sauve dans le désordre
    store.save(mission_id, 2, "code_reviewer", _FakeAgentOutput(success=True, raw_text="review"))
    store.save(mission_id, 0, "chief_orchestrator", _FakeAgentOutput(success=True, raw_text="orch"))
    store.save(mission_id, 1, "software_architect", _FakeAgentOutput(success=True, raw_text="arch"))

    checkpoints = store.load_all(mission_id)
    assert len(checkpoints) == 3
    assert [c["step_index"] for c in checkpoints] == [0, 1, 2]
    assert [c["agent_name"] for c in checkpoints] == [
        "chief_orchestrator",
        "software_architect",
        "code_reviewer",
    ]


def test_load_all_returns_empty_for_unknown_mission(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints")
    assert store.load_all("nonexistent-mission-id") == []


def test_has_checkpoint_reflects_disk_state(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints")
    mission_id = str(uuid4())

    assert store.has_checkpoint(mission_id) is False
    store.save(mission_id, 0, "agent_a", _FakeAgentOutput(success=True, raw_text="x"))
    assert store.has_checkpoint(mission_id) is True


def test_list_missions_returns_ids_with_checkpoints(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints")
    m1 = str(uuid4())
    m2 = str(uuid4())
    store.save(m1, 0, "agent_a", _FakeAgentOutput(success=True, raw_text="x"))
    store.save(m2, 0, "agent_b", _FakeAgentOutput(success=True, raw_text="y"))

    missions = store.list_missions()
    assert set(missions) == {m1, m2}


def test_list_missions_empty_root_returns_empty_list(tmp_path: Path) -> None:
    # Root n'existe même pas
    store = CheckpointStore(tmp_path / "absent")
    assert store.list_missions() == []


def test_clear_removes_all_checkpoints_of_a_mission(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints")
    mission_id = str(uuid4())
    for i, name in enumerate(["a", "b", "c"]):
        store.save(mission_id, i, name, _FakeAgentOutput(success=True, raw_text="x"))

    deleted = store.clear(mission_id)
    assert deleted == 3
    assert store.has_checkpoint(mission_id) is False
    assert store.load_all(mission_id) == []


def test_clear_idempotent_on_missing_mission(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints")
    # Mission jamais checkpointée — clear ne doit pas lever
    assert store.clear("nonexistent") == 0


def test_get_resumable_step_returns_next_index(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints")
    mission_id = str(uuid4())

    # Pas de checkpoint = on commence à 0
    assert store.get_resumable_step(mission_id) == 0

    store.save(mission_id, 0, "a", _FakeAgentOutput(success=True, raw_text="x"))
    assert store.get_resumable_step(mission_id) == 1

    store.save(mission_id, 1, "b", _FakeAgentOutput(success=True, raw_text="x"))
    store.save(mission_id, 2, "c", _FakeAgentOutput(success=True, raw_text="x"))
    assert store.get_resumable_step(mission_id) == 3


def test_load_all_tolerates_corrupted_json(tmp_path: Path) -> None:
    """Un JSON corrompu ne doit pas faire échouer load_all — il est skippé."""
    store = CheckpointStore(tmp_path / "checkpoints")
    mission_id = str(uuid4())
    store.save(mission_id, 0, "valid", _FakeAgentOutput(success=True, raw_text="ok"))

    # Crée un fichier corrompu manuellement
    bad_path = tmp_path / "checkpoints" / mission_id / "99_corrupted.json"
    bad_path.write_text("{ this is not valid json", encoding="utf-8")

    checkpoints = store.load_all(mission_id)
    assert len(checkpoints) == 1  # Le corrompu est skippé, le valide reste
    assert checkpoints[0]["agent_name"] == "valid"


def test_save_handles_non_pydantic_output(tmp_path: Path) -> None:
    """save() doit aussi marcher avec un objet dict-like (non Pydantic)."""
    store = CheckpointStore(tmp_path / "checkpoints")
    mission_id = str(uuid4())

    class _DictLike:
        def __init__(self) -> None:
            self.success = True
            self.raw_text = "from dict"
            self._private = "should not be serialized"

    path = store.save(mission_id, 0, "dict_agent", _DictLike())
    assert path is not None
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["agent_output"]["raw_text"] == "from dict"
    assert "_private" not in payload["agent_output"]


def test_save_overwrites_existing_checkpoint(tmp_path: Path) -> None:
    """Si on save deux fois sur le même (mission, step), le 2e remplace le 1er
    (utile pour mettre à jour un checkpoint après retry/repair).
    """
    store = CheckpointStore(tmp_path / "checkpoints")
    mission_id = str(uuid4())

    store.save(mission_id, 0, "agent", _FakeAgentOutput(success=True, raw_text="v1"))
    store.save(mission_id, 0, "agent", _FakeAgentOutput(success=True, raw_text="v2"))

    checkpoints = store.load_all(mission_id)
    assert len(checkpoints) == 1
    assert checkpoints[0]["agent_output"]["raw_text"] == "v2"
