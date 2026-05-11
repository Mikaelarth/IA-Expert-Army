"""Smoke test isolé du MetaDecomposer.

But : valider en conditions réelles (vrai appel Opus) que le prompt produit
du YAML bien formé et parseable, AVANT d'engager le coût d'une mission
complète cross-guildes.

Coût attendu : ~$0.05 (1 appel Opus, ~3000 tokens out).

Usage:
    uv run python scripts/smoke_meta_decomposer.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uuid import uuid4

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from src.core.config import get_settings
from src.core.logging import setup_logging
from src.memory.file_memory import FileMemory
from src.orchestrator.base_agent import AgentInput
from src.orchestrator.meta_workflow import MetaDecomposer, _parse_decomposition

console = Console()


async def main() -> None:
    settings = get_settings()
    setup_logging(level=settings.log_level, fmt=settings.log_format)

    memory = FileMemory(settings.project_root / "data" / "memory")

    # Mission test : 3 livrables clairs, 3 guildes attendues
    title = "Mini-produit water-tracker"
    description = (
        "Conçois un mini-produit ultra-simple pour suivre sa consommation d'eau. "
        "3 livrables : (1) un endpoint API POST /track qui reçoit {ml: int} et "
        "stocke la valeur en mémoire (engineering), (2) une page HTML statique "
        "de 150 mots qui explique la promesse et donne envie de tester (creative), "
        "(3) une roadmap produit 3 jalons V1/V2/V3 avec ce qui appartient à chaque "
        "version (business)."
    )

    console.print(
        Panel.fit(
            f"[bold cyan]Mission test :[/bold cyan] {title}\n[dim]{description}[/dim]",
            title="Smoke test MetaDecomposer",
            border_style="cyan",
        )
    )

    decomposer = MetaDecomposer(memory=memory, settings=settings)
    out = await decomposer.run(
        AgentInput(
            mission_id=uuid4(),
            task=f"Mission cross-domaine à décomposer.\n\nTitre : {title}\n\nDescription :\n{description}",
        )
    )

    console.print(
        f"\n[bold]Résultat brut :[/bold] success={out.success} · "
        f"tokens=({out.tokens_in}/{out.tokens_out}) · "
        f"cost=[bold green]${out.cost_usd:.4f}[/bold green] · "
        f"durée={out.duration_seconds:.1f}s · "
        f"saturated={out.saturated}"
    )

    if not out.success:
        console.print(f"\n[bold red]Décomposeur a échoué :[/bold red] {out.error}")
        raise SystemExit(1)

    if out.parsed is None:
        console.print("\n[bold red]Pas de YAML parsable dans la sortie.[/bold red]")
        console.print(
            Panel(out.raw_text[:2000], title="Sortie brute (truncated)", border_style="red")
        )
        raise SystemExit(2)

    # Affiche le YAML brut
    import yaml as _yaml

    yaml_text = _yaml.safe_dump(out.parsed, sort_keys=False, allow_unicode=True)
    console.print("\n[bold cyan]YAML parsé :[/bold cyan]")
    console.print(Syntax(yaml_text, "yaml", theme="monokai", line_numbers=False))

    # Validation finale via _parse_decomposition (mêmes checks que la prod)
    try:
        decomp = _parse_decomposition(out.parsed)
    except Exception as exc:
        console.print(f"\n[bold red]Validation strict échouée :[/bold red] {exc}")
        raise SystemExit(3) from exc

    console.print(
        f"\n[bold green]✓ Décomposition valide.[/bold green] "
        f"{len(decomp.sub_missions)} sous-mission(s), guildes : "
        f"{[s.guild for s in decomp.sub_missions]}"
    )
    console.print(
        f"[dim]Rationale ({len(decomp.rationale)} chars) :[/dim] {decomp.rationale[:300]}"
    )


if __name__ == "__main__":
    asyncio.run(main())
