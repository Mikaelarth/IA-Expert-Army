"""health_check — diagnostic global de l'environnement IA-Expert-Army.

En une commande, vérifie que toutes les couches sont opérationnelles :
- Couche 1/2 : Settings + daemon Ollama joignable + 4 guildes importables
- Couche 3 : FileMemory accessible + Chroma fonctionnel + Sandbox Docker
- Couche 4 : SkillsLibrary + PatternMiner whitelist complet
- Garde-fous : BudgetController + Killswitch
- Observabilité : Langfuse joignable + tracing détecté

Bascule v0.4.0 (ADR-025) : le backend LLM est Ollama local — le check
vérifie que le daemon répond et que les 3 modèles configurés sont pullés.

# audit: ignore FILE_TOO_LONG -- ~510 lignes acceptées : 18 checks indépendants
# regroupés dans un seul script CLI pour un usage `just health-quick`. Split
# par couche fragmenterait l'output utilisateur (tableau unique avec 18 lignes)
# sans gain de lisibilité.

Usage:
    uv run python scripts/health_check.py
    uv run python scripts/health_check.py --quick  # skip les checks Docker (rapide)
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

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
    except Exception as exc:
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
    if not s.ollama_base_url:
        return _fail("OLLAMA_BASE_URL absent dans .env")
    return _ok(
        f"strategic={s.model_strategic} · operational={s.model_operational} · bulk={s.model_bulk}"
    )


def check_ollama_daemon() -> tuple[str, str]:
    """Pingue le daemon Ollama et vérifie que les 3 modèles configurés sont pullés.

    Endpoint natif `/api/tags` (pas /v1/...) — c'est la route Ollama-spécifique
    qui liste les modèles locaux. Si le daemon n'est pas démarré, return FAIL
    avec instruction.
    """
    import json
    import urllib.error
    import urllib.request

    from src.core.config import get_settings

    s = get_settings()
    # Dérive l'URL native depuis ollama_base_url : retire /v1 et ajoute /api/tags
    api_base = s.ollama_base_url.rstrip("/").removesuffix("/v1")
    tags_url = f"{api_base}/api/tags"

    try:
        req = urllib.request.Request(tags_url)  # noqa: S310 — localhost Ollama (cf. ligne suivante)
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 — localhost Ollama
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return _fail(
            f"Daemon Ollama injoignable à {api_base} ({exc.reason if hasattr(exc, 'reason') else exc}). "
            "Lance `ollama serve` ou installe https://ollama.com"
        )
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")

    installed = {m["name"] for m in payload.get("models", []) if isinstance(m, dict)}
    expected = {s.model_strategic, s.model_operational, s.model_bulk}
    missing = expected - installed
    if missing:
        return _warn(
            f"Daemon OK ({len(installed)} modèles) mais manquants : "
            f"{sorted(missing)} — `ollama pull <nom>`"
        )
    return _ok(f"daemon OK · 3 modèles configurés pullés · {len(installed)} dispos au total")


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
    sk = s.langfuse_secret_key
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
    except Exception as exc:
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
    except Exception:
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
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 — localhost-only Langfuse health
            return _ok(f"HTTP {resp.status} sur :3000")
    except urllib.error.URLError:
        return _skipped("Langfuse pas démarré (docker compose --profile observability up -d)")
    except Exception as exc:
        return _warn(f"{type(exc).__name__}: {exc}")


# ===== Sprint NNN — checks des briques récentes =====


def check_notifier_config() -> tuple[str, str]:
    """Sprint HHH : webhook notifications. Vérifie la config sans envoyer."""
    from src.core.notifier import get_notifier_from_settings

    notifier = get_notifier_from_settings()
    if not notifier.is_enabled:
        return _skipped("NOTIFY_WEBHOOK_URL absent dans .env (notifier en NO-OP)")
    return _ok(f"backend détecté : {notifier.backend} (URL : {notifier.webhook_url[:40]}…)")


def check_notifier_send_test() -> tuple[str, str]:
    """Sprint NNN : envoie une notification de test. Utile pour valider que
    le webhook configuré dans .env fonctionne réellement (pas juste la config).
    Activé via `--full` ou `--notify-test`."""
    from src.core.notifier import NotifyLevel, get_notifier_from_settings

    notifier = get_notifier_from_settings()
    if not notifier.is_enabled:
        return _skipped("NOTIFY_WEBHOOK_URL absent — pas d'envoi possible")
    sent = notifier.send(
        NotifyLevel.INFO,
        "IA-Expert-Army — Health check",
        "Test d'envoi depuis `health_check.py --notify-test`. "
        "Si tu vois ce message, le webhook fonctionne.",
    )
    if sent:
        return _ok(f"Notification envoyée via {notifier.backend} (vérifie ton mobile)")
    return _fail("Envoi échoué — cf. logs (URL invalide ou réseau down)")


def check_vps_config() -> tuple[str, str]:
    """Sprint GGG : affiche le profil VPS détecté + état sandbox kill-switch."""
    from src.core.config import get_settings

    s = get_settings()
    profile = s.vps_profile or "auto/inconnu"
    sandbox_state = "ON" if s.enable_sandbox else "OFF (skip silencieux)"
    return _ok(f"profile={profile} · enable_sandbox={sandbox_state}")


def check_deploy_scripts() -> tuple[str, str]:
    """Sprint GGG : les 2 scripts shell de déploiement existent + syntaxe valide."""
    import shutil
    import subprocess

    project_root = Path(__file__).resolve().parents[1]
    scripts = [
        project_root / "scripts" / "deploy_vps.sh",
        project_root / "scripts" / "migrate_vps.sh",
    ]
    missing = [s.name for s in scripts if not s.exists()]
    if missing:
        return _fail(f"Scripts manquants : {missing}")

    # Syntaxe bash si bash disponible — sur Windows pur sans Git Bash, on skip
    bash = shutil.which("bash")
    if bash is None:
        return _warn("Scripts présents mais bash absent — syntaxe non vérifiée")

    for script in scripts:
        try:
            result = subprocess.run(  # noqa: S603 — args contrôlés (paths du repo)
                [bash, "-n", str(script)],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return _warn(
                f"bash trouvé mais inexécutable ({type(exc).__name__}) — syntaxe non vérifiée"
            )
        if result.returncode != 0:
            stderr = result.stderr.lower()
            # Cas WSL Windows sans distribution installée : bash.EXE existe dans
            # system32 mais le relai échoue. On le distingue d'une vraie erreur
            # de syntaxe (WARN au lieu de FAIL — c'est un manque d'environnement,
            # pas un bug du script).
            if (
                "wsl" in stderr
                or "createprocesscommon" in stderr
                or "no such file or directory" in stderr
            ):
                return _warn(
                    f"bash trouvé mais relai WSL/exécution indisponible — syntaxe non vérifiée ({script.name})"
                )
            return _fail(f"{script.name} : syntaxe invalide ({result.stderr[:100]})")
    return _ok(f"{len(scripts)} scripts syntaxe OK (deploy + migrate)")


def check_coverage_config() -> tuple[str, str]:
    """Sprint KKK : vérifie que la config coverage gate (fail_under) est présente
    dans pyproject.toml. Garantit que personne ne l'a supprimé silencieusement."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    if "fail_under" not in text:
        return _fail("[tool.coverage.report] fail_under absent — politique JJJ/KKK perdue !")
    # Extraction simple de la valeur
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("fail_under"):
            value = line.split("=")[1].strip()
            return _ok(f"fail_under={value} dans pyproject.toml (CI gate actif)")
    return _warn("fail_under présent mais format inattendu")


def check_adrs_index() -> tuple[str, str]:
    """Sprint NNN : compte les ADRs indexés dans docs/adr/README.md vs présents
    sur le disque. Détecte les ADRs non-indexés (oublis)."""
    adr_dir = Path(__file__).resolve().parents[1] / "docs" / "adr"
    index = adr_dir / "README.md"
    if not index.exists():
        return _warn("docs/adr/README.md absent")
    index_content = index.read_text(encoding="utf-8")
    # Compte les fichiers ADR sur disque (NNN-*.md)
    on_disk = sorted(f.name for f in adr_dir.glob("[0-9][0-9][0-9]-*.md") if f.name != "README.md")
    not_indexed = [name for name in on_disk if name not in index_content]
    if not_indexed:
        return _warn(f"{len(not_indexed)} ADR(s) non indexé(s) : {not_indexed[:3]}")
    return _ok(f"{len(on_disk)} ADRs indexés (cohérent disque ↔ index)")


# ===== Main CLI =====


@app.command()
def check(
    quick: bool = typer.Option(False, "--quick", help="Skip les checks Docker (rapide)"),
    full: bool = typer.Option(
        False,
        "--full",
        help="Sprint NNN : active aussi les checks externes (envoi notification de test)",
    ),
    notify_test: bool = typer.Option(
        False,
        "--notify-test",
        help="Sprint NNN : envoie une notification de test si webhook configuré",
    ),
) -> None:
    table = Table(title="IA-Expert-Army — Health Check Global", show_lines=True)
    table.add_column("Couche", style="cyan", width=14)
    table.add_column("Composant", style="white", width=28)
    table.add_column("Statut", justify="center", width=8)
    table.add_column("Détail", style="white")

    checks: list[tuple[str, str, Callable[[], tuple[str, str]]]] = [
        ("Setup", "Python 3.12+", check_python),
        ("Setup", "Settings + modèles configurés", check_settings),
        # Sprint NNN : checks de config rapides toujours actifs
        ("Setup", "VPS profile + sandbox", check_vps_config),
        ("Setup", "Coverage gate config", check_coverage_config),
        ("Couche 2", "4 workflows importables", check_workflows_importable),
        ("Couche 2", "MissionRouter classifier", check_router),
        ("Couche 3", "FileMemory", check_file_memory),
        ("Couche 3", "VectorMemory (Chroma)", check_vector_memory),
        ("Couche 3", "SkillsLibrary", check_skills_library),
        ("Couche 4", "PatternMiner whitelist", check_pattern_miner_whitelist),
        ("Garde-fou", "BudgetController", check_budget),
        ("Garde-fou", "Killswitch", check_killswitch),
        # Sprint NNN : nouveaux composants Sprint EEE→KKK
        ("Notification", "Notifier config", check_notifier_config),
        ("Déploiement", "Scripts deploy/migrate VPS", check_deploy_scripts),
        ("Documentation", "ADRs index cohérent", check_adrs_index),
        ("Observabilité", "Tracing Langfuse", check_tracing),
    ]
    # Le check Ollama appelle un daemon localhost externe (cf. ADR-025).
    # Comme Docker, c'est un pré-requis runtime qu'on saute en mode --quick
    # (utilisé en CI sur des runners qui n'ont pas Ollama installé). En
    # mode normal il reste actif pour le diagnostic local.
    if not quick:
        checks.extend(
            [
                ("Setup", "Ollama daemon + modèles pullés", check_ollama_daemon),
                ("Sandbox", "Docker daemon", check_docker),
                ("Sandbox", "Image iaa-sandbox", check_sandbox_image),
                ("Observabilité", "Langfuse HTTP :3000", check_langfuse_http),
            ]
        )

    # Sprint NNN : --full ou --notify-test active les checks coûteux
    # (envoi réseau, etc.)
    if full or notify_test:
        checks.append(
            ("Notification", "Webhook envoi test", check_notifier_send_test),
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
