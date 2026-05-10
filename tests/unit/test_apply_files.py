"""Tests pour src.tools.apply_files."""
from __future__ import annotations

from pathlib import Path

from src.tools.apply_files import (
    DEFAULT_ALLOWED_DIRS,
    ApplyAction,
    apply_files,
)


def _file(path: str, content: str = "x = 1\n") -> dict[str, str]:
    return {"path": path, "content": content, "language": "python"}


def test_writes_simple_file_in_allowed_dir(tmp_path: Path) -> None:
    results = apply_files([_file("src/foo.py")], tmp_path)
    assert len(results) == 1
    assert results[0].action == ApplyAction.WRITTEN
    assert results[0].bytes_written > 0
    assert (tmp_path / "src" / "foo.py").read_text(encoding="utf-8") == "x = 1\n"


def test_creates_intermediate_dirs(tmp_path: Path) -> None:
    results = apply_files([_file("src/api/v1/health.py", "OK")], tmp_path)
    assert results[0].action == ApplyAction.WRITTEN
    assert (tmp_path / "src" / "api" / "v1" / "health.py").exists()


def test_rejects_absolute_path(tmp_path: Path) -> None:
    """Sur Windows /etc/passwd n'est pas absolu (pas de drive letter), mais la résolution sort de project_root."""
    results = apply_files([_file("/etc/passwd", "evil")], tmp_path)
    assert results[0].action in {ApplyAction.REJECTED_PATH, ApplyAction.REJECTED_OUTSIDE, ApplyAction.REJECTED_DIR}
    # L'essentiel : le fichier n'a PAS été écrit
    assert not (tmp_path / "etc" / "passwd").exists()


def test_rejects_path_traversal(tmp_path: Path) -> None:
    results = apply_files([_file("src/../../../escape.py")], tmp_path)
    # Le ".." est attrapé par la regex traversal OU la résolution hors root
    assert results[0].action in {ApplyAction.REJECTED_PATH, ApplyAction.REJECTED_OUTSIDE}


def test_rejects_non_whitelisted_dir(tmp_path: Path) -> None:
    results = apply_files([_file("evil/foo.py")], tmp_path)
    assert results[0].action == ApplyAction.REJECTED_DIR


def test_rejects_root_files(tmp_path: Path) -> None:
    results = apply_files([_file("pyproject.toml")], tmp_path)
    assert results[0].action == ApplyAction.REJECTED_DIR


def test_rejects_suspicious_filename(tmp_path: Path) -> None:
    results = apply_files([_file("src/pyproject.toml (section à fusionner)")], tmp_path)
    assert results[0].action == ApplyAction.REJECTED_NAME


def test_skips_existing_without_force(tmp_path: Path) -> None:
    target = tmp_path / "src" / "foo.py"
    target.parent.mkdir(parents=True)
    target.write_text("OLD", encoding="utf-8")

    results = apply_files([_file("src/foo.py", "NEW")], tmp_path)
    assert results[0].action == ApplyAction.SKIPPED_EXISTS
    assert target.read_text(encoding="utf-8") == "OLD"


def test_overwrites_with_force(tmp_path: Path) -> None:
    target = tmp_path / "src" / "foo.py"
    target.parent.mkdir(parents=True)
    target.write_text("OLD", encoding="utf-8")

    results = apply_files([_file("src/foo.py", "NEW\n")], tmp_path, force=True)
    assert results[0].action == ApplyAction.WRITTEN
    assert target.read_text(encoding="utf-8") == "NEW\n"


def test_empty_content_writes_empty_file(tmp_path: Path) -> None:
    results = apply_files([_file("src/__init__.py", "")], tmp_path)
    assert results[0].action == ApplyAction.WRITTEN
    assert (tmp_path / "src" / "__init__.py").read_text(encoding="utf-8") == ""


def test_each_file_independent(tmp_path: Path) -> None:
    """Un fichier rejeté ne doit pas bloquer les autres."""
    files = [
        _file("/abs/evil.py"),  # rejeté
        _file("src/ok.py"),  # OK
        _file("not_allowed/foo.py"),  # rejeté
        _file("tests/test_ok.py"),  # OK
    ]
    results = apply_files(files, tmp_path)
    assert len(results) == 4
    written = [r for r in results if r.action == ApplyAction.WRITTEN]
    assert len(written) == 2
    assert (tmp_path / "src" / "ok.py").exists()
    assert (tmp_path / "tests" / "test_ok.py").exists()


def test_default_allowed_dirs_include_main_areas() -> None:
    assert "src" in DEFAULT_ALLOWED_DIRS
    assert "tests" in DEFAULT_ALLOWED_DIRS
    assert "docs" in DEFAULT_ALLOWED_DIRS
