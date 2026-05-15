"""Test round-trip de scripts/migrate_vps.sh (Sprint HHH.1).

migrate_vps.sh est CRITIQUE : une migration ratée = perte de la mémoire vivante
du système (épisodes, skills, vector DB). Ce test exécute le vrai script bash
sur un INSTALL_DIR mock en tmp_path :
  1. Crée un faux état système (data/memory + skills + prompts + .env)
  2. Lance `migrate_vps.sh export <archive>` avec INSTALL_DIR=tmp_path
  3. Lance `migrate_vps.sh verify <archive>` — doit passer
  4. Crée un autre INSTALL_DIR vierge
  5. Lance `migrate_vps.sh import <archive>` avec INSTALL_DIR=dest_path
  6. Diff arborescent : tout doit matcher byte-for-byte

Skip automatique si bash absent (Windows pur sans Git Bash, par ex.).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATE_SCRIPT = REPO_ROOT / "scripts" / "migrate_vps.sh"

# Skip toute la suite si bash absent
bash_path = shutil.which("bash")
pytestmark = pytest.mark.skipif(
    bash_path is None,
    reason="bash absent — test round-trip migrate_vps.sh nécessite Git Bash, WSL ou Linux",
)


def _bash() -> str:
    """Path bash résolu (le pytestmark a déjà filtré le cas None)."""
    p = shutil.which("bash")
    assert p is not None, "bash absent — skipif aurait dû filtrer"
    return p


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_tree(root: Path) -> dict[str, str]:
    """Hashe chaque fichier du tree, indexé par chemin relatif."""
    hashes: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            hashes[rel] = _hash_file(p)
    return hashes


def _populate_install_dir(install_dir: Path) -> None:
    """Crée une fausse arborescence IA-Expert-Army réaliste."""
    install_dir.mkdir(parents=True, exist_ok=True)

    # data/memory/
    (install_dir / "data" / "memory").mkdir(parents=True)
    (install_dir / "data" / "memory" / "missions").mkdir()
    (install_dir / "data" / "memory" / "missions" / "abc123.md").write_text(
        "---\nmission_id: abc123\nfinal_verdict: APPROVED\n---\n\n# Test mission\n",
        encoding="utf-8",
    )
    (install_dir / "data" / "memory" / "episodes").mkdir()
    (install_dir / "data" / "memory" / "episodes" / "ep1.md").write_text(
        "Episode 1 content with accents : éàù\n", encoding="utf-8"
    )

    # data/chroma/ (binaire factice)
    (install_dir / "data" / "chroma").mkdir(parents=True)
    (install_dir / "data" / "chroma" / "chroma.sqlite3").write_bytes(b"\x00\x01\x02SQLITE\x00fake")

    # data/budget.json
    (install_dir / "data" / "budget.json").write_text(
        '{"today": "2026-05-15", "spent_usd": 1.23}\n', encoding="utf-8"
    )

    # data/error_log.json
    (install_dir / "data" / "error_log.json").write_text('{"errors": []}\n', encoding="utf-8")

    # data/approvals/
    (install_dir / "data" / "approvals" / "pending").mkdir(parents=True)
    (install_dir / "data" / "approvals" / "decided").mkdir()

    # skills/
    (install_dir / "skills").mkdir()
    (install_dir / "skills" / "engineering").mkdir()
    (install_dir / "skills" / "engineering" / "skill1.md").write_text(
        "# Skill 1\n\nProcédure validée.\n", encoding="utf-8"
    )

    # prompts/ (au cas où custom)
    (install_dir / "prompts").mkdir()
    (install_dir / "prompts" / "test.md").write_text("Test prompt\n", encoding="utf-8")

    # .env
    (install_dir / ".env").write_text(
        "ANTHROPIC_API_KEY=sk-ant-test-fake\nDAILY_BUDGET_USD=10.0\nVPS_PROFILE=local\n",
        encoding="utf-8",
    )


def _run_migrate(install_dir: Path, args: list[str], expected_rc: int = 0) -> subprocess.CompletedProcess:
    """Lance migrate_vps.sh avec INSTALL_DIR override."""
    env = os.environ.copy()
    env["INSTALL_DIR"] = str(install_dir)
    # Sur Windows Git Bash, MSYSTEM=MINGW64 est posé. On laisse tel quel.
    result = subprocess.run(  # noqa: S603 — args contrôlés par le test (paths tmp_path)
        [_bash(), str(MIGRATE_SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode != expected_rc:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
    assert result.returncode == expected_rc, (
        f"migrate_vps.sh {' '.join(args)} a renvoyé {result.returncode} "
        f"(attendu {expected_rc})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


def test_migrate_vps_export_then_import_round_trip(tmp_path: Path) -> None:
    """Test E2E : export d'une INSTALL_DIR peuplée, puis import dans une autre,
    et toute l'arborescence doit matcher byte-for-byte."""
    src = tmp_path / "src_vps"
    dst = tmp_path / "dst_vps"
    archive = tmp_path / "snapshot.tar.gz"

    # 1. Peuple la source avec un état réaliste
    _populate_install_dir(src)
    src_hashes = _hash_tree(src)
    assert len(src_hashes) >= 7, f"Setup raté : seulement {len(src_hashes)} fichiers"

    # 2. Export depuis src
    result = _run_migrate(src, ["export", str(archive)])
    assert archive.exists(), "L'archive n'a pas été créée"
    assert archive.stat().st_size > 100, "Archive suspectement petite"
    assert "Export complet" in result.stdout or "Export complet" in result.stderr

    # 3. Verify l'archive
    _run_migrate(src, ["verify", str(archive)])

    # 4. Prépare le destination VPS vide (mais arborescence parent existe)
    dst.mkdir()

    # 5. Import vers dst
    result = _run_migrate(dst, ["import", str(archive)])
    assert "Import complet" in result.stdout or "Import complet" in result.stderr

    # 6. Diff byte-for-byte (sauf .pre-migrate-backup-* créés à l'import)
    dst_hashes = {
        rel: h
        for rel, h in _hash_tree(dst).items()
        if not rel.startswith("data/.pre-migrate-backup-")
    }

    # Tous les fichiers source doivent être présents en destination
    missing = set(src_hashes.keys()) - set(dst_hashes.keys())
    assert not missing, f"Fichiers manquants après import : {missing}"

    # Tous les hashes doivent matcher
    diffs = {
        rel: (src_hashes[rel], dst_hashes[rel])
        for rel in src_hashes
        if src_hashes[rel] != dst_hashes[rel]
    }
    assert not diffs, f"Contenus altérés : {diffs}"

    # Optionnel : vérifier qu'aucun fichier "fantôme" non présent en source
    # (ce serait un bug du script qui crée des artefacts qu'on n'avait pas)
    extra = set(dst_hashes.keys()) - set(src_hashes.keys())
    # Ignorer les manifests éventuels et fichiers techniques
    extra_filtered = {
        e for e in extra
        if not e.startswith("data/.pre-migrate-backup-")
        and not e.endswith("manifest.json")
        and not e.endswith("checksums.sha256")
    }
    assert not extra_filtered, f"Fichiers parasites créés à l'import : {extra_filtered}"


def test_migrate_vps_verify_rejects_corrupted_archive(tmp_path: Path) -> None:
    """Si l'archive est altérée après export, verify doit refuser."""
    src = tmp_path / "src_vps"
    archive = tmp_path / "snapshot.tar.gz"

    _populate_install_dir(src)
    _run_migrate(src, ["export", str(archive)])

    # Corrompt l'archive en y injectant des bytes au milieu (préserve structure
    # tar.gz mais altère les checksums sha256)
    original = archive.read_bytes()
    # Modifie un byte arbitraire dans la partie compressée. Tar.gz tolère
    # certaines altérations sans erreur d'extraction → la détection passe par
    # le manifest checksums.
    corrupted_bytes = bytearray(original)
    # Injecte un byte arbitraire vers la fin (sans casser le footer gzip)
    mid = len(corrupted_bytes) // 2
    corrupted_bytes[mid] = (corrupted_bytes[mid] + 1) % 256
    archive.write_bytes(bytes(corrupted_bytes))

    # Verify doit échouer non-zero
    env = os.environ.copy()
    env["INSTALL_DIR"] = str(src)
    result = subprocess.run(  # noqa: S603 — args contrôlés par le test (paths tmp_path)
        [_bash(), str(MIGRATE_SCRIPT), "verify", str(archive)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    # Soit checksums divergent (rc=3), soit extract échoue (rc!=0)
    assert result.returncode != 0, (
        f"verify a accepté une archive corrompue ! stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_migrate_vps_import_creates_pre_migration_backup(tmp_path: Path) -> None:
    """L'import doit créer un backup pré-migration de l'état destination
    avant overwrite, dans data/.pre-migrate-backup-YYYYMMDD-HHMMSS/.
    Garantit le rollback en cas d'import problématique."""
    src = tmp_path / "src_vps"
    dst = tmp_path / "dst_vps"
    archive = tmp_path / "snapshot.tar.gz"

    _populate_install_dir(src)
    _run_migrate(src, ["export", str(archive)])

    # Peuple le destination avec un état différent (qu'on devrait sauvegarder)
    _populate_install_dir(dst)
    # Modifie un fichier dans dst pour qu'on puisse vérifier qu'il est sauvegardé
    sentinel = dst / "data" / "memory" / "missions" / "DST-SENTINEL.md"
    sentinel.write_text("# Sentinel destination — doit aller en pre-migrate-backup\n", encoding="utf-8")

    _run_migrate(dst, ["import", str(archive)])

    # Vérifie qu'un backup a été créé
    backup_dirs = list((dst / "data").glob(".pre-migrate-backup-*"))
    assert len(backup_dirs) == 1, f"Attendu 1 backup pré-migration, trouvé {len(backup_dirs)}"

    backup_dir = backup_dirs[0]
    # Le sentinel doit être dans le backup
    sentinel_in_backup = backup_dir / "data" / "memory" / "missions" / "DST-SENTINEL.md"
    assert sentinel_in_backup.exists(), (
        f"Sentinel pas retrouvé dans le backup pré-migration : {sentinel_in_backup}"
    )
    # Mais ne doit plus être dans dst principal (overwrite a remplacé data/memory)
    assert not sentinel.exists(), "Sentinel encore présent — overwrite n'a pas eu lieu"


def test_migrate_vps_list_content_lists_archive(tmp_path: Path) -> None:
    """L'action list-content doit afficher les entrées de l'archive sans
    la décompresser dans INSTALL_DIR."""
    src = tmp_path / "src_vps"
    archive = tmp_path / "snapshot.tar.gz"
    _populate_install_dir(src)
    _run_migrate(src, ["export", str(archive)])

    result = _run_migrate(src, ["list-content", str(archive)])
    # Doit mentionner au moins le manifest et quelques fichiers connus
    assert "manifest.json" in result.stdout
    assert "checksums.sha256" in result.stdout


def test_migrate_vps_help_runs_without_args() -> None:
    """`migrate_vps.sh help` doit afficher l'usage et exit 0."""
    result = subprocess.run(  # noqa: S603 — args contrôlés par le test (paths tmp_path)
        [_bash(), str(MIGRATE_SCRIPT), "help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    assert result.returncode == 0
    assert "Usage" in result.stdout
    assert "export" in result.stdout
    assert "import" in result.stdout


def test_migrate_vps_unknown_action_errors() -> None:
    """Action inconnue → exit non-zero + message err."""
    result = subprocess.run(  # noqa: S603 — args contrôlés par le test (paths tmp_path)
        [_bash(), str(MIGRATE_SCRIPT), "frobnicate"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    assert result.returncode != 0
    assert "inconnue" in result.stdout.lower() or "inconnue" in result.stderr.lower()
