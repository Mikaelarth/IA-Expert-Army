"""nightly_learning — déclenche le pattern mining + l'extraction de skills.

À lancer périodiquement (manuel pour la Phase 5 MVP, ou via cron/Task Scheduler en Phase 5+).

Usage:
    uv run python scripts/nightly_learning.py
    uv run python scripts/nightly_learning.py --top-k 5 --min-quality 0.9
    uv run python scripts/nightly_learning.py --dry-run   # ne demande pas Claude, montre juste ce qui serait minté
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.core.config import get_settings
from src.core.logging import setup_logging
from src.learning.pattern_miner import PatternMiner
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()


@app.command()
def mine(
    top_k: int = typer.Option(3, "--top-k", "-k", help="Nombre d'épisodes top par agent"),
    min_quality: float = typer.Option(0.85, "--min-quality", "-q", help="Score minimum pour considérer un épisode"),
    min_episodes: int = typer.Option(2, "--min-episodes", "-n", help="Minimum d'épisodes pour produire une skill"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Affiche le plan sans appeler Claude"),
    agents: str = typer.Option(
        None, "--agents", "-a",
        help="Liste séparée par virgules d'agents à miner (par défaut tous). Ex: research_lead,tech_watch"
    ),
) -> None:
    settings = get_settings()
    setup_logging(level=settings.log_level, fmt=settings.log_format)
    memory = FileMemory(settings.project_root / "data" / "memory")
    vector_skills = VectorMemory(
        persist_dir=settings.chroma_persist_dir, collection_name="agent_skills"
    )
    skills_lib = SkillsLibrary(
        settings.project_root / "skills", vector_memory=vector_skills
    )

    selected_agents: tuple[str, ...] | None = None
    if agents:
        selected_agents = tuple(a.strip() for a in agents.split(",") if a.strip())
        unknown = [a for a in selected_agents if a not in PatternMiner.AGENT_WHITELIST]
        if unknown:
            console.print(
                f"[red]Agents inconnus : {unknown}. Connus : {PatternMiner.AGENT_WHITELIST}[/red]"
            )
            raise SystemExit(2)

    miner = PatternMiner(
        memory=memory,
        skills=skills_lib,
        settings=settings,
        min_episodes=min_episodes,
        top_k=top_k,
        min_quality=min_quality,
        agents=selected_agents,
    )

    if dry_run:
        grouped = miner._load_eligible_episodes()
        plan_table = Table(title="Plan de mining (dry-run)", show_lines=True)
        plan_table.add_column("Agent", style="cyan")
        plan_table.add_column("Épisodes éligibles", justify="right")
        plan_table.add_column("Statut", style="white")
        for agent in miner.agents:
            n = len(grouped.get(agent, []))
            status = (
                "[yellow]skip[/yellow]" if n < min_episodes else "[green]would mine[/green]"
            )
            plan_table.add_row(agent, str(n), status)
        console.print(plan_table)
        return

    console.print(
        Panel.fit(
            f"[bold cyan]Nightly learning[/bold cyan]\n"
            f"top_k={top_k} · min_quality={min_quality} · min_episodes={min_episodes}",
            border_style="cyan",
        )
    )

    report = asyncio.run(miner.mine())

    res_table = Table(title="Résultat du mining", show_lines=True)
    res_table.add_column("Agent", style="cyan")
    res_table.add_column("Épisodes", justify="right")
    res_table.add_column("Skill", style="green")
    res_table.add_column("Coût", justify="right")
    res_table.add_column("Erreur", style="red")

    for r in report.per_agent:
        skill_label = r.skill_extracted.title if r.skill_extracted else "—"
        res_table.add_row(
            r.agent,
            str(r.episodes_considered),
            skill_label,
            f"${r.cost_usd:.4f}",
            r.error or "",
        )
    console.print(res_table)

    counters = Counter(s.agent for s in (r.skill_extracted for r in report.per_agent) if s)
    console.print(
        f"\n[bold green]{report.skills_created} skill(s) créée(s)[/bold green] · "
        f"coût total : [bold]${report.total_cost_usd:.4f}[/bold] · "
        f"durée : {(report.ended_at - report.started_at).total_seconds():.1f}s"
    )
    if counters:
        console.print(f"[dim]Répartition : {dict(counters)}[/dim]")
    raise SystemExit(0 if report.skills_created > 0 else 1)


if __name__ == "__main__":
    app()
