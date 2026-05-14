"""Parseurs partagés — extraction de YAML / code blocks à partir de la sortie d'un LLM."""

from __future__ import annotations

import re
from typing import Any

import yaml

_FENCE = re.compile(r"```(?:yaml|yml)?\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)

# Détecte un item de liste YAML qui contient un `:` suivi d'espace dans son texte
# (typique des chaînes générées par LLM). Cas piégé :
#   - Conditions de validité explicites : "payant pour X / contre-productif Y"
# YAML strict interprète " :" comme séparateur clé-valeur → ParserError.
# Le pré-traitement consiste à entourer l'item de guillemets simples si non-quoté.
_LIST_ITEM_WITH_COLON = re.compile(
    r"^(?P<indent>\s*-\s+)(?!['\"])(?P<content>[^\n]*?\s:\s[^\n]+)$",
    re.MULTILINE,
)


def _quote_problematic_list_items(yaml_text: str) -> str:
    """Pré-traite un YAML texte pour quoter automatiquement les items de liste
    contenant ' : ' non quotés. Bug récurrent des LLMs.

    Conserve les items déjà quotés ou qui sont des dicts (clé: valeur en début de ligne)."""

    def _quote(match: re.Match[str]) -> str:
        indent = match.group("indent")
        content = match.group("content").rstrip()
        # On échappe les apostrophes dans le contenu
        escaped = content.replace("'", "''")
        return f"{indent}'{escaped}'"

    return _LIST_ITEM_WITH_COLON.sub(_quote, yaml_text)


def _safe_yaml_load(text: str) -> dict[str, Any] | None:
    """Essaie un chargement strict, puis avec pré-traitement de récupération."""
    try:
        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            return loaded
        return None
    except yaml.YAMLError:
        pass

    # Recovery : pré-traiter et retenter
    pre_processed = _quote_problematic_list_items(text)
    if pre_processed != text:
        try:
            loaded = yaml.safe_load(pre_processed)
            if isinstance(loaded, dict):
                return loaded
        except yaml.YAMLError:
            pass

    return None


# Fallback regex pour extraire les champs essentiels d'une skill quand YAML
# refuse de parser même après pré-traitement. Couvre les cas LLM les plus
# pathologiques (quotes au milieu d'un item, structures imbriquées invalides,
# etc.). Renvoie un dict partiel — au minimum title doit être présent.
# Note : on utilise [ \t]+ (pas \s*) pour ne PAS traverser les newlines, sinon
# greedy match ramasserait des lignes suivantes par erreur.
_RX_SCALAR_FIELD = re.compile(r"^([a-z_]+):[ \t]+(\S[^\n]*)$", re.MULTILINE)
_RX_BLOCK_SCALAR = re.compile(
    r"^([a-z_]+):[ \t]*[|>][-+]?[ \t]*\n((?:[ \t]+[^\n]*\n?)+)",
    re.MULTILINE,
)
_RX_LIST_FIELD = re.compile(
    r"^([a-z_]+):[ \t]*\n((?:[ \t]*-[ \t]+[^\n]+\n?)+)",
    re.MULTILINE,
)
_RX_LIST_ITEM = re.compile(r"^[ \t]*-[ \t]+(.+?)\s*$", re.MULTILINE)


def _dedent_block(block_text: str) -> str:
    """Dédente un bloc YAML ``|`` ou ``>`` en retirant l'indentation commune."""
    lines = block_text.rstrip().split("\n")
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return ""
    min_indent = min(len(line) - len(line.lstrip()) for line in non_empty)
    return "\n".join(line[min_indent:] for line in lines).strip()


def _strip_outer_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and (
        (text.startswith('"') and text.endswith('"'))
        or (text.startswith("'") and text.endswith("'"))
    ):
        return text[1:-1]
    return text


# Champs qui, s'ils sont présents dans le résultat regex, indiquent qu'on a
# bien extrait un YAML d'agent connu (skill, reviewer, QG, security audit, etc.).
# Sprint DDD.bis : le critère initial `result.get("title")` était trop restrictif
# (les reviewers n'ont pas de title). Sans cette extension, un reviewer YAML
# avec un item de liste multi-ligne contenant ` : ` faisait échouer strict
# parse → fallback retournait None → workflow tombait sur le default REJECTED
# alors que le verdict réel était APPROVED (cf. mission ea8999b0 du 2026-05-14).
_RECOGNIZED_TOP_LEVEL_FIELDS = (
    "title",  # skill, decomposition
    "verdict",  # reviewer (engineering, research, creative)
    "verdict_qg",  # quality guardian
    "verdict_sec",  # security auditor
    "verdict_lead",  # research lead (futur)
    "sub_missions",  # meta decomposer
    "findings",  # security auditor (alternative)
)


def _regex_fallback_extract(text: str) -> dict[str, Any] | None:
    """Extraction de last-resort par regex des champs scalaires + listes + blocks.

    Ne récupère pas de structures imbriquées complexes. Accepte le résultat s'il
    contient au moins un champ "signature" connu (cf. _RECOGNIZED_TOP_LEVEL_FIELDS).
    """
    result: dict[str, Any] = {}

    for match in _RX_SCALAR_FIELD.finditer(text):
        key = match.group(1)
        value = match.group(2).strip()
        # Skip block scalar markers (`|` ou `>`) — gérés par _RX_BLOCK_SCALAR
        if value.startswith("|") or value.startswith(">"):
            continue
        value = _strip_outer_quotes(value)
        if key not in result:  # premier match gagne (évite les overrides depuis exemples)
            result[key] = value

    for match in _RX_BLOCK_SCALAR.finditer(text):
        key = match.group(1)
        if key not in result:
            result[key] = _dedent_block(match.group(2))

    for match in _RX_LIST_FIELD.finditer(text):
        key = match.group(1)
        if key in result:
            continue
        items = [
            _strip_outer_quotes(item_match.group(1))
            for item_match in _RX_LIST_ITEM.finditer(match.group(2))
        ]
        if items:
            result[key] = items

    # On accepte si au moins un champ "signature" est présent (extension du
    # critère initial trop-skill-spécifique).
    if any(field in result for field in _RECOGNIZED_TOP_LEVEL_FIELDS):
        return result
    return None


def extract_yaml(text: str) -> dict[str, Any] | None:
    """Extrait un bloc YAML : code fence ```yaml ... ``` en priorité, sinon tout le texte.

    Tolérance progressive face aux YAML LLM mal formés :
      1. Parse strict yaml.safe_load
      2. Si échec → pré-traitement (quote auto des items list avec ` : `) + retry
      3. Si échec → fallback regex qui extrait les champs scalaires/listes/blocks
         indépendamment (last-resort, perd les structures imbriquées)
    """
    match = _FENCE.search(text)
    candidate = match.group(1) if match else text

    result = _safe_yaml_load(candidate)
    if result is not None:
        return result

    return _regex_fallback_extract(candidate)


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
