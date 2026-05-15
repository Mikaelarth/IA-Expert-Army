"""Hello Agent — Premier appel à Claude depuis IA-Expert-Army.

Cette commande active le tout premier agent de l'armée. Elle valide :
- la clé API Anthropic
- la connectivité réseau
- la configuration Settings
- le pipeline de logging

Usage:
    uv run python scripts/hello_agent.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Force UTF-8 sur stdout/stderr (Windows console = cp1252 par défaut, casse les emojis Rich)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Permet d'exécuter ce script depuis la racine du projet
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anthropic import AsyncAnthropic
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from src.core.config import get_settings
from src.core.logging import get_logger, setup_logging

console = Console()


async def main() -> int:
    settings = get_settings()
    setup_logging(level=settings.log_level, fmt=settings.log_format)
    log = get_logger("hello_agent")

    console.print(
        Panel.fit(
            Text("IA-EXPERT-ARMY — Activation du premier agent", style="bold cyan"),
            border_style="cyan",
        )
    )

    log.info(
        "settings.loaded",
        # Opus pour le script demo (présentation initiale, ~$0.03 unique, justifié).
        model=settings.model_strategic,
        budget=settings.daily_budget_usd,
        log_format=settings.log_format,
    )

    client = AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())

    system_prompt = (
        "Tu es le tout premier agent activé du système IA-Expert-Army, "
        "une équipe d'agents IA experts pilotée par MikaelArth. "
        "Tu inaugures une architecture en 4 couches : direction, guildes, infrastructure, apprentissage. "
        "Réponds en français, sois bref (4-6 phrases), inspirant et professionnel."
    )

    user_prompt = (
        "Présente-toi à MikaelArth en tant que Chief Orchestrator de l'IA-Expert-Army. "
        "Confirme que tu es opérationnel, mentionne les 4 guildes que tu coordonneras "
        "(Engineering, Research, Creative, Business), et exprime ce que cette armée pourra accomplir."
    )

    console.print("\n[dim]Appel à Claude…[/dim]\n")

    try:
        # Opus pour la présentation initiale (cf. commentaire ligne 50).
        response = await client.messages.create(
            model=settings.model_strategic,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:
        log.error("anthropic.call.failed", error=str(exc), exc_info=True)
        console.print(f"\n[bold red]Échec de l'appel Anthropic :[/bold red] {exc}")
        return 1

    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )

    console.print(
        Panel(
            Text(text, style="white"),
            title=f"[bold cyan]Chief Orchestrator ({response.model})[/bold cyan]",
            border_style="cyan",
        )
    )

    in_tok = response.usage.input_tokens
    out_tok = response.usage.output_tokens
    log.info(
        "anthropic.call.success",
        model=response.model,
        stop_reason=response.stop_reason,
        input_tokens=in_tok,
        output_tokens=out_tok,
    )

    console.print(
        f"\n[green]✓[/green] Tokens consommés : "
        f"[bold]{in_tok}[/bold] in · [bold]{out_tok}[/bold] out"
    )
    console.print("\n[bold green]Phase 0 validée — l'armée est prête à grandir.[/bold green]\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
