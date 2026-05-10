"""health_check — diagnostic global de l'environnement IA-Expert-Army.

En une commande, vérifie que toutes les couches sont opérationnelles :
- Couche 1/2 : Settings + clé API Anthropic + 4 guildes importables
- Couche 3 : FileMemory accessible + Chroma fonctionnel + Sandbox Docker
- Couche 4 : SkillsLibrary + PatternMiner whitelist complet
- Garde-fous : BudgetController + Killswitch
- Observabilité : Langfuse joignable + tracing détecté

Usage:
    uv run python scripts/health_check.py
    uv run python scripts/health_check.py --quick  # skip les checks Docker (rapide)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(no_args_is_help=False, add_completion=False)


def _ok(detail: str = "") -> tuple[str, str]:
    return "[green]OK[/green]", detail


def _warn(detail: str) -> tuple[str, str]:
    return "[yellow]WARN[/yellow]", detail


def _fail(detail: str) -> tuple[str, str]:
    return "[red]FAIL[/red]", detail


def _skipped(detail: str = "") -> tuple[str, str]:
    return "[dim]SKIP[/dim]", detail


def _safe(fn: Callable[[], tuple[str, str]]) -> tuple[str, str]:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return _fail(f"{type(exc).__name__}: {exc}")


# ===== Checks =====


def check_python() -> tuple[str, str]:
    v = sys.version_info
    if v >= (3, 12):
        return _ok(f"{v.major}.{v.minor}.{v.micro}")
    return _fail(f"Python {v.major}.{v.minor} (3.12+ requis)")


def check_settings() -> tuple[str, str]:
    from src.core.config import get_settings

    s = get_settings()
    key = s.anthropic_api_key.get_secret_value()
    if not key.startswith("sk-ant-"):
        return _fail("ANTHROPIC_API_KEY absent ou invalide dans .env")
    return _ok(
        f"Opus={s.model_strategic} · Sonnet={s.model_operational} · Haiku={s.model_bulk}"
    )


def check_file_memory() -> tuple[str, str]:
    from src.core.config import get_settings
    from src.memory.file_memory import FileMemory

    s = get_settings()
    mem = FileMemory(s.project_root / "data" / "memory")
    n_missions = len(mem.list_missions())
    n_episodes = len(mem.list_episodes())
    return _ok(f"{n_missions} missions · {n_episodes} épisodes archivés")


def check_vector_memory() -> tuple[str, str]:
    from src.core.config import get_settings
    from src.memory.vector_memory import VectorMemory

    s = get_settings()
    vmem = VectorMemory(persist_dir=s.chroma_persist_dir)
    n = vmem.count()
    return _ok(f"{n} épisodes indexés (Chroma in-process)")


def check_skills_library() -> tuple[str, str]:
    from src.core.config import get_settings
    from src.learning.skills_library import SkillsLibrary

    s = get_settings()
    lib = SkillsLibrary(s.project_root / "skills")
    total = lib.count()
    return _ok(f"{total} skills auto-générées au total")


def check_pattern_miner_whitelist() -> tuple[str, str]:
    from src.learning.pattern_miner import PatternMiner

    expected_per_guild = {
        "Engineering": ("software_architect", "backend_developer", "code_reviewer"),
        "Research": ("research_lead", "tech_watch", "document_synthesizer", "research_reviewer"),
        "Creative": ("content_strategist", "copywriter", "editor"),
        "Business": ("project_manager", "business_analyst", "legal_reviewer"),
    }
    missing = []
    for guild, agents in expected_per_guild.items():
        for agent in agents:
            if agent not in PatternMiner.AGENT_WHITELIST:
                missing.append(f"{guild}/{agent}")
    if missing:
        return _fail(f"Agents absents du whitelist : {missing}")
    return _ok(f"{len(PatternMiner.AGENT_WHITELIST)} agents whitelistés (4 guildes complètes)")


def check_workflows_importable() -> tuple[str, str]:
    """Vérifie que les 4 workflows sont importables sans erreur."""
    from src.guilds.business.workflow import BusinessWorkflow  # noqa: F401
    from src.guilds.creative.workflow import CreativeWorkflow  # noqa: F401
    from src.guilds.research.workflow import ResearchWorkflow  # noqa: F401
    from src.orchestrator.workflow import Workflow  # noqa: F401

    return _ok("Engineering + Research + Creative + Business")


def check_router() -> tuple[str, str]:
    from src.orchestrator.router import HeuristicGuildClassifier

    clf = HeuristicGuildClassifier()
    # Smoke test : 4 missions canon doivent router correctement
    cases = {
        "engineering": clf.classify("Endpoint /health", "Crée FastAPI"),
        "research": clf.classify("Synthétise les patterns", "Compare X et Y"),
        "creative": clf.classify("Rédige une landing page", "Pour le SaaS"),
        "business": clf.classify("Roadmap projet open-source", "Plan jalons et viabilité"),
    }
    failures = [g for g, actual in cases.items() if actual != g]
    if failures:
        return _fail(f"Classifier échoue pour : {failures}")
    return _ok("4 routages canon OK")


def check_budget() -> tuple[str, str]:
    from src.core.budget import BudgetController
    from src.core.config import get_settings

    s = get_settings()
    bc = BudgetController(
        state_path=s.project_root / "data" / "budget_state.json",
        daily_budget_usd=s.daily_budget_usd,
    )
    st = bc.status()
    pct = st["percent_used"]
    detail = f"${st['spent_usd']:.4f} / ${st['daily_budget_usd']:.2f} ({pct:.1f}%)"
    if pct >= 100:
        return _warn(f"Budget atteint — {detail}")
    if pct >= 80:
        return _warn(f"Budget > 80% — {detail}")
    return _ok(detail)


def check_killswitch() -> tuple[str, str]:
    from src.core.config import get_settings
    from src.core.killswitch import Killswitch

    s = get_settings()
    ks = Killswitch(s.project_root / "data" / ".killswitch")
    if ks.is_engaged():
        return _warn(f"Killswitch ENGAGÉ ({ks.path})")
    return _ok("libre")


def check_tracing() -> tuple[str, str]:
    from src.core import tracing
    from src.core.config import get_settings

    s = get_settings()
    pk = s.langfuse_public_key
    sk = s.langfuse_secret_key.get_secret_value()
    if not pk or not sk:
        return _skipped("LANGFUSE_PUBLIC_KEY/SECRET_KEY absents — tracing en NO-OP")
    tracing.reset_for_tests()
    enabled = tracing.init_tracing()
    if enabled:
        return _ok(f"Langfuse actif → {s.langfuse_host}")
    return _warn("Credentials présents mais init Langfuse a échoué")


def check_docker() -> tuple[str, str]:
    try:
        import docker  # type: ignore[import]
    except ImportError:
        return _fail("docker SDK Python absent")
    try:
        client = docker.from_env()
        client.ping()
        version = client.version()
        return _ok(f"Docker {version.get('Version', '?')} joignable")
    except Exception as exc:  # noqa: BLE001
        return _fail(f"Docker daemon down : {exc}")


def check_sandbox_image() -> tuple[str, str]:
    try:
        import docker  # type: ignore[import]
        from docker.errors import ImageNotFound  # type: ignore[import]
    except ImportError:
        return _fail("docker SDK Python absent")
    try:
        client = docker.from_env()
        client.ping()
    except Exception:  # noqa: BLE001
        return _skipped("Docker down — vérifié plus haut")
    try:
        client.images.get("iaa-sandbox:latest")
        return _ok("iaa-sandbox:latest présente")
    except ImageNotFound:
        return _warn("Image absente — build via : check_sandbox.py --build")


def check_langfuse_http() -> tuple[str, str]:
    """Tente une requête HTTP sur localhost:3000 (Langfuse self-hosted)."""
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.Request("http://localhost:3000")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return _ok(f"HTTP {resp.status} sur :3000")
    except urllib.error.URLError:
        return _skipped("Langfuse pas démarré (docker compose --profile observability up -d)")
    except Exception as exc:  # noqa: BLE001
        return _warn(f"{type(exc).__name__}: {exc}")


# ===== Main CLI =====


@app.command()
def check(
    quick: bool = typer.Option(False, "--quick", help="Skip les checks Docker (rapide)"),
) -> None:
    table = Table(title="IA-Expert-Army — Health Check Global", show_lines=True)
    table.add_column("Couche", style="cyan", width=14)
    table.add_column("Composant", style="white", width=28)
    table.add_column("Statut", justify="center", width=8)
    table.add_column("Détail", style="white")

    checks: list[tuple[str, str, Callable[[], tuple[str, str]]]] = [
        ("Setup", "Python 3.12+", check_python),
        ("Setup", "Settings + clé API", check_settings),
        ("Couche 2", "4 workflows importables", check_workflows_importable),
        ("Couche 2", "MissionRouter classifier", check_router),
        ("Couche 3", "FileMemory", check_file_memory),
        ("Couche 3", "VectorMemory (Chroma)", check_vector_memory),
        ("Couche 3", "SkillsLibrary", check_skills_library),
        ("Couche 4", "PatternMiner whitelist", check_pattern_miner_whitelist),
        ("Garde-fou", "BudgetController", check_budget),
        ("Garde-fou", "Killswitch", check_killswitch),
        ("Observabilité", "Tracing Langfuse", check_tracing),
    ]
    if not quick:
        checks.extend(
            [
                ("Sandbox", "Docker daemon", check_docker),
                ("Sandbox", "Image iaa-sandbox", check_sandbox_image),
                ("Observabilité", "Langfuse HTTP :3000", check_langfuse_http),
            ]
        )

    n_ok = n_warn = n_fail = n_skip = 0
    for layer, component, fn in checks:
        status, detail = _safe(fn)
        if "OK" in status:
            n_ok += 1
        elif "WARN" in status:
            n_warn += 1
        elif "FAIL" in status:
            n_fail += 1
        else:
            n_skip += 1
        table.add_row(layer, component, status, detail)

    console.print(table)
    summary = (
        f"[green]{n_ok} OK[/green] · "
        f"[yellow]{n_warn} WARN[/yellow] · "
        f"[red]{n_fail} FAIL[/red] · "
        f"[dim]{n_skip} SKIP[/dim]"
    )
    console.print(f"\n{summary}")
    if n_fail:
        console.print("\n[bold red]Health check : KO[/bold red]")
        raise SystemExit(1)
    if n_warn:
        console.print("\n[bold yellow]Health check : OK avec warnings[/bold yellow]")
        raise SystemExit(0)
    console.print("\n[bold green]Health check : tout vert[/bold green]")
    raise SystemExit(0)


if __name__ == "__main__":
    app()
