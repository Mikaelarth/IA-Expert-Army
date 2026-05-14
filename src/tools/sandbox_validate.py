"""sandbox_validate — helpers partagés pour valider une liste de fichiers
dans le sandbox Docker.

Utilisé par :
- scripts/apply_mission.py --validate / --validate-only (mission archivée)
- scripts/run_mission.py --apply --validate (boucle fermée live)

Le helper encapsule : préparation workspace temp + auto-conftest + lancement
sandbox + cleanup. Renvoie None si le sandbox est indisponible (Docker down
ou image absente) — au caller de décider quoi faire.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterable
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from src.sandbox.runner import SandboxResult, SandboxRunner, SandboxUnavailable


def validate_files_in_sandbox(
    files: Iterable[dict[str, str]],
    sandbox_image: str = "iaa-sandbox:latest",
    sandbox_timeout: int = 60,
    console: Console | None = None,
    enable_sandbox: bool | None = None,
) -> SandboxResult | None:
    """Lance pytest dans le sandbox sur la liste de fichiers donnée.

    - `files` : liste de dicts au format Developer agent ({path, content, language?}).
      Les entrées sans path (ou avec path vide) sont silencieusement ignorées.
    - Si l'utilisateur fournit son propre `conftest.py` dans la liste, il est
      préservé. Sinon, un conftest minimal est créé pour permettre les imports
      `from src.x import y` sans installation package.
    - Renvoie None si Docker est indisponible, l'image absente, ou si
      `enable_sandbox=False` (kill-switch GGG.1).
    - Si `enable_sandbox` est None (défaut), lit `Settings.enable_sandbox`.
    - Le workspace temp est nettoyé automatiquement après le run.
    """
    cons = console or Console()

    # Sprint GGG.1 : kill-switch explicite (utile sur VPS sans Docker).
    if enable_sandbox is None:
        from src.core.config import get_settings

        enable_sandbox = get_settings().enable_sandbox
    if not enable_sandbox:
        cons.print(
            "[yellow]Sandbox désactivé (Settings.enable_sandbox=False) — "
            "validation skippée.[/yellow]"
        )
        return None

    try:
        runner = SandboxRunner(image=sandbox_image, timeout_seconds=sandbox_timeout)
    except SandboxUnavailable as exc:
        cons.print(f"[yellow]Sandbox indisponible — validation skippée : {exc}[/yellow]")
        return None
    if not runner.image_exists():
        cons.print(
            f"[yellow]Image {sandbox_image} absente — validation skippée. "
            f"Build via : uv run python scripts/check_sandbox.py --build[/yellow]"
        )
        return None

    with tempfile.TemporaryDirectory() as td:
        workspace = Path(td)
        for entry in files:
            rel = (entry.get("path") or "").strip()
            if not rel:
                continue
            content = entry.get("content", "")
            dst = workspace / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(content, encoding="utf-8")

        # Conftest minimal pour permettre `from src.x import y` sans installation
        # package. Préserve un éventuel conftest fourni par l'utilisateur.
        conftest = workspace / "conftest.py"
        if not conftest.exists():
            conftest.write_text(
                "import sys\nfrom pathlib import Path\n"
                "sys.path.insert(0, str(Path(__file__).parent))\n",
                encoding="utf-8",
            )
        return runner.run(workspace=workspace, command=["pytest", "-v", "--tb=short"])


def print_sandbox_result(result: SandboxResult, console: Console | None = None) -> None:
    """Rend un SandboxResult lisiblement : Panel coloré + stdout/stderr tronqués."""
    cons = console or Console()
    color = "green" if result.exit_code == 0 else "red"
    cons.print(
        Panel.fit(
            f"[bold {color}]pytest exit_code={result.exit_code}[/bold {color}] · "
            f"{result.duration_seconds:.2f}s · timed_out={result.timed_out}",
            border_style=color,
            title="Sandbox validation",
        )
    )
    if result.stdout:
        cons.print("\n[bold cyan]STDOUT[/bold cyan]")
        # Tronque à 80 dernières lignes pour rester lisible sur les longs runs.
        for line in result.stdout.split("\n")[-80:]:
            cons.print(line)
    if result.stderr.strip():
        cons.print("\n[bold yellow]STDERR[/bold yellow]")
        cons.print(result.stderr[-2000:])
