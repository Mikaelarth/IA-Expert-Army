"""probe_reviewer — Mesure directe et déterministe du CodeReviewer sur input contrôlé.

Session 5 : on lance le CodeReviewer (modèle = `settings.model_operational`,
par défaut `qwen2.5-coder:32b`) sur le code+test bugué Session 2 *inchangé*
(le test `test_slugify_multiple_punctuation` attend `"-"` alors que
`.strip('-')` final produit `""`). Mesure si le Reviewer détecte le bug
grâce aux instructions v0.2.0+ "exécution mentale" et v0.3.0+ "conformité spec".

Pourquoi un script et pas un test pytest : un vrai appel Ollama prend
5-10 min sans GPU haut de gamme. C'est trop lent pour la suite pytest
standard. Le probe est un outil de mesure reproductible à lancer à la main
quand on modifie le prompt et qu'on veut un benchmark avant/après.

Le résultat YAML brut + métriques sont écrits dans `data/probes/<timestamp>_<case>.md`
pour traçabilité (un fichier par run, jamais écrasé). Exit code 0 si le
bug est détecté, 2 sinon (utilisable en CI manuel).

Usage:
    uv run python scripts/probe_reviewer.py
    uv run python scripts/probe_reviewer.py --case bug-session-2  # défaut
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import typer
from rich.console import Console

from src.core.config import get_settings
from src.core.logging import setup_logging
from src.memory.file_memory import FileMemory
from src.orchestrator.agents.reviewer import CodeReviewer
from src.orchestrator.base_agent import AgentInput

console = Console()
app = typer.Typer(no_args_is_help=False, add_completion=False)


# ============================================================================
# Cas contrôlé : bug Session 2 reproduit exactement, dans le format
# qu'aurait produit le BackendDeveloper (cf. workflow.py context passé au
# Reviewer : `developer_output_md`).
# ============================================================================

_BUG_SESSION_2_DEVELOPER_OUTPUT = """## Approche

Implémentation directe selon le plan d'architecte. Module `src/utils/text.py`
avec une fonction unique `slugify`. Tests pytest pour les cas canoniques +
edge cases.

## Fichiers produits

### `src/utils/text.py`

```python
import re
import unicodedata


def slugify(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r'[^a-z0-9]', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')
```

### `tests/unit/test_text.py`

```python
import pytest
from src.utils.text import slugify


def test_slugify_normal():
    assert slugify("Hello World") == "hello-world"


def test_slugify_accents():
    assert slugify("Café à Paris") == "cafe-a-paris"


def test_slugify_empty_string():
    assert slugify("") == ""


def test_slugify_multiple_punctuation():
    assert slugify("!@#$%^&*().,?/") == "-"


def test_slugify_multiple_spaces():
    assert slugify("a     b") == "a-b"
```
"""

_BUG_SESSION_2_ARCHITECTURE = """## Approche

Une fonction `slugify(text: str) -> str` qui :
1. Normalise NFKD pour décomposer les accents
2. Encode en ASCII pour drop les diacritiques
3. Lowercase + remplace les non-alphanum par `-`
4. Strip les `-` en début/fin et compacte les multiples

## Architecture

- Module : `src/utils/text.py`
- Fonction unique exposée : `slugify`
- Tests : `tests/unit/test_text.py` couvrant cas canoniques + edge cases
"""

_TASK_DESCRIPTION_ORIGINAL = (
    "Implémente une fonction Python `slugify(text: str) -> str` qui produit un slug "
    "url-safe à partir d'un texte arbitraire. Contraintes : pas de dépendance externe "
    "(juste unicodedata + re de la stdlib). Comportements attendus : lowercase, accents "
    "et diacritiques retirés, caractères non-alphanumériques remplacés par '-', dashes "
    "multiples compactés, dashes en début/fin retirés. Inclus des tests pytest pour les "
    "cas canoniques (Hello World), accents (Café à Paris), chaîne vide, ponctuation "
    "multiple, espaces multiples. Module cible : src/utils/text.py. Tests cible : "
    "tests/unit/test_text.py."
)


def _bug_was_detected(parsed: dict | None) -> tuple[bool, str]:
    """Heuristique d'analyse du verdict Reviewer.

    Renvoie (detected, reason). Le test bugué est considéré comme détecté si :
    - le verdict est NEEDS_CHANGES ou REJECTED, OU
    - un finding cite explicitement le nom du test ou son input, OU
    - un finding mentionne la valeur attendue `"-"` vs réalité `""`.
    """
    if not parsed or not isinstance(parsed, dict):
        return False, "parsed output None ou invalide"

    verdict = str(parsed.get("verdict", "")).upper()
    if verdict in {"NEEDS_CHANGES", "REJECTED"}:
        return True, f"verdict={verdict} (refuse l'output, donc a flaggé un problème)"

    issues = parsed.get("issues") or []
    if not isinstance(issues, list):
        return False, "issues non-liste"

    bug_markers = (
        "test_slugify_multiple_punctuation",
        '"-"',
        "strip",
        "empty string",
        "chaîne vide",
        "expected",
        "expectation",
        "assertion incorrect",
        "incorrect assertion",
    )
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        msg = str(issue.get("message", "")).lower()
        sev = str(issue.get("severity", "")).lower()
        cat = str(issue.get("category", "")).lower()
        if sev in {"blocker", "major"} and cat in {"tests", "correctness"}:
            if any(marker.lower() in msg for marker in bug_markers):
                return True, (
                    f"finding severity={sev} category={cat} citant un marqueur du bug : "
                    f"« {msg[:120]}… »"
                )
    return False, "aucun finding ne cite le bug du test_slugify_multiple_punctuation"


@app.command()
def probe(
    case: str = typer.Option(
        "bug-session-2",
        "--case",
        help="Identifiant du cas de probe (défaut : bug-session-2)",
    ),
) -> None:
    """Lance le CodeReviewer sur le cas contrôlé, mesure si le bug est détecté."""
    settings = get_settings()
    setup_logging(level=settings.log_level, fmt=settings.log_format)

    project_root = Path(__file__).resolve().parents[1]
    probes_dir = project_root / "data" / "probes"
    probes_dir.mkdir(parents=True, exist_ok=True)
    # Mémoire temp : on isole le probe pour ne pas polluer data/memory/.
    tmp_memory_root = probes_dir / "_tmp_memory"
    tmp_memory_root.mkdir(parents=True, exist_ok=True)
    memory = FileMemory(tmp_memory_root)

    # Pas de RAG ni de skills injectées : isolation maximale, on teste UNIQUEMENT
    # le pouvoir du system prompt v0.3.0 face à l'input contrôlé.
    reviewer = CodeReviewer(
        memory=memory,
        settings=settings,
        vector_memory=None,
        skills_library=None,
    )

    console.print(f"[cyan]Probe case   :[/cyan] {case}")
    console.print(f"[cyan]Modèle       :[/cyan] {settings.model_operational}")
    console.print(f"[cyan]Prompt path  :[/cyan] {reviewer.prompt_path.relative_to(project_root)}")
    console.print(f"[cyan]Ollama URL   :[/cyan] {settings.ollama_base_url}")
    console.print(f"[cyan]Timeout      :[/cyan] {settings.ollama_timeout_seconds} s")

    agent_input = AgentInput(
        mission_id=uuid4(),
        task="Implémenter la logique de la fonction slugify()",
        context={
            "architecture_proposal_yaml": _BUG_SESSION_2_ARCHITECTURE,
            "developer_output_md": _BUG_SESSION_2_DEVELOPER_OUTPUT,
            "_probe_mission_description": _TASK_DESCRIPTION_ORIGINAL,
        },
    )

    console.print("\n[dim]Appel Reviewer (5-10 min sur qwen2.5-coder:32b sans GPU)…[/dim]\n")
    output = asyncio.run(reviewer.run(agent_input))

    parsed = output.parsed if isinstance(output.parsed, dict) else None
    verdict = parsed.get("verdict", "?") if parsed else "?"
    score = parsed.get("quality_score", "?") if parsed else "?"
    detected, reason = _bug_was_detected(parsed)

    console.print(f"\n[bold]Verdict        :[/bold] {verdict}")
    console.print(f"[bold]Score          :[/bold] {score}")
    console.print(f"[bold]Bug détecté    :[/bold] {'✅ OUI' if detected else '❌ NON'}")
    console.print(f"[dim]Raison         : {reason}[/dim]")
    console.print(
        f"[dim]Durée          : {output.duration_seconds:.1f}s · "
        f"tokens in/out : {output.tokens_in}/{output.tokens_out} · "
        f"saturé : {output.saturated}[/dim]"
    )

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out_path = probes_dir / f"{ts}_{case}.md"
    body = f"""# Probe Reviewer — case `{case}`

**Date**     : `{datetime.now(UTC).isoformat()}`
**Modèle**   : `{settings.model_operational}`
**Prompt**   : `{reviewer.prompt_path.relative_to(project_root)}`
**Ollama**   : `{settings.ollama_base_url}` (timeout {settings.ollama_timeout_seconds} s)

## Mesure

| Champ | Valeur |
|---|---|
| Verdict | `{verdict}` |
| Quality score | `{score}` |
| **Bug détecté** | {'✅ OUI' if detected else '❌ NON'} |
| Raison | {reason} |
| Durée | {output.duration_seconds:.1f} s |
| Tokens in / out | {output.tokens_in} / {output.tokens_out} |
| Saturation | {'OUI ⚠️' if output.saturated else 'non'} |
| Success | {output.success} |

## Output YAML brut du Reviewer

```yaml
{output.raw_text}
```

## Input fourni au Reviewer

### Mission description (contexte)

```
{_TASK_DESCRIPTION_ORIGINAL}
```

### Architecture proposition (context.architecture_proposal_yaml)

```
{_BUG_SESSION_2_ARCHITECTURE}
```

### Developer output avec le bug intentionnel (context.developer_output_md)

```markdown
{_BUG_SESSION_2_DEVELOPER_OUTPUT}
```

## Note

Le test bugué est `test_slugify_multiple_punctuation` ligne 22 du developer_output :
`assert slugify("!@#$%^&*().,?/") == "-"` — mais l'exécution réelle du pipeline
slugify avec `.strip('-')` final produit `""`, pas `"-"`. Un Reviewer rigoureux
qui fait l'exécution mentale (instruction v0.2.0 du prompt) doit détecter ce
décalage et émettre un finding `severity: major` catégorie `tests`.
"""
    out_path.write_text(body, encoding="utf-8")
    console.print(f"\n[green]Résultat écrit dans :[/green] {out_path}")

    raise SystemExit(0 if detected else 2)


if __name__ == "__main__":
    app()
