"""autonomous_run — exécution longue autonome avec garde-fous Phase 6.

Lit une queue YAML de missions et les exécute séquentiellement en surveillant
les 5 garde-fous d'autonomie. S'arrête proprement sur dépassement de l'un
d'eux ou épuisement de la queue.

Critère de succès Phase 6 (cf. ADR-010) : « Mission longue 24h sans dérive,
dans budget ». Concrètement :

  1. Budget restant ≥ seuil (par défaut $5) — sinon STOP.
  2. Killswitch clear — sinon STOP.
  3. Error rate des N dernières < 30% (circuit breaker) — sinon STOP.
  4. Saturation rate des N dernières < 20% — sinon STOP.
  5. Quality moving average des N dernières ≥ 0.70 — sinon STOP (anti-dérive).

Le rapport final est écrit dans `data/autonomous_runs/<timestamp>.md` et
restitue : timeline, stats par mission, garde-fou déclencheur d'arrêt.

Usage :
    uv run python scripts/autonomous_run.py --queue data/autonomous_queue.yml
    uv run python scripts/autonomous_run.py --queue ... --max-missions 5
    uv run python scripts/autonomous_run.py --queue ... --dry-run  # parse only
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.core.budget import BudgetController, BudgetExceeded
from src.core.config import get_settings
from src.core.killswitch import Killswitch, KillswitchEngaged
from src.core.logging import setup_logging
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory
from src.orchestrator.router import MissionRouter, UnifiedMissionResult

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()


# ===== Garde-fous (paramètres) =====

DEFAULTS = {
    "budget_floor_usd": 5.0,
    "max_error_rate": 0.30,
    "max_saturation_rate": 0.20,
    "min_moving_quality": 0.70,
    "rolling_window": 5,  # taille de la fenêtre pour les rates / moving avg
}


# ===== Modèles =====


class QueueItem:
    """Une mission à exécuter."""

    __slots__ = ("description", "force_guild", "title")

    def __init__(self, title: str, description: str, force_guild: str | None = None) -> None:
        self.title = title
        self.description = description
        self.force_guild = force_guild


class RunRecord:
    """Une entrée dans la timeline du run autonome."""

    __slots__ = (
        "cost",
        "duration",
        "ended_at",
        "error",
        "guild",
        "quality",
        "saturated",
        "started_at",
        "title",
        "verdict",
    )

    def __init__(
        self,
        started_at: datetime,
        ended_at: datetime,
        title: str,
        guild: str,
        verdict: str,
        quality: float | None,
        cost: float,
        duration: float,
        saturated: bool,
        error: str | None = None,
    ) -> None:
        self.started_at = started_at
        self.ended_at = ended_at
        self.title = title
        self.guild = guild
        self.verdict = verdict
        self.quality = quality
        self.cost = cost
        self.duration = duration
        self.saturated = saturated
        self.error = error

    @property
    def success(self) -> bool:
        return self.verdict == "APPROVED"

    @property
    def errored(self) -> bool:
        return self.error is not None or self.verdict.startswith("FAILED")


# ===== Garde-fous (logique) =====


def evaluate_guardrails(
    history: list[RunRecord],
    budget_remaining: float,
    killswitch: Killswitch,
    cfg: dict[str, Any],
) -> tuple[bool, str | None]:
    """Retourne (ok, raison_d_arret_si_pas_ok). Pure function — testable."""
    if budget_remaining < cfg["budget_floor_usd"]:
        return (
            False,
            f"budget restant ${budget_remaining:.4f} < seuil ${cfg['budget_floor_usd']:.2f}",
        )

    try:
        killswitch.assert_clear()
    except KillswitchEngaged as exc:
        return False, f"killswitch engagé : {exc}"

    window = list(history[-cfg["rolling_window"] :])
    if not window:
        return True, None

    n = len(window)
    n_errors = sum(1 for r in window if r.errored)
    n_saturated = sum(1 for r in window if r.saturated)
    qualities = [r.quality for r in window if r.quality is not None]

    error_rate = n_errors / n
    saturation_rate = n_saturated / n

    if error_rate > cfg["max_error_rate"]:
        return False, (
            f"error rate {error_rate:.0%} > seuil {cfg['max_error_rate']:.0%} "
            f"sur les {n} dernières missions"
        )
    if saturation_rate > cfg["max_saturation_rate"]:
        return False, (
            f"saturation rate {saturation_rate:.0%} > seuil "
            f"{cfg['max_saturation_rate']:.0%} sur les {n} dernières"
        )
    if qualities:
        moving_avg = sum(qualities) / len(qualities)
        if moving_avg < cfg["min_moving_quality"]:
            return False, (
                f"quality moving avg {moving_avg:.2f} < seuil "
                f"{cfg['min_moving_quality']:.2f} (dérive détectée)"
            )

    return True, None


# ===== Queue parsing =====


def parse_queue(yaml_text: str) -> list[QueueItem]:
    """Parse une queue YAML en QueueItem list.

    Format attendu :
        missions:
          - title: "Titre 1"
            description: "Desc 1"
            guild: engineering   # optionnel
          - title: "Titre 2"
            description: |
              Multi-ligne OK.
    """
    data = yaml.safe_load(yaml_text) or {}
    missions_raw = data.get("missions") or []
    if not isinstance(missions_raw, list):
        raise ValueError("Le YAML doit contenir une clé 'missions' liste.")
    items: list[QueueItem] = []
    for i, m in enumerate(missions_raw):
        if not isinstance(m, dict):
            raise ValueError(f"Mission #{i} n'est pas un dict.")
        title = str(m.get("title", "")).strip()
        description = str(m.get("description", "")).strip()
        if not title or not description:
            raise ValueError(f"Mission #{i} : title et description requis.")
        guild = m.get("guild")
        guild_str = str(guild).strip().lower() if guild else None
        items.append(QueueItem(title=title, description=description, force_guild=guild_str))
    return items


# ===== Rapport markdown =====


def render_report(
    started: datetime,
    ended: datetime,
    history: list[RunRecord],
    stop_reason: str,
    budget_start: float,
    budget_end: float,
) -> str:
    duration_total = (ended - started).total_seconds()
    n = len(history)
    success_n = sum(1 for r in history if r.success)
    errored_n = sum(1 for r in history if r.errored)
    saturated_n = sum(1 for r in history if r.saturated)
    qualities = [r.quality for r in history if r.quality is not None]
    avg_quality = sum(qualities) / len(qualities) if qualities else None
    total_cost = sum(r.cost for r in history)

    lines = [
        f"# Autonomous Run — IA-Expert-Army — {started.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Synthèse",
        "",
        f"- **Missions exécutées :** {n}",
        f"- **Succès (APPROVED) :** {success_n} ({(success_n / n * 100) if n else 0:.0f}%)",
        f"- **Erreurs / FAILED :** {errored_n}",
        f"- **Saturations :** {saturated_n}",
        f"- **Quality moyen :** {avg_quality:.2f}"
        if avg_quality is not None
        else "- **Quality moyen :** n/a",
        f"- **Coût total :** ${total_cost:.4f}",
        f"- **Budget : début=${budget_start:.4f}, fin=${budget_end:.4f}** (consommé : ${budget_start - budget_end:.4f})",
        f"- **Durée totale :** {duration_total:.1f}s ({duration_total / 60:.1f} min)",
        f"- **Raison d'arrêt :** {stop_reason}",
        "",
        "## Timeline",
        "",
        "| Heure | Titre | Guilde | Verdict | Score | Coût | Sat | Durée |",
        "|-------|-------|--------|---------|-------|------|-----|-------|",
    ]
    for r in history:
        ts = r.started_at.strftime("%H:%M")
        score_str = f"{r.quality:.2f}" if r.quality is not None else "—"
        sat_str = "⚠" if r.saturated else ""
        lines.append(
            f"| {ts} | {r.title[:50]} | {r.guild} | {r.verdict} | "
            f"{score_str} | ${r.cost:.4f} | {sat_str} | {r.duration:.0f}s |"
        )
    if not history:
        lines.append("| _aucune mission exécutée_ | | | | | | | |")
    return "\n".join(lines)


# ===== Loop principal =====


async def run_autonomous(
    queue: list[QueueItem],
    cfg: dict[str, Any],
    max_missions: int | None = None,
) -> tuple[list[RunRecord], str, float, float]:
    """Exécute la queue séquentiellement avec garde-fous.

    Retourne (history, stop_reason, budget_start, budget_end).
    """
    s = get_settings()
    memory_root = s.project_root / "data" / "memory"
    memory = FileMemory(memory_root)
    vector = VectorMemory(persist_dir=s.chroma_persist_dir)
    vector_skills = VectorMemory(persist_dir=s.chroma_persist_dir, collection_name="agent_skills")
    skills = SkillsLibrary(s.project_root / "skills", vector_memory=vector_skills)
    budget = BudgetController(
        state_path=s.project_root / "data" / "budget_state.json",
        daily_budget_usd=s.daily_budget_usd,
    )
    killswitch = Killswitch(s.project_root / "data" / ".killswitch")

    router = MissionRouter(
        memory=memory,
        settings=s,
        vector_memory=vector,
        skills_library=skills,
        budget=budget,
        killswitch=killswitch,
    )

    history: list[RunRecord] = []
    budget_start = budget.remaining_today()
    cap = max_missions or len(queue)
    stop_reason = "queue épuisée"

    for i, item in enumerate(queue[:cap], start=1):
        budget_remaining = budget.remaining_today()
        ok, reason = evaluate_guardrails(history, budget_remaining, killswitch, cfg)
        if not ok:
            stop_reason = f"garde-fou pré-mission : {reason}"
            console.print(f"\n[bold red]STOP avant mission #{i}[/bold red] — {reason}")
            break

        console.print(
            f"\n[bold cyan]Mission {i}/{cap}[/bold cyan] · "
            f"[white]{item.title}[/white] · "
            f"[dim]guild={item.force_guild or 'auto'} · budget restant ${budget_remaining:.4f}[/dim]"
        )

        started_at = datetime.now(UTC)
        try:
            res: UnifiedMissionResult = await router.run(
                title=item.title,
                description=item.description,
                force_guild=item.force_guild,
            )
            ended_at = datetime.now(UTC)
            saturated = bool(res.raw_result.get("saturated", False))
            history.append(
                RunRecord(
                    started_at=started_at,
                    ended_at=ended_at,
                    title=item.title,
                    guild=res.guild,
                    verdict=res.final_verdict,
                    quality=res.quality_score,
                    cost=res.total_cost_usd,
                    duration=res.total_duration_seconds,
                    saturated=saturated,
                )
            )
            console.print(
                f"  → [bold]{res.final_verdict}[/bold] · score "
                f"{res.quality_score:.2f} · ${res.total_cost_usd:.4f} · "
                f"{res.total_duration_seconds:.0f}s"
                if res.quality_score is not None
                else f"  → [bold]{res.final_verdict}[/bold] · score n/a · ${res.total_cost_usd:.4f}"
            )
        except (BudgetExceeded, KillswitchEngaged) as exc:
            stop_reason = f"hard guardrail levé pendant exécution : {type(exc).__name__}: {exc}"
            console.print(f"\n[bold red]STOP pendant mission #{i}[/bold red] — {stop_reason}")
            break
        except Exception as exc:
            ended_at = datetime.now(UTC)
            history.append(
                RunRecord(
                    started_at=started_at,
                    ended_at=ended_at,
                    title=item.title,
                    guild=item.force_guild or "?",
                    verdict="FAILED:exception",
                    quality=None,
                    cost=0.0,
                    duration=(ended_at - started_at).total_seconds(),
                    saturated=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            console.print(f"  → [bold red]ERROR[/bold red] {type(exc).__name__}: {exc}")

    budget_end = budget.remaining_today()
    return history, stop_reason, budget_start, budget_end


@app.command()
def run(
    queue: Path = typer.Option(
        ..., "--queue", "-q", help="Fichier YAML décrivant la queue de missions"
    ),
    max_missions: int = typer.Option(
        0, "--max-missions", "-n", help="Limite N missions (0 = pas de limite)"
    ),
    budget_floor: float = typer.Option(
        DEFAULTS["budget_floor_usd"], "--budget-floor", help="Stop si budget restant < ce seuil USD"
    ),
    min_quality: float = typer.Option(
        DEFAULTS["min_moving_quality"],
        "--min-quality",
        help="Stop si moving avg quality des N dernières missions < ce seuil",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse la queue, n'exécute pas"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Chemin du rapport markdown (défaut auto)"
    ),
) -> None:
    s = get_settings()
    setup_logging(level=s.log_level, fmt=s.log_format)

    if not queue.exists():
        console.print(f"[red]Queue introuvable : {queue}[/red]")
        raise SystemExit(1)

    try:
        items = parse_queue(queue.read_text(encoding="utf-8"))
    except (ValueError, yaml.YAMLError) as exc:
        console.print(f"[red]Queue invalide : {exc}[/red]")
        raise SystemExit(2) from exc

    console.print(
        Panel.fit(
            f"[bold cyan]Queue chargée :[/bold cyan] {len(items)} missions\n"
            f"[dim]Fichier : {queue}[/dim]",
            border_style="cyan",
        )
    )
    preview = Table(show_header=True, header_style="bold")
    preview.add_column("#", style="dim", width=3)
    preview.add_column("Titre", style="white")
    preview.add_column("Guilde forcée", style="magenta")
    for i, it in enumerate(items, 1):
        preview.add_row(str(i), it.title[:60], it.force_guild or "auto")
    console.print(preview)

    if dry_run:
        console.print("\n[yellow]Dry-run : queue parsée, aucune exécution.[/yellow]")
        raise SystemExit(0)

    cfg = {**DEFAULTS, "budget_floor_usd": budget_floor, "min_moving_quality": min_quality}

    started = datetime.now(UTC)
    history, stop_reason, b_start, b_end = asyncio.run(
        run_autonomous(items, cfg, max_missions=(max_missions if max_missions > 0 else None))
    )
    ended = datetime.now(UTC)

    report = render_report(started, ended, history, stop_reason, b_start, b_end)
    out_dir = s.project_root / "data" / "autonomous_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = output or out_dir / f"{started.strftime('%Y%m%dT%H%M%S')}.md"
    out_path.write_text(report, encoding="utf-8")

    console.print("\n" + report)
    console.print(f"\n[bold green]Rapport écrit :[/bold green] {out_path}")

    # exit code : 0 si stop = queue épuisée, 3 si garde-fou déclenché
    raise SystemExit(0 if stop_reason == "queue épuisée" else 3)


if __name__ == "__main__":
    app()
