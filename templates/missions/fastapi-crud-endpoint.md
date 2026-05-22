---
id: fastapi-crud-endpoint
name: "Endpoint FastAPI CRUD"
description: "Crée un endpoint REST CRUD complet (5 routes) avec Pydantic + tests pytest."
guild: engineering
tags: [fastapi, rest, crud, pytest]
params:
  - name: entity_name
    label: "Nom de l'entité (PascalCase)"
    example: "Product"
    required: true
  - name: fields
    label: "Champs (format: nom:type, séparés par virgule)"
    example: "name:str, price:float, in_stock:bool"
    required: true
  - name: file_target
    label: "Module cible (chemin relatif depuis src/)"
    example: "api/products.py"
    required: true
---
Implémente un endpoint FastAPI CRUD complet pour l'entité **{{ entity_name }}**.

## Champs de l'entité

{{ fields }}

## Livrables attendus

1. **Pydantic models** (`{{ entity_name }}Create`, `{{ entity_name }}Update`,
   `{{ entity_name }}Response`) avec validation des champs et types appropriés.
2. **APIRouter** monté sous `/{{ entity_name.lower() }}s` avec les 5 routes :
   - `POST /` — création (retourne 201 + response)
   - `GET /` — liste paginée (query params `limit` + `offset`)
   - `GET /{id}` — détail (404 si absent)
   - `PUT /{id}` — update partiel (404 si absent)
   - `DELETE /{id}` — suppression (204 si OK, 404 si absent)
3. **Stockage in-memory** dans un `dict[int, dict]` (pas de DB pour MVP).
   IDs auto-incrémentés.
4. **Tests pytest** dans `tests/unit/test_{{ entity_name.lower() }}s.py`
   couvrant les 5 routes + cas d'erreur 404. Utiliser
   `httpx.AsyncClient` + `ASGITransport`.

## Contraintes

- Stdlib + `fastapi` + `pydantic` + `httpx` (déjà dans deps base) uniquement.
- Pas de dépendance DB (`sqlalchemy`, `aiosqlite`).
- Fichier cible : `src/{{ file_target }}` (et tests symétriques sous `tests/`).
- Tous les endpoints doivent retourner JSON avec `response_model` explicite.
- Le `DELETE` ne retourne pas de body (status 204).

## Critères de succès

- Tous les tests pytest passent.
- Mypy `--strict` clean sur le nouveau module.
- Coverage du nouveau module ≥ 95 %.
