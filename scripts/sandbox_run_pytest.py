"""sandbox_run_pytest — exécute pytest sur un sous-arbre du projet dans le sandbox Docker.

Usage:
    uv run python scripts/sandbox_run_pytest.py <fichiers_à_tester>...

Exemple:
    uv run python scripts/sandbox_run_pytest.py src/api/version.py tests/test_version.py

Le script copie les fichiers demandés dans un workspace temporaire isolé, puis
lance le sandbox Docker (image iaa-sandbox) qui exécute pytest. Aucune autre
partie du projet n'est exposée — pas d'accès à .env, data/, .venv, etc.

Démontre la chaîne complète Phase 3 :
  workspace minimal → sandbox isolé (no-net, non-root, mem limit) → pytest
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import typer
from rich.console import Console
from rich.panel import Panel

from src.core.config import get_settings
from src.sandbox.runner import SandboxRunner, SandboxUnavailable

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.command()
def run(
    files: list[Path] = typer.Argument(..., help="Fichiers du projet à inclure dans le workspace"),
    timeout: int = typer.Option(60, "--timeout", help="Timeout en secondes"),
    image: str = typer.Option("iaa-sandbox:latest", "--image"),
) -> None:
    settings = get_settings()
    project_root = settings.project_root.resolve()

    # Validation : tous les fichiers doivent exister et être dans le project_root
    resolved_files: list[tuple[Path, Path]] = []
    for f in files:
        abs_path = (project_root / f).resolve() if not f.is_absolute() else f.resolve()
        if not abs_path.exists():
            console.print(f"[red]Fichier introuvable : {f}[/red]")
            raise SystemExit(1)
        try:
            rel = abs_path.relative_to(project_root)
        except ValueError:
            console.print(f"[red]Fichier hors du project root : {f}[/red]")
            raise SystemExit(1)
        resolved_files.append((abs_path, rel))

    try:
        runner = SandboxRunner(image=image, timeout_seconds=timeout)
    except SandboxUnavailable as exc:
        console.print(f"[red]Sandbox indisponible : {exc}[/red]")
        raise SystemExit(2)

    if not runner.image_exists():
        console.print(
            f"[red]Image {image} absente. Build via :[/red]\n"
            f"  uv run python scripts/check_sandbox.py --build"
        )
        raise SystemExit(2)

    # Préparer workspace temporaire
    with tempfile.TemporaryDirectory() as td:
        workspace = Path(td)
        for src, rel in resolved_files:
            dst = workspace / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        # Ensure pytest can import from src/ (add empty conftest if needed)
        conftest = workspace / "conftest.py"
        if not conftest.exists():
            conftest.write_text(
                "import sys\nfrom pathlib import Path\n"
                "sys.path.insert(0, str(Path(__file__).parent))\n",
                encoding="utf-8",
            )

        console.print(
            Panel.fit(
                f"[bold cyan]Sandbox pytest[/bold cyan]\n"
                f"Image : {image}\n"
                f"Fichiers : {len(resolved_files)}\n"
                f"Workspace temp : {workspace}",
                border_style="cyan",
            )
        )

        result = runner.run(workspace=workspace, command=["pytest", "-v", "--tb=short"])

    console.print("\n[bold cyan]STDOUT[/bold cyan]")
    console.print(result.stdout or "[dim](vide)[/dim]")

    if result.stderr:
        console.print("\n[bold yellow]STDERR[/bold yellow]")
        console.print(result.stderr)

    color = "green" if result.exit_code == 0 else "red"
    console.print(
        f"\n[bold {color}]exit_code={result.exit_code}[/bold {color}] · "
        f"{result.duration_seconds:.2f}s · timed_out={result.timed_out}"
    )
    raise SystemExit(0 if result.exit_code == 0 else 1)


if __name__ == "__main__":
    app()
