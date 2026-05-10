"""killswitch — engage/release/status le sentinel d'arrêt d'urgence.

Usage:
    uv run python scripts/killswitch.py status
    uv run python scripts/killswitch.py engage --reason "Inspection en cours"
    uv run python scripts/killswitch.py release
"""
from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import typer
from rich.console import Console

from src.core.config import get_settings
from src.core.killswitch import Killswitch

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


def _ks() -> Killswitch:
    s = get_settings()
    return Killswitch(s.project_root / "data" / ".killswitch")


@app.command()
def status() -> None:
    ks = _ks()
    st = ks.status()
    if st["engaged"]:
        console.print(f"[bold red]ENGAGÉ[/bold red] · {st['path']}")
        console.print(st["content"])
    else:
        console.print(f"[bold green]LIBRE[/bold green] · sentinel attendu en {st['path']}")


@app.command()
def engage(
    reason: str = typer.Option("manual", "--reason", "-r", help="Raison courte de l'engagement"),
) -> None:
    ks = _ks()
    if ks.is_engaged():
        console.print("[yellow]Déjà engagé. État inchangé.[/yellow]")
        raise SystemExit(0)
    ks.engage(reason=reason)
    console.print(
        f"[bold red]Killswitch ENGAGÉ.[/bold red] Plus aucune mission ne pourra démarrer.\n"
        f"[dim]Sentinel : {ks.path}[/dim]"
    )


@app.command()
def release() -> None:
    ks = _ks()
    if not ks.is_engaged():
        console.print("[yellow]Pas engagé, rien à faire.[/yellow]")
        raise SystemExit(0)
    ks.release()
    console.print("[bold green]Killswitch LIBÉRÉ.[/bold green] Les missions peuvent reprendre.")


if __name__ == "__main__":
    app()
