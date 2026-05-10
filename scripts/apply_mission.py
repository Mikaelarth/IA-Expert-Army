"""apply_mission — applique sur disque une mission déjà exécutée et APPROVED.

Utile pour :
- Tester en condition réelle le mode --apply sur une mission validée historiquement.
- Réintégrer dans le projet le code d'une mission qui avait été lancée en dry-run.

Usage:
    uv run python scripts/apply_mission.py <mission-id-prefix>
    uv run python scripts/apply_mission.py b0d6e871 --force --allow-non-approved

Sécurité : par défaut on refuse d'appliquer une mission non-APPROVED.
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

from src.core.config import get_settings
from src.memory.file_memory import FileMemory
from src.orchestrator.agents._parsers import extract_files
from src.tools.apply_files import ApplyAction, apply_files

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()

_ACTION_STYLES = {
    ApplyAction.WRITTEN: "green",
    ApplyAction.SKIPPED_EXISTS: "yellow",
    ApplyAction.REJECTED_PATH: "red",
    ApplyAction.REJECTED_NAME: "red",
    ApplyAction.REJECTED_OUTSIDE: "red",
    ApplyAction.REJECTED_DIR: "red",
}


@app.command()
def apply(
    mission_id_prefix: str = typer.Argument(..., help="Préfixe d'UUID (8+ chars) ou UUID complet"),
    force: bool = typer.Option(False, "--force", help="Overwrite les fichiers existants"),
    allow_non_approved: bool = typer.Option(False, "--allow-non-approved", help="Applique même si verdict != APPROVED"),
) -> None:
    settings = get_settings()
    memory = FileMemory(settings.project_root / "data" / "memory")

    # Trouve la mission
    matching = [p for p in memory.list_missions() if p.stem.startswith(mission_id_prefix)]
    if not matching:
        console.print(f"[red]Aucune mission trouvée avec le préfixe « {mission_id_prefix} ».[/red]")
        raise SystemExit(1)
    if len(matching) > 1:
        console.print(f"[red]Préfixe ambigu — {len(matching)} missions matchent. Précise plus.[/red]")
        for p in matching:
            console.print(f"  - {p.stem}")
        raise SystemExit(1)

    mission_path = matching[0]
    mission_id = mission_path.stem
    summary = memory.get_mission_summary(mission_id)
    if summary is None:
        console.print(f"[red]Impossible de lire le résumé de mission {mission_id}.[/red]")
        raise SystemExit(1)

    title = summary.metadata.get("title", "(sans titre)")
    verdict = summary.metadata.get("final_verdict", "?")
    score = summary.metadata.get("quality_score")

    console.print(f"\n[bold cyan]Mission :[/bold cyan] {title}")
    console.print(f"[dim]ID :[/dim] {mission_id}")
    console.print(f"[dim]Verdict :[/dim] {verdict} · [dim]Score :[/dim] {score}")

    if verdict != "APPROVED" and not allow_non_approved:
        console.print(
            "\n[bold red]Refusé : verdict non-APPROVED.[/bold red] "
            "Utilise --allow-non-approved pour forcer."
        )
        raise SystemExit(2)

    # Trouve l'épisode du backend_developer (c'est lui qui produit les fichiers)
    episodes = memory.list_episodes(mission_id)
    dev_episodes = [
        p for p in episodes if "backend_developer" in p.stem or "developer" in p.stem
    ]
    if not dev_episodes:
        console.print(f"[red]Aucun épisode developer trouvé pour cette mission.[/red]")
        raise SystemExit(1)

    # Le dernier épisode developer est le plus à jour (cas de boucle de réparation)
    dev_episode = sorted(dev_episodes)[-1]
    record = memory.read_episode(dev_episode)

    # Re-parse les fichiers depuis la sortie brute
    body = record.body
    raw_marker = "## Sortie brute"
    if raw_marker in body:
        raw_section = body.split(raw_marker, 1)[1]
    else:
        raw_section = body
    files = extract_files(raw_section)

    if not files:
        console.print("[yellow]Aucun fichier extrait de l'épisode developer.[/yellow]")
        raise SystemExit(0)

    console.print(f"\n[cyan]{len(files)} fichier(s) à appliquer · force={force}[/cyan]\n")

    results = apply_files(
        files=files,
        project_root=settings.project_root,
        force=force,
    )

    table = Table(show_lines=False)
    table.add_column("Action", style="white")
    table.add_column("Fichier", style="cyan")
    table.add_column("Détail", style="dim")
    written = 0
    for r in results:
        style = _ACTION_STYLES.get(r.action, "white")
        if r.action == ApplyAction.WRITTEN:
            written += 1
            detail = f"{r.bytes_written} octets"
        else:
            detail = r.reason
        table.add_row(f"[{style}]{r.action.value}[/{style}]", r.path, detail)
    console.print(table)

    console.print(
        f"\n[bold green]{written}/{len(results)} fichier(s) écrits.[/bold green]"
    )
    raise SystemExit(0 if written == len(results) else 1)


if __name__ == "__main__":
    app()
