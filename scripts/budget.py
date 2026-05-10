"""budget — affiche/modifie l'état du BudgetController.

Usage:
    uv run python scripts/budget.py status
    uv run python scripts/budget.py reset       # remet à 0 pour aujourd'hui
    uv run python scripts/budget.py record 0.50 # ajoute 0.50 USD au cumul du jour
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

from src.core.budget import BudgetController
from src.core.config import get_settings

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


def _controller() -> BudgetController:
    s = get_settings()
    return BudgetController(
        state_path=s.project_root / "data" / "budget_state.json",
        daily_budget_usd=s.daily_budget_usd,
    )


@app.command()
def status() -> None:
    """Affiche le statut actuel du budget."""
    bc = _controller()
    st = bc.status()
    table = Table(title="Budget journalier", show_lines=False)
    table.add_column("Champ", style="cyan")
    table.add_column("Valeur", style="white")
    table.add_row("Date", st["date"])
    table.add_row("Plafond (USD)", f"{st['daily_budget_usd']:.2f}")
    table.add_row("Dépensé (USD)", f"{st['spent_usd']:.4f}")
    table.add_row("Restant (USD)", f"{st['remaining_usd']:.4f}")
    table.add_row("Utilisation", f"{st['percent_used']:.1f}%")
    table.add_row("Jours archivés", str(st["history_days_kept"]))
    console.print(table)
    if st["percent_used"] >= 100:
        console.print("[bold red]Budget atteint pour aujourd'hui.[/bold red]")
    elif st["percent_used"] >= 80:
        console.print("[yellow]Attention : > 80% du budget consommé.[/yellow]")


@app.command()
def reset() -> None:
    """Remet le compteur du jour à zéro (préserve l'historique)."""
    bc = _controller()
    data = bc._load()
    data["spent_usd"] = 0.0
    bc._save(data)
    console.print("[green]Cumul du jour remis à 0.[/green]")


@app.command()
def record(amount: float = typer.Argument(..., help="Montant en USD à ajouter")) -> None:
    """Ajoute manuellement un montant au cumul du jour."""
    bc = _controller()
    data = bc.record(amount)
    console.print(
        f"[green]Enregistré +{amount:.4f} USD.[/green] "
        f"Total du jour : [bold]{data['spent_usd']:.4f}[/bold]"
    )


if __name__ == "__main__":
    app()
