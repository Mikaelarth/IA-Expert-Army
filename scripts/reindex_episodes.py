"""Reindex Episodes — backfill de la VectorMemory depuis les épisodes FileMemory existants.

Utile pour :
- Initialiser la mémoire vectorielle après l'introduction de Phase 2 sur des épisodes pré-existants.
- Re-construire l'index si la collection Chroma est corrompue ou supprimée.

Usage:
    uv run python scripts/reindex_episodes.py
    uv run python scripts/reindex_episodes.py --reset  # vide la collection avant reindex
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import typer
from rich.console import Console

from src.core.config import get_settings
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory

app = typer.Typer(no_args_is_help=False, add_completion=False)
console = Console()

_TASK_RE = re.compile(r"##\s+T[âa]che\s*\n+(.*?)(?=\n##\s|\Z)", re.DOTALL)
_OUTPUT_RE = re.compile(r"##\s+Sortie\s+brute\s*\n+(.*?)(?=\n##\s|\Z)", re.DOTALL)


def _extract_task_and_output(body: str) -> tuple[str, str]:
    task_match = _TASK_RE.search(body)
    output_match = _OUTPUT_RE.search(body)
    task = task_match.group(1).strip() if task_match else ""
    output = output_match.group(1).strip() if output_match else ""
    return task, output


def _truncate(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "\n…[tronqué]"


@app.command()
def reindex(
    reset: bool = typer.Option(False, "--reset", help="Vide la collection avant reindex"),
) -> None:
    settings = get_settings()
    memory_root = settings.project_root / "data" / "memory"
    memory = FileMemory(memory_root)
    vmem = VectorMemory(persist_dir=settings.chroma_persist_dir)

    if reset:
        before = vmem.count()
        vmem.reset()
        console.print(f"[yellow]Collection réinitialisée ({before} épisodes supprimés)[/yellow]")

    episodes = memory.list_episodes()
    if not episodes:
        console.print("[yellow]Aucun épisode trouvé dans data/memory/episodes/.[/yellow]")
        raise SystemExit(0)

    console.print(f"[cyan]Indexation de {len(episodes)} épisode(s)…[/cyan]")
    indexed = 0
    skipped = 0

    for path in episodes:
        record = memory.read_episode(path)
        meta = record.metadata
        if not meta.get("success"):
            skipped += 1
            continue
        task, output = _extract_task_and_output(record.body)
        if not task and not output:
            skipped += 1
            continue
        document = f"Tâche: {task}\n\nSortie:\n{_truncate(output, 2000)}"
        # Reconstitue un episode_id stable depuis le nom de fichier
        episode_id = path.stem
        vmem.add_episode(episode_id=episode_id, document=document, metadata=meta)
        indexed += 1
        console.print(f"  [green]✓[/green] {episode_id} (agent={meta.get('agent', '?')})")

    console.print(
        f"\n[bold green]{indexed} épisodes indexés[/bold green]"
        + (f" · [dim]{skipped} ignorés (échec ou vides)[/dim]" if skipped else "")
    )
    console.print(
        f"[dim]Collection « {vmem.collection_name} » contient maintenant {vmem.count()} épisodes.[/dim]"
    )


if __name__ == "__main__":
    app()
