"""Hello Agent — Premier appel LLM depuis IA-Expert-Army (Ollama local).

Cette commande active le tout premier agent de l'armée. Elle valide :
- la connectivité au daemon Ollama (http://localhost:11434/v1)
- la présence du modèle stratégique configuré
- la configuration Settings
- le pipeline de logging

Bascule v0.4.0 (ADR-025) : passe par Ollama local via le SDK openai
pointé sur localhost:11434/v1. Aucun coût, aucune clé API.

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

from openai import AsyncOpenAI
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
        model=settings.model_strategic,
        ollama_url=settings.ollama_base_url,
        log_format=settings.log_format,
    )

    client = AsyncOpenAI(
        base_url=settings.ollama_base_url,
        api_key=settings.ollama_api_key,
        timeout=settings.ollama_timeout_seconds,
    )

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

    console.print(f"\n[dim]Appel à Ollama ({settings.model_strategic})…[/dim]\n")

    try:
        response = await client.chat.completions.create(
            model=settings.model_strategic,
            max_tokens=512,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as exc:
        log.error("ollama.call.failed", error=str(exc), exc_info=True)
        console.print(f"\n[bold red]Échec de l'appel Ollama :[/bold red] {exc}")
        console.print(
            "\n[yellow]Vérifie qu'Ollama tourne :[/yellow] `ollama list` doit répondre.\n"
            f"[yellow]Et que le modèle est pullé :[/yellow] `ollama pull {settings.model_strategic}`"
        )
        return 1

    text = response.choices[0].message.content or ""

    console.print(
        Panel(
            Text(text, style="white"),
            title=f"[bold cyan]Chief Orchestrator ({response.model})[/bold cyan]",
            border_style="cyan",
        )
    )

    usage = response.usage
    in_tok = getattr(usage, "prompt_tokens", 0) if usage else 0
    out_tok = getattr(usage, "completion_tokens", 0) if usage else 0
    log.info(
        "ollama.call.success",
        model=response.model,
        finish_reason=response.choices[0].finish_reason,
        prompt_tokens=in_tok,
        completion_tokens=out_tok,
    )

    console.print(
        f"\n[green]✓[/green] Tokens consommés : "
        f"[bold]{in_tok}[/bold] in · [bold]{out_tok}[/bold] out · [bold]$0.00[/bold] (local)"
    )
    console.print("\n[bold green]Phase 0 validée — l'armée est prête à grandir.[/bold green]\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
