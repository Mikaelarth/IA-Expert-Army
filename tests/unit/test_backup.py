"""Tests pour src.core.backup — Sprint BBB.

Couvre :
- create_backup : produit un ZIP valide avec manifest, atomicité (.tmp puis move)
- list_backups : tri par date décroissante
- rotate_backups : LRU avec keep_last
- read_manifest : extraction du metadata + tolérance corruption
- restore_backup : refuse overwrite par défaut, succès avec overwrite=True,
  sécurité path traversal
- exclusion patterns : __pycache__/ et autres caches ignorés
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from src.core.backup import (
    BackupManifest,
    create_backup,
    list_backups,
    read_manifest,
    restore_backup,
    rotate_backups,
)


# ===== Fixtures : un mini-projet en tmp_path =====


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Crée une arbo de projet minimaliste à backup."""
    root = tmp_path / "project"
    (root / "skills" / "agent_x").mkdir(parents=True)
    (root / "skills" / "agent_x" / "skill1.md").write_text("# Skill 1", encoding="utf-8")
    (root / "data" / "memory" / "missions").mkdir(parents=True)
    (root / "data" / "memory" / "missions" / "abc.md").write_text(
        "---\nmission_id: abc\n---\n\nbody", encoding="utf-8"
    )
    (root / "prompts").mkdir()
    (root / "prompts" / "p.md").write_text("prompt", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "0.9.0"\n', encoding="utf-8"
    )
    # Dossier à exclure
    (root / "skills" / "agent_x" / "__pycache__").mkdir()
    (root / "skills" / "agent_x" / "__pycache__" / "x.pyc").write_text("trash")
    return root


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    return tmp_path / "backups"


# ===== create_backup =====


def test_create_backup_produces_valid_zip(project_root: Path, backup_dir: Path) -> None:
    archive = create_backup(project_root, backup_dir)
    assert archive.exists()
    assert archive.suffix == ".zip"
    # Le .tmp n'existe plus (move atomique a réussi)
    tmp_files = list(backup_dir.glob("*.tmp"))
    assert tmp_files == []
    # Le ZIP est ouvrable et contient au moins le manifest
    with zipfile.ZipFile(archive, "r") as zf:
        names = zf.namelist()
        assert "manifest.json" in names


def test_create_backup_includes_expected_files(project_root: Path, backup_dir: Path) -> None:
    archive = create_backup(project_root, backup_dir)
    with zipfile.ZipFile(archive, "r") as zf:
        names = set(zf.namelist())
    assert "skills/agent_x/skill1.md" in names
    assert "data/memory/missions/abc.md" in names
    assert "prompts/p.md" in names
    assert "pyproject.toml" in names


def test_create_backup_excludes_pycache(project_root: Path, backup_dir: Path) -> None:
    """Les caches Python doivent être exclus pour ne pas alourdir l'archive."""
    archive = create_backup(project_root, backup_dir)
    with zipfile.ZipFile(archive, "r") as zf:
        names = zf.namelist()
    for n in names:
        assert "__pycache__" not in n, f"Cache leaked into backup: {n}"
        assert not n.endswith(".pyc"), f"PYC file in backup: {n}"


def test_create_backup_manifest_has_correct_metadata(
    project_root: Path, backup_dir: Path
) -> None:
    archive = create_backup(project_root, backup_dir)
    with zipfile.ZipFile(archive, "r") as zf:
        manifest_raw = zf.read("manifest.json").decode("utf-8")
    manifest = json.loads(manifest_raw)
    assert manifest["iaa_version"] == "0.9.0"
    assert manifest["total_size_bytes"] > 0
    assert len(manifest["files_included"]) >= 3  # skill, mission, prompt
    # Le manifest référence les exclusions
    assert any("env" in s.lower() for s in manifest["excluded_paths"])


def test_create_backup_handles_missing_source(project_root: Path, backup_dir: Path) -> None:
    """Si une source n'existe pas, on ignore silencieusement (pas de crash)."""
    archive = create_backup(project_root, backup_dir, sources=["does_not_exist", "skills"])
    with zipfile.ZipFile(archive, "r") as zf:
        names = zf.namelist()
    # Skills présent, le manquant est silencieusement ignoré
    assert any("skills/" in n for n in names)


# ===== list_backups =====


def test_list_backups_empty_when_no_backups(backup_dir: Path) -> None:
    assert list_backups(backup_dir) == []


def test_list_backups_sorted_by_date_desc(project_root: Path, backup_dir: Path) -> None:
    import time

    b1 = create_backup(project_root, backup_dir)
    time.sleep(1.1)  # garantir mtime différent
    b2 = create_backup(project_root, backup_dir)
    listed = list_backups(backup_dir)
    assert len(listed) == 2
    # Le plus récent en premier
    assert listed[0].name == b2.name
    assert listed[1].name == b1.name


# ===== rotate_backups =====


def test_rotate_keeps_only_last_n(project_root: Path, backup_dir: Path) -> None:
    import time

    # Crée 4 backups
    for _ in range(4):
        create_backup(project_root, backup_dir)
        time.sleep(1.05)
    deleted = rotate_backups(backup_dir, keep_last=2)
    remaining = list_backups(backup_dir)
    assert len(remaining) == 2
    assert len(deleted) == 2


def test_rotate_no_op_when_fewer_than_keep_last(
    project_root: Path, backup_dir: Path
) -> None:
    create_backup(project_root, backup_dir)
    deleted = rotate_backups(backup_dir, keep_last=10)
    assert deleted == []
    assert len(list_backups(backup_dir)) == 1


def test_rotate_rejects_keep_last_zero(backup_dir: Path) -> None:
    with pytest.raises(ValueError, match=">= 1"):
        rotate_backups(backup_dir, keep_last=0)


# ===== read_manifest =====


def test_read_manifest_returns_typed_model(project_root: Path, backup_dir: Path) -> None:
    archive = create_backup(project_root, backup_dir)
    m = read_manifest(archive)
    assert isinstance(m, BackupManifest)
    assert m.iaa_version == "0.9.0"
    assert m.total_size_bytes > 0


def test_read_manifest_returns_none_on_corrupt(backup_dir: Path, tmp_path: Path) -> None:
    """Un ZIP corrompu ou sans manifest → None (pas de crash)."""
    fake = tmp_path / "fake.zip"
    fake.write_text("not a zip at all")
    assert read_manifest(fake) is None


def test_read_manifest_returns_none_when_manifest_missing(
    backup_dir: Path, tmp_path: Path
) -> None:
    empty_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty_zip, "w") as zf:
        zf.writestr("not-manifest.txt", "hello")
    assert read_manifest(empty_zip) is None


# ===== restore_backup =====


def test_restore_backup_refuses_overwrite_by_default(
    project_root: Path, backup_dir: Path, tmp_path: Path
) -> None:
    """Par défaut, restore ne touche pas aux fichiers existants."""
    archive = create_backup(project_root, backup_dir)
    target = tmp_path / "restored"
    target.mkdir()
    # Fichier déjà présent à destination
    (target / "skills" / "agent_x").mkdir(parents=True)
    (target / "skills" / "agent_x" / "skill1.md").write_text(
        "EXISTING DO NOT OVERWRITE", encoding="utf-8"
    )

    stats = restore_backup(archive, target, overwrite=False)

    assert stats["skipped_existing"] >= 1
    # Le fichier existant a été préservé
    assert (
        target / "skills" / "agent_x" / "skill1.md"
    ).read_text(encoding="utf-8") == "EXISTING DO NOT OVERWRITE"


def test_restore_backup_overwrites_when_flag_set(
    project_root: Path, backup_dir: Path, tmp_path: Path
) -> None:
    archive = create_backup(project_root, backup_dir)
    target = tmp_path / "restored"
    target.mkdir()
    (target / "skills" / "agent_x").mkdir(parents=True)
    (target / "skills" / "agent_x" / "skill1.md").write_text("old", encoding="utf-8")

    stats = restore_backup(archive, target, overwrite=True)

    assert stats["restored"] >= 1
    # Le contenu du backup a remplacé l'ancien
    content = (target / "skills" / "agent_x" / "skill1.md").read_text(encoding="utf-8")
    assert content == "# Skill 1"


def test_restore_creates_target_dirs(
    project_root: Path, backup_dir: Path, tmp_path: Path
) -> None:
    archive = create_backup(project_root, backup_dir)
    target = tmp_path / "fresh_restore"  # n'existe pas encore
    stats = restore_backup(archive, target)
    assert stats["restored"] >= 3
    assert (target / "skills" / "agent_x" / "skill1.md").exists()


def test_restore_rejects_path_traversal(tmp_path: Path) -> None:
    """Sécurité : un fichier dans le ZIP avec '..' ne doit pas échapper du target."""
    malicious_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(malicious_zip, "w") as zf:
        zf.writestr("../../etc/evil.txt", "pwned")
        zf.writestr("ok/file.txt", "safe")
    target = tmp_path / "target"
    stats = restore_backup(malicious_zip, target)
    # Le fichier malicieux compte comme failed, mais le ZIP n'est pas crash
    assert stats["failed"] >= 1
    assert (target / "ok" / "file.txt").exists()
    # Le fichier ../../ n'a PAS été écrit hors du target
    assert not (tmp_path.parent / "etc" / "evil.txt").exists()


def test_restore_raises_if_backup_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        restore_backup(tmp_path / "ghost.zip", tmp_path / "target")
