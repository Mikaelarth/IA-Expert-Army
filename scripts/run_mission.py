"""Run Mission — déclenche une mission via le workflow MVP de la Phase 1.

Usage:
    uv run python scripts/run_mission.py --title "Titre court" --description "Description longue"
    uv run python scripts/run_mission.py --title "..." --description "..." --apply
    uv run python scripts/run_mission.py --title "..." --description "..." --apply --validate
    uv run python scripts/run_mission.py --interactive

La mission est exécutée en chaîne : Orchestrator → Architect → Developer → Reviewer.
Les épisodes et le résumé sont écrits dans data/memory/.

Mode --apply (Phase 1.5) : si le verdict est APPROVED, les fichiers proposés sont écrits
sur disque dans les dossiers whitelistés (src/, tests/, scripts/, docs/, prompts/, skills/).
Par défaut --apply n'overwrite pas les fichiers existants — utiliser --force pour cela.

Mode --validate (Phase 8) : avec --apply, lance pytest dans le sandbox Docker sur les
fichiers écrits et fail si les tests ne passent pas (exit 4). Boucle qualité fermée
DÈS la mission live, sans étape manuelle de re-validation.
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

from src.core.budget import BudgetController
from src.core.config import get_settings
from src.core.killswitch import Killswitch
from src.core.logging import setup_logging
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory
from src.orchestrator.router import MissionRouter
from src.tools.apply_files import ApplyAction, apply_files
from src.tools.sandbox_validate import print_sandbox_result, validate_files_in_sandbox

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
    apply: bool = typer.Option(False, "--apply", help="Écrit les fichiers sur disque si APPROVED (Engineering only)"),
    force: bool = typer.Option(False, "--force", help="Avec --apply : overwrite les fichiers existants"),
    guild: str = typer.Option(None, "--guild", "-g", help="Force la guilde (engineering | research | creative | business)"),
    validate: bool = typer.Option(
        False, "--validate",
        help="Avec --apply : lance pytest sandbox sur les fichiers écrits (boucle qualité fermée)"
    ),
    sandbox_image: str = typer.Option("iaa-sandbox:latest", "--sandbox-image"),
    sandbox_timeout: int = typer.Option(60, "--sandbox-timeout", help="Timeout pytest sandbox en secondes"),
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
    budget = BudgetController(
        state_path=settings.project_root / "data" / "budget_state.json",
        daily_budget_usd=settings.daily_budget_usd,
    )
    killswitch = Killswitch(settings.project_root / "data" / ".killswitch")

    router = MissionRouter(
        memory=memory,
        settings=settings,
        vector_memory=vector_memory,
        skills_library=skills_library,
        budget=budget,
        killswitch=killswitch,
    )
    decision = router.decide(title, description, force_guild=guild)

    console.print(
        Panel.fit(
            f"[bold cyan]Mission :[/bold cyan] {title}\n"
            f"[bold magenta]Guilde :[/bold magenta] {decision.guild}  "
            f"[dim]({decision.reason})[/dim]\n"
            f"[dim]Mémoire vectorielle : {vector_memory.count()} épisodes indexés[/dim]\n"
            f"[dim]Skills library : {skills_library.count()} skill(s) apprises "
            f"(sémantique : {vector_skills.count()} indexées)[/dim]\n"
            f"[dim]Budget restant : ${budget.remaining_today():.4f} / ${settings.daily_budget_usd:.2f}[/dim]",
            border_style="cyan",
        )
    )

    result = asyncio.run(router.run(title=title, description=description, force_guild=guild))

    raw = result.raw_result
    files_produced = raw.get("files_produced", [])
    synthesis_md = raw.get("synthesis_markdown", "")

    table = Table(title="Résultat de la mission", show_lines=True)
    table.add_column("Champ", style="cyan")
    table.add_column("Valeur", style="white")
    table.add_row("Mission ID", str(result.mission_id))
    table.add_row("Guilde", result.guild)
    table.add_row("Verdict", result.final_verdict)
    table.add_row("Quality score", f"{result.quality_score:.2f}" if result.quality_score is not None else "n/a")
    table.add_row("Coût total (USD)", f"{result.total_cost_usd:.4f}")
    table.add_row("Durée (s)", f"{result.total_duration_seconds:.2f}")
    if files_produced:
        table.add_row("Fichiers produits", str(len(files_produced)))
    if synthesis_md:
        table.add_row("Synthèse (chars)", str(len(synthesis_md)))
    console.print(table)

    if synthesis_md:
        console.print("\n[bold cyan]Synthèse produite :[/bold cyan]\n")
        from rich.markdown import Markdown
        console.print(Markdown(synthesis_md))

    if files_produced:
        console.print("\n[bold cyan]Fichiers proposés :[/bold cyan]")
        for f in files_produced:
            console.print(f"\n[bold]{f['path']}[/bold]")
            lang = f.get("language") or "text"
            console.print(Syntax(f["content"], lang, theme="monokai", line_numbers=True))

    # --- Apply mode (Phase 1.5) — Engineering only ---
    apply_succeeded = False
    written_files: list[dict[str, str]] = []
    if apply:
        if result.guild != "engineering":
            console.print(
                f"\n[yellow]--apply ignoré : la guilde [bold]{result.guild}[/bold] ne produit pas de fichiers à écrire.[/yellow]"
            )
        elif not result.success:
            console.print("\n[yellow]--apply ignoré : verdict non-APPROVED, rien n'est écrit.[/yellow]")
        elif not files_produced:
            console.print("\n[yellow]--apply ignoré : aucun fichier à écrire.[/yellow]")
        else:
            console.print(
                f"\n[bold cyan]Application sur disque[/bold cyan] "
                f"(force={force})…"
            )
            apply_results = apply_files(
                files=files_produced,
                project_root=settings.project_root,
                force=force,
            )
            apply_table = Table(show_lines=False)
            apply_table.add_column("Action", style="white")
            apply_table.add_column("Fichier", style="cyan")
            apply_table.add_column("Détail", style="dim")
            for f, r in zip(files_produced, apply_results, strict=False):
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
                if r.action == ApplyAction.WRITTEN:
                    written_files.append(f)
            console.print(apply_table)
            apply_succeeded = bool(written_files)
    elif result.guild == "engineering" and files_produced:
        console.print(
            "\n[dim]Mode dry-run actif. Ajoute [bold]--apply[/bold] pour écrire les fichiers sur disque.[/dim]"
        )

    # --- Validate mode (Phase 8) — sandbox pytest sur les fichiers écrits ---
    validation_failed = False
    if validate:
        if not apply:
            console.print(
                "\n[yellow]--validate ignoré : nécessite --apply pour avoir des fichiers à tester.[/yellow]"
            )
        elif not apply_succeeded:
            console.print(
                "\n[yellow]--validate ignoré : aucun fichier écrit (apply n'a rien produit ou guild non-engineering).[/yellow]"
            )
        else:
            console.print("\n[bold cyan]Validation sandbox des fichiers appliqués…[/bold cyan]")
            sandbox_result = validate_files_in_sandbox(
                written_files,
                sandbox_image=sandbox_image,
                sandbox_timeout=sandbox_timeout,
                console=console,
            )
            if sandbox_result is None:
                console.print(
                    "[yellow]Sandbox indisponible — apply OK mais qualité non vérifiée.[/yellow]"
                )
            else:
                print_sandbox_result(sandbox_result, console=console)
                if sandbox_result.exit_code != 0:
                    validation_failed = True
                    console.print(
                        "\n[bold red]Validation sandbox ÉCHOUÉE.[/bold red] "
                        "Les fichiers ont été appliqués mais ne passent pas pytest. "
                        "Inspecte le diff avant de committer."
                    )
                else:
                    console.print(
                        "\n[bold green]Boucle qualité fermée : mission APPROVED + apply OK + sandbox pytest OK.[/bold green]"
                    )

    console.print("\n[dim]Résumé écrit dans :[/dim] " f"{memory_root / 'missions' / (str(result.mission_id) + '.md')}")

    # Exit code combiné : si validate a fail, exit 4 (cf. apply_mission.py).
    # Sinon, exit selon le succès de la mission elle-même.
    if validation_failed:
        raise SystemExit(4)
    raise SystemExit(0 if result.success else 1)


if __name__ == "__main__":
    app()
