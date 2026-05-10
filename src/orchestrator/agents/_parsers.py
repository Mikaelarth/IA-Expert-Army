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


_CODE_BLOCK = re.compile(
    r"^###\s+`(?P<path>[^`]+)`\s*\n+```(?P<lang>\w+)?\s*\n(?P<code>.*?)\n```",
    re.DOTALL | re.MULTILINE,
)


def extract_files(text: str) -> list[dict[str, str]]:
    r"""Extrait les fichiers d'une réponse Markdown du Developer.

    Chaque fichier est repéré par un titre `### \`chemin\`` suivi d'un bloc de code.
    """
    files: list[dict[str, str]] = []
    for m in _CODE_BLOCK.finditer(text):
        files.append(
            {
                "path": m.group("path").strip(),
                "language": (m.group("lang") or "").strip(),
                "content": m.group("code"),
            }
        )
    return files
