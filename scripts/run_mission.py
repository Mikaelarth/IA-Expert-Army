"""Run Mission — déclenche une mission via le workflow MVP de la Phase 1.

Usage:
    uv run python scripts/run_mission.py --title "Titre court" --description "Description longue"
    uv run python scripts/run_mission.py  # mode interactif

La mission est exécutée en chaîne : Orchestrator → Architect → Developer → Reviewer.
Les épisodes et le résumé sont écrits dans data/memory/.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from src.core.config import get_settings
from src.core.logging import setup_logging
from src.memory.file_memory import FileMemory
from src.orchestrator.workflow import Workflow

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()


@app.command()
def run(
    title: str = typer.Option(None, "--title", "-t", help="Titre court de la mission"),
    description: str = typer.Option(None, "--description", "-d", help="Description détaillée"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Saisie interactive"),
) -> None:
    settings = get_settings()
    setup_logging(level=settings.log_level, fmt=settings.log_format)

    if interactive or not title or not description:
        title = title or typer.prompt("Titre de la mission")
        description = description or typer.prompt("Description complète")

    memory_root = settings.project_root / "data" / "memory"
    memory = FileMemory(memory_root)

    console.print(
        Panel.fit(
            f"[bold cyan]Mission :[/bold cyan] {title}\n"
            f"[dim]Mémoire : {memory_root}[/dim]",
            border_style="cyan",
        )
    )

    workflow = Workflow(memory=memory, settings=settings)
    result = asyncio.run(workflow.run(title=title, description=description))

    table = Table(title="Résultat de la mission", show_lines=True)
    table.add_column("Champ", style="cyan")
    table.add_column("Valeur", style="white")
    table.add_row("Mission ID", str(result.mission_id))
    table.add_row("Verdict", result.final_verdict)
    table.add_row("Quality score", f"{result.quality_score:.2f}" if result.quality_score is not None else "n/a")
    table.add_row("Coût total (USD)", f"{result.total_cost_usd:.4f}")
    table.add_row("Durée (s)", f"{result.total_duration_seconds:.2f}")
    table.add_row("Épisodes", str(result.episodes_count))
    table.add_row("Fichiers produits", str(len(result.files_produced)))
    console.print(table)

    if result.files_produced:
        console.print("\n[bold cyan]Fichiers produits :[/bold cyan]")
        for f in result.files_produced:
            console.print(f"\n[bold]{f['path']}[/bold]")
            lang = f.get("language") or "text"
            console.print(Syntax(f["content"], lang, theme="monokai", line_numbers=True))

    console.print("\n[dim]Résumé écrit dans :[/dim] " f"{memory_root / 'missions' / (str(result.mission_id) + '.md')}")
    raise SystemExit(0 if result.success else 1)


if __name__ == "__main__":
    app()
