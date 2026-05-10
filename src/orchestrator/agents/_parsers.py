"""Parseurs partagés — extraction de YAML / code blocks à partir de la sortie d'un LLM."""
from __future__ import annotations

import re
from typing import Any

import yaml

_FENCE = re.compile(r"```(?:yaml|yml)?\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)


def extract_yaml(text: str) -> dict[str, Any] | None:
    """Extrait un bloc YAML : code fence ```yaml ... ``` en priorité, sinon tout le texte."""
    match = _FENCE.search(text)
    candidate = match.group(1) if match else text
    try:
        loaded = yaml.safe_load(candidate)
    except yaml.YAMLError:
        return None
    if isinstance(loaded, dict):
        return loaded
    return None


_TITLE = re.compile(r"^###\s+`([^`]+)`\s*$")
_FENCE_OPEN = re.compile(r"^```(\w*)\s*$")
_FENCE_CLOSE = "```"


def extract_files(text: str) -> list[dict[str, str]]:
    r"""Extrait les fichiers d'une réponse Markdown du Developer.

    Convention attendue (cf. system prompt du backend_developer) :

        ### `chemin/relatif/fichier.py`

        ```python
        <contenu>
        ```

    Parser ligne-à-ligne (plutôt qu'un regex monolithique) pour gérer correctement :
    les blocs vides (`__init__.py`), les contenus multi-lignes avec ``` à l'intérieur,
    et les titres entre blocs.
    """
    files: list[dict[str, str]] = []
    lines = text.split("\n")
    i = 0
    n = len(lines)

    while i < n:
        title_match = _TITLE.match(lines[i])
        if not title_match:
            i += 1
            continue

        path = title_match.group(1).strip()

        # Skip lignes vides entre titre et fence d'ouverture
        j = i + 1
        while j < n and lines[j].strip() == "":
            j += 1

        if j >= n:
            i += 1
            continue

        fence_match = _FENCE_OPEN.match(lines[j])
        if not fence_match:
            i += 1
            continue

        language = fence_match.group(1)
        code_lines: list[str] = []
        k = j + 1
        closed = False

        while k < n:
            if lines[k].rstrip() == _FENCE_CLOSE:
                closed = True
                break
            code_lines.append(lines[k])
            k += 1

        if closed:
            files.append(
                {
                    "path": path,
                    "language": language,
                    "content": "\n".join(code_lines),
                }
            )
            i = k + 1
        else:
            # Fence non fermée : on ignore ce bloc et on continue après le titre
            i += 1

    return files
