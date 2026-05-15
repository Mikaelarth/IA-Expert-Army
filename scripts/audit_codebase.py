"""audit_codebase — détecte les anti-patterns spécifiques à IA-Expert-Army.

Sprint LLL — garde-fou défensif contre la dérive architecturale (humaine ou
introduite par un agent IA qui code sans connaître la politique du repo).

Usage :
    uv run python scripts/audit_codebase.py                     # rapport complet
    uv run python scripts/audit_codebase.py --rule FILE_TOO_LONG  # filtre par règle
    uv run python scripts/audit_codebase.py --strict             # exit non-zero si findings
    uv run python scripts/audit_codebase.py --json               # sortie JSON pour CI

Détecte :
  - FILE_TOO_LONG               : fichier > 500 lignes
  - TEST_NO_ASSERT              : `def test_*` sans assert
  - ORPHAN_TODO                 : TODO/FIXME sans référence
  - OPUS_WITHOUT_JUSTIFICATION  : agent Opus sans commentaire
  - HARDCODED_PROMPT            : string > 300 chars qui ressemble à un prompt

Whitelist : ajoute `# audit: ignore <RULE>` à la ligne du finding.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import typer
from rich.console import Console
from rich.table import Table

from src.core.audit import AuditConfig, Finding, run_audit, summarize_findings

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()


def _format_severity(sev: str) -> str:
    return {
        "info": "[blue]info[/blue]",
        "warning": "[yellow]warning[/yellow]",
        "error": "[red]error[/red]",
    }.get(sev, sev)


def _print_table(findings: list[Finding], project_root: Path) -> None:
    table = Table(title=f"Audit codebase ({len(findings)} findings)", show_lines=False)
    table.add_column("Règle", style="cyan", width=28)
    table.add_column("Sév.", justify="center", width=8)
    table.add_column("Fichier", style="white", width=36)
    table.add_column("L#", justify="right", width=5)
    table.add_column("Snippet", style="dim")

    for f in findings:
        rel_path = f.path.relative_to(project_root) if f.path.is_absolute() else f.path
        table.add_row(
            f.rule,
            _format_severity(f.severity),
            str(rel_path).replace("\\", "/"),
            str(f.line) if f.line > 0 else "-",
            f.snippet[:60] + ("…" if len(f.snippet) > 60 else ""),
        )
    console.print(table)


def _print_summary(findings: list[Finding]) -> None:
    counts = summarize_findings(findings)
    if not counts:
        console.print("\n[bold green]Audit propre — aucun anti-pattern détecté[/bold green]")
        return

    console.print("\n[bold]Résumé par règle :[/bold]")
    for rule, n in sorted(counts.items()):
        console.print(f"  • [cyan]{rule}[/cyan] : {n}")
    console.print(f"\n[bold]Total : {len(findings)} findings[/bold]")


@app.command()
def audit(
    rule: str | None = typer.Option(
        None, "--rule", "-r", help="Filtre par règle (ex: FILE_TOO_LONG)"
    ),
    strict: bool = typer.Option(False, "--strict", help="Exit non-zero si findings (utile en CI)"),
    json_output: bool = typer.Option(False, "--json", help="Sortie JSON (pour CI / tooling)"),
    max_lines: int = typer.Option(
        500,
        "--max-lines",
        help="Seuil FILE_TOO_LONG (défaut 500)",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Affiche le message complet de chaque finding"
    ),
) -> None:
    project_root = Path(__file__).resolve().parents[1]

    config = AuditConfig(max_file_lines=max_lines)
    findings = run_audit(project_root, config)

    # Filtre par règle si demandé
    if rule:
        findings = [f for f in findings if f.rule.upper() == rule.upper()]

    if json_output:
        out = [
            {
                "rule": f.rule,
                "severity": f.severity,
                "path": str(f.path.relative_to(project_root)).replace("\\", "/"),
                "line": f.line,
                "snippet": f.snippet,
                "message": f.message,
            }
            for f in findings
        ]
        print(json.dumps(out, indent=2, ensure_ascii=False))
        if strict and findings:
            raise SystemExit(1)
        raise SystemExit(0)

    _print_table(findings, project_root)
    _print_summary(findings)

    if verbose:
        console.print("\n[bold]Détails :[/bold]")
        for f in findings:
            rel_path = f.path.relative_to(project_root) if f.path.is_absolute() else f.path
            location = f"{rel_path}:{f.line}" if f.line > 0 else str(rel_path)
            console.print(
                f"\n[cyan]{f.rule}[/cyan] · {_format_severity(f.severity)} · "
                f"{str(location).replace(chr(92), '/')}"
            )
            console.print(f"  {f.message}")

    if strict and findings:
        console.print(f"\n[bold red]--strict : {len(findings)} findings → exit 1[/bold red]")
        raise SystemExit(1)
    raise SystemExit(0)


if __name__ == "__main__":
    app()
