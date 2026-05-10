"""daily_digest — rapport quotidien des missions et activité de l'équipe.

Garde-fou Phase 6 — à exécuter chaque soir (cron / Task Scheduler) pour que
l'utilisateur garde la main sur ce qui s'est passé en mode autonome.

Usage:
    uv run python scripts/daily_digest.py                 # affiche le digest du jour
    uv run python scripts/daily_digest.py --date 2026-05-10
    uv run python scripts/daily_digest.py --output digest.md   # sauvegarde aussi
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import typer
from rich.console import Console
from rich.markdown import Markdown

from src.core.budget import BudgetController
from src.core.config import get_settings
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()


def _parse_date(s: str | None) -> date:
    if s is None:
        return date.today()
    return datetime.fromisoformat(s).date()


def _missions_for_date(memory: FileMemory, target: date) -> list:
    out = []
    for path in memory.list_missions():
        record = memory.get_mission_summary(path.stem)
        if record is None:
            continue
        meta = record.metadata
        started = meta.get("started_at")
        if not isinstance(started, str):
            continue
        try:
            d = datetime.fromisoformat(started.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if d == target:
            out.append((path, record))
    return out


def _skills_created_on(skills: SkillsLibrary, target: date) -> int:
    n = 0
    for agent_dir in skills.root.iterdir():
        if not agent_dir.is_dir():
            continue
        for f in agent_dir.glob("*.md"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime).date()
                if mtime == target:
                    n += 1
            except OSError:
                continue
    return n


def _build_digest(target: date) -> str:
    s = get_settings()
    memory = FileMemory(s.project_root / "data" / "memory")
    skills = SkillsLibrary(s.project_root / "skills")
    budget = BudgetController(
        state_path=s.project_root / "data" / "budget_state.json",
        daily_budget_usd=s.daily_budget_usd,
    )

    missions = _missions_for_date(memory, target)
    success_count = sum(1 for _, r in missions if r.metadata.get("success"))
    total_cost = sum(float(r.metadata.get("total_cost_usd", 0) or 0) for _, r in missions)
    avg_quality = (
        sum(
            float(r.metadata.get("quality_score", 0) or 0)
            for _, r in missions
            if isinstance(r.metadata.get("quality_score"), (int, float))
        )
        / max(1, sum(1 for _, r in missions if isinstance(r.metadata.get("quality_score"), (int, float))))
    )
    verdict_counts = Counter(r.metadata.get("final_verdict", "?") for _, r in missions)

    skills_count = _skills_created_on(skills, target)
    budget_status = budget.status()

    lines = [
        f"# Daily Digest — IA-Expert-Army — {target.isoformat()}",
        "",
        "## Synthèse",
        "",
        f"- **Missions exécutées :** {len(missions)} ({success_count} APPROVED)",
        f"- **Score qualité moyen :** {avg_quality:.2f}" if missions else "- **Score qualité moyen :** n/a",
        f"- **Coût total des missions :** ${total_cost:.4f}",
        f"- **Skills auto-créées aujourd'hui :** {skills_count}",
        f"- **Budget API du jour :** ${budget_status['spent_usd']:.4f} / "
        f"${budget_status['daily_budget_usd']:.2f} ({budget_status['percent_used']:.1f}%)",
        "",
    ]
    if verdict_counts:
        lines.append("## Verdicts")
        lines.append("")
        for v, n in verdict_counts.most_common():
            lines.append(f"- {v} : {n}")
        lines.append("")

    if missions:
        lines.append("## Missions")
        lines.append("")
        lines.append("| Heure | Titre | Verdict | Score | Coût | Durée |")
        lines.append("|-------|-------|---------|-------|------|-------|")
        for _, r in sorted(missions, key=lambda x: x[1].metadata.get("started_at", "")):
            meta = r.metadata
            ts = (meta.get("started_at") or "")[11:16]  # HH:MM
            title = meta.get("title", "?")
            verdict = meta.get("final_verdict", "?")
            score = meta.get("quality_score")
            score_str = f"{score:.2f}" if isinstance(score, (int, float)) else "—"
            cost = meta.get("total_cost_usd")
            cost_str = f"${cost:.4f}" if isinstance(cost, (int, float)) else "—"
            dur = meta.get("total_duration_seconds")
            dur_str = f"{dur:.1f}s" if isinstance(dur, (int, float)) else "—"
            lines.append(f"| {ts} | {title} | {verdict} | {score_str} | {cost_str} | {dur_str} |")
        lines.append("")

    if budget_status["percent_used"] >= 100:
        lines.append("> ⚠ **Budget journalier atteint** — toute nouvelle mission sera refusée jusqu'à minuit.")
    elif budget_status["percent_used"] >= 80:
        lines.append("> ⚠ Plus de 80% du budget consommé.")

    if not missions:
        lines.append("_Aucune mission exécutée ce jour._")

    return "\n".join(lines)


@app.command()
def show(
    date_str: str | None = typer.Option(None, "--date", "-d", help="Date au format YYYY-MM-DD"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Fichier où sauvegarder le digest"),
) -> None:
    target = _parse_date(date_str)
    digest = _build_digest(target)
    console.print(Markdown(digest))
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(digest, encoding="utf-8")
        console.print(f"\n[dim]Digest sauvegardé dans {output}[/dim]")


if __name__ == "__main__":
    app()
