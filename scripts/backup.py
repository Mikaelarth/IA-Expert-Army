"""backup — produit un backup atomique du projet IA-Expert-Army.

Garde-fou Sprint BBB — capture les artefacts critiques NON RECONSTRUCTIBLES
(skills, mémoire, prompts, ADRs, configs) dans une archive ZIP horodatée.

Usage :
    uv run python scripts/backup.py                        # backup + rotation 7
    uv run python scripts/backup.py --keep 14              # garde 14 derniers
    uv run python scripts/backup.py --output /path/to/dir  # destination custom
    uv run python scripts/backup.py --list                 # liste sans créer

Cf. ADR-013 pour la politique complète (sources, exclusions, fréquence).
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import typer
from rich.console import Console
from rich.table import Table

from src.core.backup import (
    create_backup,
    list_backups,
    read_manifest,
    rotate_backups,
)
from src.core.config import get_settings

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()


def _format_size(n_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes = int(n_bytes / 1024)
    return f"{n_bytes:.1f} TB"


@app.command()
def backup(
    output: Path | None = typer.Option(None, "--output", "-o", help="Dossier des backups"),
    keep: int = typer.Option(7, "--keep", "-k", help="Garde les N derniers (rotation LRU)"),
    list_only: bool = typer.Option(
        False, "--list", "-l", help="Liste les backups existants sans créer"
    ),
) -> None:
    settings = get_settings()
    backup_dir = output or settings.project_root / "data" / "backups"

    if list_only:
        backups = list_backups(backup_dir)
        if not backups:
            console.print(f"[yellow]Aucun backup trouvé dans {backup_dir}[/yellow]")
            raise SystemExit(0)
        table = Table(title=f"Backups dans {backup_dir} ({len(backups)})")
        table.add_column("Fichier", style="cyan")
        table.add_column("Taille", justify="right")
        table.add_column("Version", style="dim")
        table.add_column("Git", style="dim")
        table.add_column("Date", style="dim")
        for path in backups:
            manifest = read_manifest(path)
            size = _format_size(path.stat().st_size)
            version = manifest.iaa_version if manifest else "?"
            git = manifest.git_commit if manifest else "?"
            date = manifest.created_at[:19] if manifest else "?"
            table.add_row(path.name, size, version, git, date)
        console.print(table)
        raise SystemExit(0)

    console.print(f"[bold cyan]Création du backup[/bold cyan] dans {backup_dir}...")
    archive = create_backup(settings.project_root, backup_dir)
    manifest = read_manifest(archive)

    size = _format_size(archive.stat().st_size)
    console.print(f"[green]✓ Backup créé :[/green] {archive.name} ({size})")
    if manifest:
        console.print(
            f"[dim]  Version : {manifest.iaa_version} · "
            f"git : {manifest.git_commit} · "
            f"{len(manifest.files_included)} fichiers · "
            f"{_format_size(manifest.total_size_bytes)} non-compressés[/dim]"
        )

    deleted = rotate_backups(backup_dir, keep_last=keep)
    if deleted:
        console.print(
            f"[dim]  Rotation : {len(deleted)} ancien(s) backup(s) supprimé(s) "
            f"(garde les {keep} plus récents)[/dim]"
        )


if __name__ == "__main__":
    app()
