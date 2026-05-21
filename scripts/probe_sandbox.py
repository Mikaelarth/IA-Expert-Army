"""probe_sandbox — Validation directe du SandboxRunner sur du code existant.

Session 6 : sans avoir à re-lancer une mission Qwen complète (20-30 min),
on valide le critère #5 du contrat ("Sécurité par défaut") en montrant
que la chaîne sandbox Docker fonctionne end-to-end sur un input contrôlé.

Le script :
1. Vérifie que Docker est joignable + image `iaa-sandbox:latest` présente.
2. Prend le code+test slugify (existant sur disque, validé Session 4).
3. Le copie dans un workspace temp + lance pytest dans le container
   isolé (network=none, user=nobody, mem 512m, pids 256, timeout 30s).
4. Vérifie que pytest exit code 0.
5. Mesure la durée du build sandbox (vs durée du test isolé).

Usage :
    uv run python scripts/probe_sandbox.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rich.console import Console

from src.tools.sandbox_validate import print_sandbox_result, validate_files_in_sandbox

console = Console()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    src_text = project_root / "src" / "utils" / "text.py"
    test_text = project_root / "tests" / "unit" / "test_text.py"

    if not src_text.exists() or not test_text.exists():
        console.print(
            f"[red]Pré-requis manquants :[/red]\n"
            f"  {src_text} {'OK' if src_text.exists() else 'ABSENT'}\n"
            f"  {test_text} {'OK' if test_text.exists() else 'ABSENT'}"
        )
        return 2

    files = [
        {"path": "src/utils/text.py", "content": _read(src_text)},
        {
            "path": "src/utils/__init__.py",
            "content": '"""Utilitaires généraux (slugify, etc.)."""\n',
        },
        {"path": "src/__init__.py", "content": ""},
        {"path": "tests/__init__.py", "content": ""},
        {"path": "tests/unit/__init__.py", "content": ""},
        {"path": "tests/unit/test_text.py", "content": _read(test_text)},
    ]

    console.print(
        f"[cyan]Probe sandbox sur :[/cyan] {len(files)} fichiers "
        f"(slugify Session 4 + structure de packages minimale)"
    )

    started = time.perf_counter()
    result = validate_files_in_sandbox(
        files=files,
        sandbox_image="iaa-sandbox:latest",
        sandbox_timeout=60,
        console=console,
        enable_sandbox=True,
    )
    total = time.perf_counter() - started

    if result is None:
        console.print(
            "[red]Sandbox indisponible — Docker down OU image absente. "
            "Lance `docker info` et `docker images iaa-sandbox` pour diagnostiquer.[/red]"
        )
        return 3

    print_sandbox_result(result, console)
    console.print(
        f"\n[dim]Wall-clock total (build workspace + run pytest + cleanup) : {total:.2f}s[/dim]"
    )

    if result.exit_code == 0:
        console.print("\n[bold green]✓ Sandbox validation OK[/bold green] — critère #5 démontré.")
        return 0
    console.print(
        f"\n[bold red]✗ pytest a échoué dans le sandbox (exit_code={result.exit_code}, "
        f"timed_out={result.timed_out})[/bold red]"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
