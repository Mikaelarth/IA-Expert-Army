"""restore — restaure un backup atomique du projet IA-Expert-Army.

DANGER : par défaut, restore refuse d'écraser les fichiers existants. Utiliser
--overwrite uniquement après avoir confirmé qu'on veut écraser l'état courant
(typiquement après une corruption Chroma ou une perte de skills/).

Usage :
    uv run python scripts/restore.py --backup data/backups/iaa-backup-20260514T120000.zip
    uv run python scripts/restore.py --latest                       # dernier backup
    uv run python scripts/restore.py --backup ... --target /tmp/recover  # restore ailleurs
    uv run python scripts/restore.py --backup ... --overwrite       # écrase les conflits

Procédure d'urgence (cf. docs/runbook.md) :
    1. Stop le projet : killswitch engage
    2. Sauvegarder l'état actuel : just backup
    3. Restore : restore --latest --overwrite
    4. Reindex Chroma : uv run python scripts/reindex_episodes.py
    5. Vérifier : just health
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
from rich.panel import Panel
from rich.table import Table

from src.core.backup import list_backups, read_manifest, restore_backup
from src.core.config import get_settings

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()


@app.command()
def restore(
    backup: Path | None = typer.Option(None, "--backup", "-b", help="Chemin du backup ZIP"),
    latest: bool = typer.Option(False, "--latest", help="Utilise le backup le plus récent"),
    target: Path | None = typer.Option(
        None, "--target", "-t", help="Dossier de restauration (défaut : project_root)"
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Écrase les fichiers existants (DANGER)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip la confirmation interactive"),
) -> None:
    settings = get_settings()
    target_dir = target or settings.project_root
    backup_dir = settings.project_root / "data" / "backups"

    if latest:
        backups = list_backups(backup_dir)
        if not backups:
            console.print(f"[red]Aucun backup trouvé dans {backup_dir}[/red]")
            raise SystemExit(1)
        backup_path = backups[0]
    elif backup:
        backup_path = backup
    else:
        console.print("[red]Précise --backup <path> ou --latest pour le plus récent.[/red]")
        raise SystemExit(2)

    if not backup_path.exists():
        console.print(f"[red]Backup introuvable : {backup_path}[/red]")
        raise SystemExit(1)

    manifest = read_manifest(backup_path)

    table = Table(title="Restore plan", show_header=False)
    table.add_column("Champ", style="cyan")
    table.add_column("Valeur", style="white")
    table.add_row("Backup source", str(backup_path))
    table.add_row("Target dir", str(target_dir))
    table.add_row("Overwrite", "[red]OUI[/red]" if overwrite else "[green]non[/green]")
    if manifest:
        table.add_row("Backup version", manifest.iaa_version)
        table.add_row("Backup git", manifest.git_commit)
        table.add_row("Backup date", manifest.created_at[:19])
        table.add_row("Files in backup", str(len(manifest.files_included)))
    console.print(table)

    if not yes:
        if overwrite:
            console.print(
                Panel(
                    "Mode OVERWRITE actif : les fichiers existants à destination "
                    "seront ÉCRASÉS sans pitié. Confirme avant de continuer.",
                    border_style="red",
                )
            )
        confirm = typer.confirm("Continuer ?", default=False)
        if not confirm:
            console.print("[yellow]Restore annulé.[/yellow]")
            raise SystemExit(0)

    console.print("[bold cyan]Restoration en cours...[/bold cyan]")
    stats = restore_backup(backup_path, target_dir, overwrite=overwrite)

    console.print(
        f"\n[green]✓ Restoration terminée :[/green]\n"
        f"  • Restaurés : {stats['restored']}\n"
        f"  • Ignorés (existaient déjà) : {stats['skipped_existing']}\n"
        f"  • Échoués (path traversal / OSError) : {stats['failed']}"
    )

    if stats["skipped_existing"] > 0 and not overwrite:
        console.print(
            "\n[dim]→ Pour écraser les fichiers existants, relance avec --overwrite.[/dim]"
        )
    if stats["failed"] > 0:
        console.print(
            "\n[yellow]⚠ Certains fichiers ont échoué — vérifie les permissions "
            "ou la présence de chemins suspects (..) dans le backup.[/yellow]"
        )

    console.print(
        "\n[bold cyan]Post-restore checklist :[/bold cyan]\n"
        "  1. [dim]uv run python scripts/reindex_episodes.py[/dim] (Chroma index)\n"
        "  2. [dim]just health[/dim] (sanity check)\n"
        "  3. [dim]just killswitch release[/dim] (si engagé pour la procédure)\n"
    )


if __name__ == "__main__":
    app()
