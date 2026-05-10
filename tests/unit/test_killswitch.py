"""Tests pour src.core.killswitch."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.killswitch import Killswitch, KillswitchEngaged


@pytest.fixture
def sentinel(tmp_path: Path) -> Path:
    return tmp_path / "data" / ".killswitch"


def test_not_engaged_initially(sentinel: Path) -> None:
    ks = Killswitch(sentinel)
    assert ks.is_engaged() is False
    assert ks.status()["engaged"] is False


def test_engage_creates_sentinel(sentinel: Path) -> None:
    ks = Killswitch(sentinel)
    ks.engage(reason="alerte sécurité")
    assert ks.is_engaged() is True
    assert sentinel.exists()
    content = sentinel.read_text(encoding="utf-8")
    assert "alerte sécurité" in content
    assert "engaged_at:" in content


def test_engage_creates_parent_dir(tmp_path: Path) -> None:
    sentinel = tmp_path / "deep" / "nested" / "dir" / ".killswitch"
    ks = Killswitch(sentinel)
    ks.engage()
    assert sentinel.exists()


def test_release_removes_sentinel(sentinel: Path) -> None:
    ks = Killswitch(sentinel)
    ks.engage()
    assert ks.release() is True
    assert ks.is_engaged() is False
    assert ks.release() is False  # second release no-op


def test_assert_clear_passes_when_not_engaged(sentinel: Path) -> None:
    ks = Killswitch(sentinel)
    # Ne doit rien lever
    ks.assert_clear()


def test_assert_clear_raises_when_engaged(sentinel: Path) -> None:
    ks = Killswitch(sentinel)
    ks.engage()
    with pytest.raises(KillswitchEngaged):
        ks.assert_clear()


def test_status_includes_content_when_engaged(sentinel: Path) -> None:
    ks = Killswitch(sentinel)
    ks.engage(reason="test")
    st = ks.status()
    assert st["engaged"] is True
    assert "test" in st["content"]
