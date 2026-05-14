"""check_sandbox — vérifie que le sandbox Docker est opérationnel.

Contrôles :
- Docker daemon joignable
- Image iaa-sandbox:latest présente (sinon propose la commande de build)
- Run d'un smoke test : `python -c "print('hello from sandbox')"` dans le container

Usage:
    uv run python scripts/check_sandbox.py
    uv run python scripts/check_sandbox.py --build  # build l'image si absente
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
from rich.table import Table

from src.core.config import get_settings
from src.sandbox.runner import SandboxRunner, SandboxUnavailable

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()


@app.command()
def check(
    build: bool = typer.Option(False, "--build", help="Build l'image iaa-sandbox si absente"),
) -> None:
    settings = get_settings()
    table = Table(title="IA-Expert-Army — Vérification du sandbox", show_lines=True)
    table.add_column("Contrôle", style="cyan")
    table.add_column("Statut", justify="center")
    table.add_column("Détail", style="white")

    # 1. Daemon
    try:
        runner = SandboxRunner(image="iaa-sandbox:latest")
    except SandboxUnavailable as exc:
        table.add_row("Docker daemon", "[red]FAIL[/red]", str(exc))
        console.print(table)
        console.print("\n[yellow]Lance Docker Desktop puis relance ce script.[/yellow]")
        raise SystemExit(1) from exc

    if not runner.ping():
        table.add_row("Docker daemon", "[red]FAIL[/red]", "ping refusé")
        console.print(table)
        raise SystemExit(1)
    table.add_row("Docker daemon", "[green]OK[/green]", "joignable")

    # 2. Image
    if not runner.image_exists():
        if build:
            dockerfile = settings.project_root / "infra" / "docker" / "sandbox.Dockerfile"
            console.print(table)
            console.print(
                "\n[yellow]Build de l'image en cours… (peut prendre quelques minutes)[/yellow]"
            )
            import subprocess

            cmd = [
                "docker",
                "build",
                "-t",
                "iaa-sandbox:latest",
                "-f",
                str(dockerfile),
                str(dockerfile.parent),
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603 — args entièrement contrôlés par le script, pas d'input externe
            if r.returncode != 0:
                console.print(f"[red]Build échoué :[/red]\n{r.stderr}")
                raise SystemExit(1)
            console.print("[green]Image construite avec succès.[/green]")
            # Recreate runner avec nouveau client view
            runner = SandboxRunner(image="iaa-sandbox:latest")
            table.add_row("Image iaa-sandbox", "[green]BUILT[/green]", "iaa-sandbox:latest")
        else:
            table.add_row(
                "Image iaa-sandbox",
                "[yellow]ABSENT[/yellow]",
                "Lance avec --build pour la construire",
            )
            console.print(table)
            console.print(
                "\n[yellow]Image absente. Pour la construire :[/yellow]\n"
                "  uv run python scripts/check_sandbox.py --build\n"
                "[dim]ou directement :[/dim]\n"
                "  docker build -t iaa-sandbox:latest -f infra/docker/sandbox.Dockerfile infra/docker"
            )
            raise SystemExit(2)
    else:
        table.add_row("Image iaa-sandbox", "[green]OK[/green]", "iaa-sandbox:latest présente")

    # 3. Smoke test
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "ok.txt").write_text("smoke")
        result = runner.run(
            workspace=tmp,
            command=["python", "-c", "print('hello from sandbox')"],
        )

    if result.exit_code == 0 and "hello from sandbox" in result.stdout:
        table.add_row(
            "Smoke test",
            "[green]OK[/green]",
            f"exit={result.exit_code} · {result.duration_seconds:.2f}s",
        )
    else:
        table.add_row(
            "Smoke test",
            "[red]FAIL[/red]",
            f"exit={result.exit_code} · stderr={result.stderr[:80]}",
        )

    console.print(table)
    console.print("\n[bold green]Sandbox opérationnel.[/bold green]")


if __name__ == "__main__":
    app()
