"""Tests pour src.memory.file_memory."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from src.memory.file_memory import FileMemory, MemoryRecord


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def test_memory_record_roundtrip() -> None:
    rec = MemoryRecord(metadata={"k": "v", "n": 3}, body="hello world")
    md = rec.to_markdown()
    parsed = MemoryRecord.from_markdown(md)
    assert parsed.metadata == {"k": "v", "n": 3}
    assert parsed.body == "hello world"


def test_memory_record_handles_no_frontmatter() -> None:
    parsed = MemoryRecord.from_markdown("just some body, no frontmatter")
    assert parsed.metadata == {}
    assert "just some body" in parsed.body


def test_filememory_creates_directories(tmp_path: Path) -> None:
    mem = FileMemory(tmp_path / "memory")
    assert mem.episodes_dir.exists()
    assert mem.missions_dir.exists()
    assert mem.working_dir.exists()


def test_working_set_get_clear(memory: FileMemory) -> None:
    rec = MemoryRecord(metadata={"agent": "test"}, body="state X")
    memory.set_working("current", rec)
    fetched = memory.get_working("current")
    assert fetched is not None
    assert fetched.metadata["agent"] == "test"
    assert fetched.body == "state X"

    cleared = memory.clear_working()
    assert cleared == 1
    assert memory.get_working("current") is None


def test_write_and_list_episodes(memory: FileMemory) -> None:
    mid = uuid4()
    memory.write_episode(mid, "agent_a", MemoryRecord(metadata={"k": 1}, body="b1"))
    memory.write_episode(mid, "agent_b", MemoryRecord(metadata={"k": 2}, body="b2"))
    memory.write_episode(uuid4(), "agent_c", MemoryRecord(metadata={"k": 3}, body="b3"))

    all_episodes = memory.list_episodes()
    assert len(all_episodes) == 3

    mid_episodes = memory.list_episodes(mid)
    assert len(mid_episodes) == 2


def test_mission_summary(memory: FileMemory) -> None:
    mid = uuid4()
    rec = MemoryRecord(metadata={"final_verdict": "APPROVED"}, body="ok")
    path = memory.write_mission_summary(mid, rec)
    assert path.exists()
    fetched = memory.get_mission_summary(mid)
    assert fetched is not None
    assert fetched.metadata["final_verdict"] == "APPROVED"


def test_search_episodes_naive(memory: FileMemory) -> None:
    memory.write_episode(uuid4(), "a1", MemoryRecord(body="fastapi endpoint authentication"))
    memory.write_episode(uuid4(), "a2", MemoryRecord(body="celery worker queue"))
    memory.write_episode(uuid4(), "a3", MemoryRecord(body="fastapi pydantic validation"))

    results = memory.search_episodes("fastapi")
    assert len(results) == 2
