"""Check Setup — Vérifie que l'environnement IA-Expert-Army est prêt.

Contrôles :
- Python 3.12+
- Dépendances Phase 0 importables
- Fichier .env présent et valide
- Clé API Anthropic présente (sans la valider auprès du serveur)
- Dossiers data/ accessibles en écriture

Usage:
    uv run python scripts/check_setup.py
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rich.console import Console
from rich.table import Table

console = Console()


def _check(label: str, fn) -> tuple[bool, str]:
    try:
        ok, detail = fn()
        return ok, detail
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def check_python() -> tuple[bool, str]:
    v = sys.version_info
    ok = v >= (3, 12)
    return ok, f"{v.major}.{v.minor}.{v.micro}"


def check_imports() -> tuple[bool, str]:
    pkgs = ["anthropic", "pydantic", "pydantic_settings", "structlog", "rich", "httpx", "typer"]
    missing = []
    for p in pkgs:
        try:
            importlib.import_module(p)
        except ImportError:
            missing.append(p)
    if missing:
        return False, f"Manquants : {', '.join(missing)}"
    return True, f"{len(pkgs)} paquets OK"


def check_env_file() -> tuple[bool, str]:
    root = Path(__file__).resolve().parents[1]
    env = root / ".env"
    if not env.exists():
        return False, ".env absent (copier depuis .env.example)"
    return True, str(env)


def check_settings() -> tuple[bool, str]:
    from src.core.config import get_settings

    s = get_settings()
    key = s.anthropic_api_key.get_secret_value()
    if not key or not key.startswith("sk-ant-"):
        return False, "ANTHROPIC_API_KEY manquante ou invalide"
    return True, f"clé OK (modèle stratégique : {s.model_strategic})"


def check_data_dirs() -> tuple[bool, str]:
    root = Path(__file__).resolve().parents[1]
    dirs = [root / "data", root / "data" / "chroma", root / "data" / "episodes"]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        test = d / ".write_test"
        test.write_text("ok")
        test.unlink()
    return True, f"{len(dirs)} dossiers OK"


def main() -> int:
    table = Table(title="IA-Expert-Army — Vérification de l'environnement", show_lines=True)
    table.add_column("Contrôle", style="cyan")
    table.add_column("Statut", style="white", justify="center")
    table.add_column("Détail", style="white")

    checks = [
        ("Python 3.12+", check_python),
        ("Dépendances Phase 0", check_imports),
        ("Fichier .env", check_env_file),
        ("Settings & clé API", check_settings),
        ("Dossiers data/", check_data_dirs),
    ]

    all_ok = True
    for label, fn in checks:
        ok, detail = _check(label, fn)
        if not ok:
            all_ok = False
        table.add_row(label, "[green]OK[/green]" if ok else "[red]FAIL[/red]", detail)

    console.print(table)

    if all_ok:
        console.print("\n[bold green]Environnement prêt. Lance `uv run python scripts/hello_agent.py`.[/bold green]\n")
        return 0
    console.print("\n[bold red]Setup incomplet. Corrige les erreurs ci-dessus.[/bold red]\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
