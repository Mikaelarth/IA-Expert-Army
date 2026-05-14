"""approvals — CLI HITL pour visualiser et décider les demandes d'approbation.

Mécanisme central documenté dans `src/core/approvals.py` et `docs/adr/014-hitl-approvals.md`.

Usage :
    uv run python scripts/approvals.py list           # liste pending
    uv run python scripts/approvals.py list --decided # liste decided (history)
    uv run python scripts/approvals.py show <id>      # détail
    uv run python scripts/approvals.py approve <id> --reason "OK car ..."
    uv run python scripts/approvals.py reject <id> --reason "Non parce que ..."
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.core.approvals import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    ApprovalStore,
    decide,
)
from src.core.config import get_settings

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


def _approvals_root() -> Path:
    s = get_settings()
    return s.project_root / "data" / "approvals"


def _verdict_style(status: str) -> str:
    return {
        STATUS_PENDING: "yellow",
        STATUS_APPROVED: "green",
        STATUS_REJECTED: "red",
    }.get(status, "white")


@app.command(name="list")
def list_cmd(
    decided: bool = typer.Option(False, "--decided", help="Liste l'historique au lieu du pending"),
    limit: int = typer.Option(20, "--limit", "-n", help="Nombre max d'entrées"),
) -> None:
    """Liste les demandes d'approbation."""
    store = ApprovalStore(_approvals_root())
    items = store.list_decided(limit=limit) if decided else store.list_pending()
    title = f"Approvals {'(decided history, latest first)' if decided else '(PENDING, FIFO)'}"

    if not items:
        console.print(f"[dim]Aucune demande {'décidée' if decided else 'en attente'}.[/dim]")
        return

    table = Table(title=title)
    table.add_column("ID", style="cyan", no_wrap=False)
    table.add_column("Event", style="magenta")
    table.add_column("Status", justify="center")
    if decided:
        table.add_column("Decided by", style="dim")
    table.add_column("Requested at", style="dim")

    for r in items[:limit]:
        style = _verdict_style(r.status)
        cols = [
            r.approval_id[:13] + "…",
            r.event_type,
            f"[{style}]{r.status}[/{style}]",
        ]
        if decided:
            cols.append(r.decided_by or "—")
        cols.append(r.requested_at[:19])
        table.add_row(*cols)

    console.print(table)


@app.command()
def show(approval_id: str = typer.Argument(..., help="ID complet de la requête")) -> None:
    """Affiche le détail complet d'une demande (pending ou decided)."""
    store = ApprovalStore(_approvals_root())
    req = store.read(approval_id)
    if req is None:
        console.print(f"[red]Approval introuvable : {approval_id}[/red]")
        raise SystemExit(1)

    style = _verdict_style(req.status)
    console.print(
        Panel(
            f"[bold cyan]ID :[/bold cyan] {req.approval_id}\n"
            f"[bold magenta]Event :[/bold magenta] {req.event_type}\n"
            f"[bold]Status :[/bold] [{style}]{req.status}[/{style}]\n"
            f"[dim]Requested at :[/dim] {req.requested_at}\n"
            f"[dim]Requested by :[/dim] {req.requested_by}\n"
            f"[dim]Blocking :[/dim] {req.blocking}"
            + (
                f"\n[dim]Decided at :[/dim] {req.decided_at}\n"
                f"[dim]Decided by :[/dim] {req.decided_by}\n"
                f"[dim]Reason :[/dim] {req.reason or '(none)'}"
                if req.status != STATUS_PENDING
                else ""
            ),
            title="Approval Request",
            border_style=style,
        )
    )

    if req.context:
        console.print("\n[bold cyan]Context :[/bold cyan]")
        console.print(json.dumps(req.context, indent=2, ensure_ascii=False))


@app.command()
def approve(
    approval_id: str = typer.Argument(..., help="ID complet de la requête"),
    reason: str = typer.Option("", "--reason", "-r", help="Raison de l'approbation (recommandé)"),
) -> None:
    """Approuve une demande pending."""
    store = ApprovalStore(_approvals_root())
    user = getpass.getuser() or "unknown"
    result = decide(store, approval_id, approved=True, decided_by=user, reason=reason)
    if result is None:
        console.print(
            f"[red]Décision impossible :[/red] {approval_id} n'existe pas ou est déjà décidée."
        )
        raise SystemExit(1)
    console.print(f"[green]✓ APPROUVÉ[/green] : {approval_id} par {user}")
    if reason:
        console.print(f"  [dim]Raison :[/dim] {reason}")


@app.command()
def reject(
    approval_id: str = typer.Argument(..., help="ID complet de la requête"),
    reason: str = typer.Option(
        ..., "--reason", "-r", help="Raison du rejet (OBLIGATOIRE pour traçabilité)"
    ),
) -> None:
    """Rejette une demande pending. La raison est obligatoire."""
    if not reason.strip():
        console.print("[red]--reason est obligatoire pour un rejet (traçabilité).[/red]")
        raise SystemExit(2)
    store = ApprovalStore(_approvals_root())
    user = getpass.getuser() or "unknown"
    result = decide(store, approval_id, approved=False, decided_by=user, reason=reason)
    if result is None:
        console.print(
            f"[red]Décision impossible :[/red] {approval_id} n'existe pas ou est déjà décidée."
        )
        raise SystemExit(1)
    console.print(f"[red]✗ REJETÉ[/red] : {approval_id} par {user}")
    console.print(f"  [dim]Raison :[/dim] {reason}")


if __name__ == "__main__":
    app()
