"""Run Mission — déclenche une mission via le workflow MVP de la Phase 1.

Usage:
    uv run python scripts/run_mission.py --title "Titre court" --description "Description longue"
    uv run python scripts/run_mission.py --title "..." --description "..." --apply
    uv run python scripts/run_mission.py --interactive

La mission est exécutée en chaîne : Orchestrator → Architect → Developer → Reviewer.
Les épisodes et le résumé sont écrits dans data/memory/.

Mode --apply (Phase 1.5) : si le verdict est APPROVED, les fichiers proposés sont écrits
sur disque dans les dossiers whitelistés (src/, tests/, scripts/, docs/, prompts/, skills/).
Par défaut --apply n'overwrite pas les fichiers existants — utiliser --force pour cela.
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
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory
from src.orchestrator.workflow import Workflow
from src.tools.apply_files import ApplyAction, apply_files

app = typer.Typer(no_args_is_help=False, add_completion=False)
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
def run(
    title: str = typer.Option(None, "--title", "-t", help="Titre court de la mission"),
    description: str = typer.Option(None, "--description", "-d", help="Description détaillée"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Saisie interactive"),
    apply: bool = typer.Option(False, "--apply", help="Écrit les fichiers sur disque si APPROVED"),
    force: bool = typer.Option(False, "--force", help="Avec --apply : overwrite les fichiers existants"),
) -> None:
    settings = get_settings()
    setup_logging(level=settings.log_level, fmt=settings.log_format)

    if interactive or not title or not description:
        title = title or typer.prompt("Titre de la mission")
        description = description or typer.prompt("Description complète")

    memory_root = settings.project_root / "data" / "memory"
    memory = FileMemory(memory_root)
    vector_memory = VectorMemory(persist_dir=settings.chroma_persist_dir)
    vector_skills = VectorMemory(
        persist_dir=settings.chroma_persist_dir, collection_name="agent_skills"
    )
    skills_library = SkillsLibrary(
        settings.project_root / "skills", vector_memory=vector_skills
    )

    console.print(
        Panel.fit(
            f"[bold cyan]Mission :[/bold cyan] {title}\n"
            f"[dim]Mémoire fichier : {memory_root}[/dim]\n"
            f"[dim]Mémoire vectorielle : {vector_memory.count()} épisodes indexés[/dim]\n"
            f"[dim]Skills library : {skills_library.count()} skill(s) apprises "
            f"(sémantique : {vector_skills.count()} indexées)[/dim]",
            border_style="cyan",
        )
    )

    workflow = Workflow(
        memory=memory,
        settings=settings,
        vector_memory=vector_memory,
        skills_library=skills_library,
    )
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
        console.print("\n[bold cyan]Fichiers proposés :[/bold cyan]")
        for f in result.files_produced:
            console.print(f"\n[bold]{f['path']}[/bold]")
            lang = f.get("language") or "text"
            console.print(Syntax(f["content"], lang, theme="monokai", line_numbers=True))

    # --- Apply mode (Phase 1.5) ---
    if apply:
        if not result.success:
            console.print("\n[yellow]--apply ignoré : verdict non-APPROVED, rien n'est écrit.[/yellow]")
        elif not result.files_produced:
            console.print("\n[yellow]--apply ignoré : aucun fichier à écrire.[/yellow]")
        else:
            console.print(
                f"\n[bold cyan]Application sur disque[/bold cyan] "
                f"(force={force})…"
            )
            apply_results = apply_files(
                files=result.files_produced,
                project_root=settings.project_root,
                force=force,
            )
            apply_table = Table(show_lines=False)
            apply_table.add_column("Action", style="white")
            apply_table.add_column("Fichier", style="cyan")
            apply_table.add_column("Détail", style="dim")
            for r in apply_results:
                style = _ACTION_STYLES.get(r.action, "white")
                detail = (
                    f"{r.bytes_written} octets"
                    if r.action == ApplyAction.WRITTEN
                    else r.reason
                )
                apply_table.add_row(
                    f"[{style}]{r.action.value}[/{style}]",
                    r.path,
                    detail,
                )
            console.print(apply_table)
    else:
        console.print(
            "\n[dim]Mode dry-run actif. Ajoute [bold]--apply[/bold] pour écrire les fichiers sur disque.[/dim]"
        )

    console.print("\n[dim]Résumé écrit dans :[/dim] " f"{memory_root / 'missions' / (str(result.mission_id) + '.md')}")
    raise SystemExit(0 if result.success else 1)


if __name__ == "__main__":
    app()
