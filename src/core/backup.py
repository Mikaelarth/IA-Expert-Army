"""backup — sauvegarde atomique du projet (Sprint BBB).

Le backup capture les artefacts critiques NON RECONSTRUCTIBLES :
- `skills/`       : skills auto-générées (perte = perte de l'apprentissage)
- `data/memory/`  : épisodes + missions + meta_missions (historique d'exécution)
- `prompts/`      : system prompts des agents (versionnés mais aussi capturés)
- `docs/adr/`     : ADRs (décisions architecturales)
- Config files     : pyproject.toml, justfile, .pre-commit-config.yaml,
                     README.md, CHANGELOG.md (utiles pour reproduire l'env)

EXCLUS (volontaire) :
- `.env`             : secrets (on ne backup PAS les credentials)
- `data/chroma/`     : INDEX, recalculable via `scripts/reindex_episodes.py`
- `data/budget_state.json` : volatile (rotate quotidien)
- `data/autonomous_runs/` : rapports horodatés, garde-fou non-critique
- `.venv/`, `__pycache__/`, `*.pyc`, etc.

L'archive ZIP contient un `manifest.json` à la racine avec :
- timestamp ISO 8601
- git_commit (si dispo)
- files_included list
- total_size_bytes
- iaa_version (lu depuis pyproject.toml)

Atomicité : on écrit dans `<archive>.tmp` puis on fait un `os.replace()` atomique.
Rotation : on garde les N derniers backups (défaut 7), suppression LRU.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

# Patterns à exclure des dossiers backupés (relatif au dossier)
_EXCLUDE_PATTERNS = re.compile(
    r"(__pycache__|\.pyc$|\.pyo$|\.pytest_cache|\.ruff_cache|\.mypy_cache|\.DS_Store)"
)


class BackupManifest(BaseModel):
    """Metadata embarquée dans chaque backup."""

    created_at: str
    git_commit: str
    iaa_version: str
    files_included: list[str]
    total_size_bytes: int
    excluded_paths: list[str]


def _detect_git_commit(project_root: Path) -> str:
    """Lit le short hash git du HEAD courant. 'unknown' si git absent."""
    try:
        result = subprocess.run(  # noqa: S603 — args fixes
            ["git", "-C", str(project_root), "rev-parse", "--short", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=2.0,
            check=True,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return "unknown"


def _detect_iaa_version(project_root: Path) -> str:
    """Lit `[project].version` du pyproject.toml. 'unknown' si parsing échoue."""
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return "unknown"
    try:
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            m = re.match(r'^\s*version\s*=\s*"([^"]+)"\s*$', line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return "unknown"


def _iter_files_to_backup(project_root: Path, sources: list[str]) -> Iterable[tuple[Path, Path]]:
    """Génère (chemin_absolu, chemin_relatif_dans_archive) pour chaque fichier à backup.

    `sources` est une liste de chemins relatifs au project_root. Chaque source
    peut être un fichier ou un dossier ; les dossiers sont parcourus récursivement.
    """
    for source_rel in sources:
        source_abs = project_root / source_rel
        if not source_abs.exists():
            continue
        if source_abs.is_file():
            yield (source_abs, source_abs.relative_to(project_root))
            continue
        # Dossier — parcours récursif
        for path in source_abs.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(project_root)
            if _EXCLUDE_PATTERNS.search(str(rel)):
                continue
            yield (path, rel)


# Sources backupées par défaut (relatif au project_root). Ordre = priorité de
# restauration (les premiers en cas de partial restore).
DEFAULT_SOURCES = [
    "skills",
    "data/memory",
    "prompts",
    "docs",
    "pyproject.toml",
    "justfile",
    ".pre-commit-config.yaml",
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "uv.lock",
]


def create_backup(
    project_root: Path,
    output_dir: Path,
    sources: list[str] | None = None,
) -> Path:
    """Produit une archive ZIP atomique des sources critiques.

    Retourne le chemin du ZIP final.
    """
    project_root = Path(project_root).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    sources = sources or DEFAULT_SOURCES
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    final_path = output_dir / f"iaa-backup-{timestamp}.zip"
    tmp_path = output_dir / f"iaa-backup-{timestamp}.zip.tmp"

    files_included: list[str] = []
    total_size = 0

    # Écrit l'archive dans le fichier temporaire (atomicité)
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for abs_path, rel_path in _iter_files_to_backup(project_root, sources):
            zf.write(abs_path, arcname=str(rel_path))
            files_included.append(str(rel_path).replace(os.sep, "/"))
            total_size += abs_path.stat().st_size

        # Manifest en dernier (après avoir compté tout le reste)
        manifest = BackupManifest(
            created_at=datetime.now(UTC).isoformat(),
            git_commit=_detect_git_commit(project_root),
            iaa_version=_detect_iaa_version(project_root),
            files_included=sorted(files_included),
            total_size_bytes=total_size,
            excluded_paths=[
                ".env (secrets)",
                "data/chroma/ (rebuildable via reindex)",
                "data/budget_state.json (volatile)",
                "data/autonomous_runs/",
                ".venv/, __pycache__/, *.pyc",
            ],
        )
        zf.writestr("manifest.json", manifest.model_dump_json(indent=2))

    # Move atomique tmp → final
    os.replace(tmp_path, final_path)
    return final_path


def list_backups(backup_dir: Path) -> list[Path]:
    """Liste les backups dans le dossier, triés par date (plus récent en premier)."""
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []
    backups = sorted(
        backup_dir.glob("iaa-backup-*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return backups


def rotate_backups(backup_dir: Path, keep_last: int = 7) -> list[Path]:
    """Supprime les backups au-delà des `keep_last` plus récents.

    Retourne la liste des chemins supprimés. Politique LRU (Least Recently Used)
    basée sur mtime — les plus anciens partent en premier.
    """
    if keep_last < 1:
        raise ValueError("keep_last doit être >= 1")
    backups = list_backups(backup_dir)
    to_delete = backups[keep_last:]
    for path in to_delete:
        # Pas critique si une suppression échoue — on retentera la prochaine fois
        with contextlib.suppress(OSError):
            path.unlink()
    return to_delete


def read_manifest(backup_path: Path) -> BackupManifest | None:
    """Lit le manifest.json d'un backup. Retourne None si absent/corrompu."""
    try:
        with zipfile.ZipFile(backup_path, "r") as zf, zf.open("manifest.json") as f:
            data = json.loads(f.read().decode("utf-8"))
        return BackupManifest(**data)
    except (KeyError, zipfile.BadZipFile, json.JSONDecodeError, OSError):
        return None


def restore_backup(
    backup_path: Path,
    target_root: Path,
    overwrite: bool = False,
) -> dict[str, int]:
    """Restaure un backup dans `target_root`.

    Par défaut, refuse d'écrire si un fichier existe déjà à destination
    (overwrite=False). Avec overwrite=True, écrase silencieusement.

    Retourne {restored: N, skipped_existing: M, failed: K}.
    """
    backup_path = Path(backup_path).resolve()
    target_root = Path(target_root).resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    if not backup_path.exists():
        raise FileNotFoundError(f"Backup introuvable : {backup_path}")

    restored = 0
    skipped = 0
    failed = 0

    with zipfile.ZipFile(backup_path, "r") as zf:
        for info in zf.infolist():
            if info.filename == "manifest.json":
                continue  # On ne restaure pas le manifest dans le project
            # Sécurité : empêcher les path traversal (..) ou les chemins absolus
            if info.filename.startswith(("/", "..")) or ".." in Path(info.filename).parts:
                failed += 1
                continue
            target_path = target_root / info.filename
            if target_path.exists() and not overwrite:
                skipped += 1
                continue
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                restored += 1
            except OSError:
                failed += 1

    return {"restored": restored, "skipped_existing": skipped, "failed": failed}
