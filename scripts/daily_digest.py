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


def _meta_missions_for_date(memory: FileMemory, target: date) -> list:
    """Meta-missions cross-guildes (Phase 7) commencées le jour donné."""
    out = []
    for path in memory.list_meta_missions():
        record = memory.get_meta_mission_summary(path.stem)
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


def _compute_qg_stats(missions: list) -> dict:
    """Sprint ZZ.3 — Agrège les métriques Quality Guardian d'un lot de missions.

    Retourne :
      - count_with_qg : nombre de missions ayant un qg_verdict (= QG appliqué)
      - verdict_counts : Counter{ACCEPT, NEEDS_REWORK, ESCALATE}
      - divergence_count : missions où qg_verdict != ACCEPT mais guild_verdict == APPROVED
        (= cas où le QG a flaggé quelque chose que la guilde avait raté)
      - score_diff_significant : missions où |qg_final_score - guild_score| > 0.10
        (= signal de divergence de calibration)
    """
    verdict_counts: Counter[str] = Counter()
    divergence_count = 0
    score_diff_significant = 0
    count_with_qg = 0
    for _, rec in missions:
        m = rec.metadata
        qg = m.get("qg_verdict")
        if qg is None:
            continue
        count_with_qg += 1
        verdict_counts[str(qg)] += 1
        if qg != "ACCEPT" and m.get("final_verdict") == "APPROVED":
            divergence_count += 1
        qg_score = m.get("qg_final_score")
        guild_score = m.get("quality_score")
        if (
            isinstance(qg_score, (int, float))
            and isinstance(guild_score, (int, float))
            and abs(float(qg_score) - float(guild_score)) > 0.10
        ):
            score_diff_significant += 1
    return {
        "count_with_qg": count_with_qg,
        "verdict_counts": verdict_counts,
        "divergence_count": divergence_count,
        "score_diff_significant": score_diff_significant,
    }


def _compute_meta_stats(meta_missions: list) -> dict:
    """Agrège les métriques d'un lot de meta-missions du jour.

    Retourne : count, total_cost, total_duration, verdict_counts, guilds_counts,
    avg_score, avg_n_sub. Aucun calcul si liste vide (tout à 0 / vide).
    """
    if not meta_missions:
        return {
            "count": 0,
            "total_cost": 0.0,
            "total_duration": 0.0,
            "verdict_counts": Counter(),
            "guilds_counts": Counter(),
            "avg_score": None,
            "avg_n_sub": 0.0,
        }
    total_cost = 0.0
    total_duration = 0.0
    scores: list[float] = []
    n_subs: list[int] = []
    verdict_counts: Counter[str] = Counter()
    guilds_counts: Counter[str] = Counter()
    for _, rec in meta_missions:
        m = rec.metadata
        c = m.get("total_cost_usd")
        if isinstance(c, (int, float)):
            total_cost += float(c)
        d = m.get("total_duration_seconds")
        if isinstance(d, (int, float)):
            total_duration += float(d)
        s = m.get("overall_quality_score")
        if isinstance(s, (int, float)):
            scores.append(float(s))
        n = m.get("n_sub_missions")
        if isinstance(n, int):
            n_subs.append(n)
        verdict_counts[str(m.get("final_verdict", "?"))] += 1
        for g in m.get("guilds") or []:
            guilds_counts[str(g)] += 1
    return {
        "count": len(meta_missions),
        "total_cost": total_cost,
        "total_duration": total_duration,
        "verdict_counts": verdict_counts,
        "guilds_counts": guilds_counts,
        "avg_score": sum(scores) / len(scores) if scores else None,
        "avg_n_sub": sum(n_subs) / len(n_subs) if n_subs else 0.0,
    }


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
    avg_quality = sum(
        float(r.metadata.get("quality_score", 0) or 0)
        for _, r in missions
        if isinstance(r.metadata.get("quality_score"), (int, float))
    ) / max(
        1, sum(1 for _, r in missions if isinstance(r.metadata.get("quality_score"), (int, float)))
    )
    verdict_counts = Counter(r.metadata.get("final_verdict", "?") for _, r in missions)

    meta_missions = _meta_missions_for_date(memory, target)
    meta_stats = _compute_meta_stats(meta_missions)
    qg_stats = _compute_qg_stats(missions)

    skills_count = _skills_created_on(skills, target)
    budget_status = budget.status()

    lines = [
        f"# Daily Digest — IA-Expert-Army — {target.isoformat()}",
        "",
        "## Synthèse",
        "",
        f"- **Missions exécutées :** {len(missions)} ({success_count} APPROVED)",
        f"- **Score qualité moyen :** {avg_quality:.2f}"
        if missions
        else "- **Score qualité moyen :** n/a",
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

    if qg_stats["count_with_qg"]:
        lines.append("## Quality Guardian (peer review méta)")
        lines.append("")
        lines.append(
            f"- **Missions auditées :** {qg_stats['count_with_qg']} / {len(missions)} "
            f"({100 * qg_stats['count_with_qg'] // max(1, len(missions))}%)"
        )
        if qg_stats["verdict_counts"]:
            verdicts_str = " · ".join(
                f"{v}={n}" for v, n in qg_stats["verdict_counts"].most_common()
            )
            lines.append(f"- **Verdicts QG :** {verdicts_str}")
        if qg_stats["divergence_count"]:
            lines.append(
                f"- ⚠ **Divergence guilde↔QG :** {qg_stats['divergence_count']} missions "
                f"APPROVED par la guilde mais flaggées par le QG"
            )
        if qg_stats["score_diff_significant"]:
            lines.append(
                f"- **Écart de score |QG − guild| > 0.10 :** "
                f"{qg_stats['score_diff_significant']} missions "
                f"(signal de calibration drift à surveiller)"
            )
        lines.append("")

    if meta_stats["count"]:
        lines.append("## Meta-missions cross-guildes (Phase 7)")
        lines.append("")
        lines.append(
            f"- **Exécutées aujourd'hui :** {meta_stats['count']} "
            f"({meta_stats['avg_n_sub']:.1f} sous-missions en moyenne)"
        )
        if meta_stats["avg_score"] is not None:
            lines.append(f"- **Score global moyen :** {meta_stats['avg_score']:.2f}")
        lines.append(f"- **Coût cumulé :** ${meta_stats['total_cost']:.4f}")
        lines.append(f"- **Durée cumulée :** {meta_stats['total_duration']:.1f}s")
        if meta_stats["verdict_counts"]:
            verdicts_str = " · ".join(
                f"{v}={n}" for v, n in meta_stats["verdict_counts"].most_common()
            )
            lines.append(f"- **Verdicts globaux :** {verdicts_str}")
        if meta_stats["guilds_counts"]:
            guilds_str = " · ".join(
                f"{g}={n}" for g, n in meta_stats["guilds_counts"].most_common()
            )
            lines.append(f"- **Guildes traversées :** {guilds_str}")
        lines.append("")
        lines.append("| Heure | Titre | Verdict | Score | Coût | Sous-missions |")
        lines.append("|-------|-------|---------|-------|------|---------------|")
        for _, rec in sorted(meta_missions, key=lambda x: x[1].metadata.get("started_at", "")):
            m = rec.metadata
            ts = (m.get("started_at") or "")[11:16]
            title = m.get("title", "?")
            verdict = m.get("final_verdict", "?")
            score = m.get("overall_quality_score")
            score_str = f"{score:.2f}" if isinstance(score, (int, float)) else "—"
            cost = m.get("total_cost_usd")
            cost_str = f"${cost:.4f}" if isinstance(cost, (int, float)) else "—"
            n_sub = m.get("n_sub_missions", "?")
            guilds_list = ", ".join(m.get("guilds") or [])
            lines.append(
                f"| {ts} | {title} | {verdict} | {score_str} | {cost_str} | {n_sub} ({guilds_list}) |"
            )
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
        lines.append(
            "> ⚠ **Budget journalier atteint** — toute nouvelle mission sera refusée jusqu'à minuit."
        )
    elif budget_status["percent_used"] >= 80:
        lines.append("> ⚠ Plus de 80% du budget consommé.")

    if not missions:
        lines.append("_Aucune mission exécutée ce jour._")

    return "\n".join(lines)


@app.command()
def show(
    date_str: str | None = typer.Option(None, "--date", "-d", help="Date au format YYYY-MM-DD"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Fichier où sauvegarder le digest"
    ),
    notify: bool = typer.Option(
        False,
        "--notify",
        help="Envoie aussi le digest via webhook (Sprint HHH — Discord/Slack/Telegram/generic)",
    ),
) -> None:
    target = _parse_date(date_str)
    digest = _build_digest(target)
    console.print(Markdown(digest))
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(digest, encoding="utf-8")
        console.print(f"\n[dim]Digest sauvegardé dans {output}[/dim]")

    if notify:
        from src.core.notifier import NotifyLevel, get_notifier_from_settings

        n = get_notifier_from_settings()
        if not n.is_enabled:
            console.print(
                "[yellow]--notify : NOTIFY_WEBHOOK_URL non configuré dans .env, "
                "envoi skippé.[/yellow]"
            )
        else:
            # Choix du level depuis le contenu : si REJECTED présent → warning,
            # sinon info. Heuristique simple, à raffiner si besoin.
            level = NotifyLevel.WARNING if "REJECTED" in digest else NotifyLevel.INFO
            title = f"Digest IA-Expert-Army {target.isoformat()}"
            sent = n.send(level, title, digest)
            if sent:
                console.print(
                    f"[dim green]Digest envoyé via webhook ({n.backend})[/dim green]"
                )
            else:
                console.print(
                    "[red]Échec d'envoi webhook (cf. logs). Digest local OK.[/red]"
                )


if __name__ == "__main__":
    app()
