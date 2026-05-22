"""templates_browser — gestion des templates de missions réutilisables (v0.8.0 F3).

Adresse le pain point quotidien "à chaque mission, je re-rédige la même
description de 5 lignes" : on définit des templates YAML versionnés dans
`templates/` qu'on instancie en 1 clic depuis la GUI, avec un formulaire
pour les paramètres variables (Jinja2 placeholders).

Format d'un template (YAML frontmatter + corps) :

    ---
    id: fastapi-crud-endpoint
    name: "Endpoint FastAPI CRUD"
    description: "Template pour créer un endpoint REST CRUD complet"
    guild: engineering
    tags: [fastapi, rest, crud]
    params:
      - name: entity_name
        label: "Nom de l'entité (PascalCase)"
        example: "Product"
        required: true
      - name: fields
        label: "Champs (séparés par virgule)"
        example: "name:str, price:float"
        required: true
    ---
    Crée un endpoint FastAPI CRUD complet pour l'entité {{ entity_name }}.

    Champs : {{ fields }}

    Livrables attendus :
    - Pydantic model {{ entity_name }}Create + {{ entity_name }}Response
    - Router avec POST, GET (list + by id), PUT, DELETE
    - Tests pytest couvrant les 5 endpoints
    - Pas de DB réelle, stockage en dict in-memory pour MVP

Les templates vivent dans `templates/missions/<id>.md` (markdown avec
frontmatter YAML, format cohérent avec FileMemory/skills).

API publique :
- list_templates() → liste tous les templates disponibles
- get_template(id) → charge un template par id
- render_template(template, params) → applique Jinja2 sur le corps
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined
from jinja2.exceptions import UndefinedError

from src.core.config import get_settings


@dataclass
class TemplateParam:
    """Un paramètre attendu par un template (rendu en formulaire GUI)."""

    name: str
    label: str
    example: str = ""
    required: bool = True


@dataclass
class MissionTemplate:
    """Un template de mission instanciable.

    `body_jinja` est le corps brut avec placeholders Jinja2. Le titre est
    suggéré par défaut comme `name` + paramètre principal interpolé, mais
    l'utilisateur peut l'éditer en GUI.
    """

    id: str
    name: str
    description: str
    guild: str  # engineering | research | creative | business | "" (auto)
    body_jinja: str
    params: list[TemplateParam] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    path: Path | None = None


# Jinja2 environment — autoescape OFF (on génère du texte LLM, pas du HTML),
# StrictUndefined ON (mieux vaut crasher fort qu'un placeholder oublié qui
# fasse "render dans un blanc" silencieusement).
_JINJA_ENV = Environment(
    autoescape=False,  # noqa: S701 — output texte pour LLM, pas HTML
    undefined=StrictUndefined,
    trim_blocks=False,
    lstrip_blocks=False,
)


def _templates_dir() -> Path:
    """Répertoire racine des templates : `<project>/templates/missions/`."""
    return get_settings().project_root / "templates" / "missions"


def list_templates() -> list[MissionTemplate]:
    """Charge tous les templates `.md` du dossier templates/missions/.

    Les templates malformés (YAML cassé, frontmatter manquant) sont skippés
    silencieusement. Retourne une liste triée par `name`.
    """
    root = _templates_dir()
    if not root.exists():
        return []
    templates: list[MissionTemplate] = []
    for path in sorted(root.glob("*.md")):
        tpl = _load_template_file(path)
        if tpl is not None:
            templates.append(tpl)
    templates.sort(key=lambda t: t.name)
    return templates


def get_template(template_id: str) -> MissionTemplate | None:
    """Charge un template par son `id`. Retourne None si absent ou malformé."""
    for tpl in list_templates():
        if tpl.id == template_id:
            return tpl
    return None


def render_template(
    template: MissionTemplate,
    params: dict[str, Any],
) -> str:
    """Applique les paramètres au corps Jinja2 du template.

    Lève `ValueError` si un paramètre requis n'est pas fourni (StrictUndefined).
    Le caller (page GUI) attrape l'erreur et affiche un message clair.
    """
    try:
        return _JINJA_ENV.from_string(template.body_jinja).render(**params)
    except UndefinedError as exc:
        raise ValueError(
            f"Paramètre manquant ou inutilisé dans le template '{template.id}' : {exc}"
        ) from exc


def _load_template_file(path: Path) -> MissionTemplate | None:
    """Parse un fichier template (frontmatter YAML + corps markdown)."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Frontmatter delimité par '---' (cohérent avec MemoryRecord/skills)
    if not content.startswith("---\n"):
        return None
    parts = content.split("---\n", 2)
    if len(parts) < 3:
        return None
    _, yaml_block, body = parts

    try:
        meta = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict):
        return None

    template_id = meta.get("id")
    name = meta.get("name")
    if not template_id or not name:
        return None

    params: list[TemplateParam] = []
    raw_params = meta.get("params") or []
    if isinstance(raw_params, list):
        for raw in raw_params:
            if not isinstance(raw, dict) or "name" not in raw:
                continue
            params.append(
                TemplateParam(
                    name=str(raw["name"]),
                    label=str(raw.get("label", raw["name"])),
                    example=str(raw.get("example", "")),
                    required=bool(raw.get("required", True)),
                )
            )

    return MissionTemplate(
        id=str(template_id),
        name=str(name),
        description=str(meta.get("description", "")),
        guild=str(meta.get("guild", "")),
        body_jinja=body.lstrip("\n"),
        params=params,
        tags=[str(t) for t in (meta.get("tags") or [])],
        path=path,
    )
