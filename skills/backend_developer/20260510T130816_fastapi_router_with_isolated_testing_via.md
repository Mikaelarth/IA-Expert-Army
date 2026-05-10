---
summary: 'Pour implémenter un endpoint FastAPI simple et bien testé : isoler la logique
  dans un APIRouter dédié,

  exposer des constantes module-level pour les valeurs stables, et tester le contrat
  HTTP via

  httpx.AsyncClient + ASGITransport (in-process, sans serveur). Les tests vérifient
  systématiquement

  status code, set complet des clés JSON, et invariants spécifiques au domaine.'
tags:
- fastapi
- pytest-asyncio
- httpx
- api-router
- python
sources:
- 20260510T122207_4fd70396_backend_developer
- 20260510T124109_b0d6e871_backend_developer
sources_avg_score: 0.0
extracted_from: 2
skill_id: 20260510T130816_fastapi_router_with_isolated_testing_via
agent: backend_developer
title: FastAPI router with isolated testing via ASGITransport
created_at: '2026-05-10T13:08:16.215703+00:00'
---

## Résumé

Pour implémenter un endpoint FastAPI simple et bien testé : isoler la logique dans un APIRouter dédié,
exposer des constantes module-level pour les valeurs stables, et tester le contrat HTTP via
httpx.AsyncClient + ASGITransport (in-process, sans serveur). Les tests vérifient systématiquement
status code, set complet des clés JSON, et invariants spécifiques au domaine.

## Patterns clés
- Un fichier par endpoint dans src/api/<name>.py exposant un APIRouter (et optionnellement une app FastAPI montant le router)
- Constantes (VERSION, APP_NAME, START_TIME) déclarées au niveau module avec annotation de type explicite
- Tests async avec @pytest.mark.asyncio + httpx.AsyncClient(transport=ASGITransport(app=app)) — pas de serveur réel
- {'Couverture de test triple': '(1) status 200 + set des clés, (2) valeurs constantes contractuelles, (3) format/invariant des champs dynamiques (regex, monotonicité)'}
- Notes finales explicitant les choix ambigus (mode pytest-asyncio, pythonpath, redondances volontaires) pour le Reviewer

## Techniques
- from httpx import ASGITransport, AsyncClient pour tests in-process
- Annotations de type strictes : router: APIRouter, VERSION: str, retours -> dict[str, str] ou Pydantic BaseModel
- Pydantic BaseModel + response_model=... quand le schéma mérite d'être documenté ; dict[str,str] suffit pour endpoints triviaux
- monkeypatch.setattr(subprocess, 'run', ...) pour tester branches d'exception sans dépendance externe
- Imports triés stdlib → tiers → projet, aucun import inutilisé
- Capture exhaustive des exceptions système (FileNotFoundError, CalledProcessError, TimeoutExpired, OSError) avec fallback string 'unknown'
- pyproject.toml : [tool.pytest.ini_options] avec asyncio_mode='auto' et pythonpath=['.']

## Pièges évités
- Ne pas lancer un vrai serveur uvicorn dans les tests (lent, fragile) — ASGITransport suffit
- Ne pas faire d'appel git/subprocess à chaque requête — cache au module-load une seule fois
- Ne pas utiliser > strict pour la monotonicité du temps (utiliser >=) car deux appels in-process peuvent avoir le même timestamp
- Ne pas oublier les __init__.py vides quand pythonpath=['.'] est utilisé sans pip install -e
- Ne pas laisser ambigu le mode pytest-asyncio — soit auto en config, soit @pytest.mark.asyncio explicite (idéalement les deux pour portabilité)

## Template d'exemple

```
# src/api/<name>.py
from fastapi import APIRouter
CONSTANT: str = "value"
router: APIRouter = APIRouter()

@router.get("/<name>")
async def handler() -> dict[str, str]:
    return {"key": CONSTANT, ...}

# tests/test_<name>.py
@pytest.fixture
def app() -> FastAPI:
    a = FastAPI(); a.include_router(router); return a

@pytest.mark.asyncio
async def test_endpoint_contract(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/<name>")
    assert r.status_code == 200
    assert set(r.json().keys()) == {"key", ...}
```

## Sources
- 20260510T122207_4fd70396_backend_developer (score n/a)
- 20260510T124109_b0d6e871_backend_developer (score n/a)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
```yaml
title: FastAPI router with isolated testing via ASGITransport
agent: backend_developer
tags:
  - fastapi
  - pytest-asyncio
  - httpx
  - api-router
  - python
summary: |
  Pour implémenter un endpoint FastAPI simple et bien testé : isoler la logique dans un APIRouter dédié,
  exposer des constantes module-level pour les valeurs stables, et tester le contrat HTTP via
  httpx.AsyncClient + ASGITransport (in-process, sans serveur). Les tests vérifient systématiquement
  status code, set complet des clés JSON, et invariants spécifiques au domaine.
key_patterns:
  - Un fichier par endpoint dans src/api/<name>.py exposant un APIRouter (et optionnellement une app FastAPI montant le router)
  - Constantes (VERSION, APP_NAME, START_TIME) déclarées au niveau module avec annotation de type explicite
  - Tests async avec @pytest.mark.asyncio + httpx.AsyncClient(transport=ASGITransport(app=app)) — pas de serveur réel
  - Couverture de test triple : (1) status 200 + set des clés, (2) valeurs constantes contractuelles, (3) format/invariant des champs dynamiques (regex, monotonicité)
  - Notes finales explicitant les choix ambigus (mode pytest-asyncio, pythonpath, redondances volontaires) pour le Reviewer
techniques:
  - "from httpx import ASGITransport, AsyncClient pour tests in-process"
  - "Annotations de type strictes : router: APIRouter, VERSION: str, retours -> dict[str, str] ou Pydantic BaseModel"
  - "Pydantic BaseModel + response_model=... quand le schéma mérite d'être documenté ; dict[str,str] suffit pour endpoints triviaux"
  - "monkeypatch.setattr(subprocess, 'run', ...) pour tester branches d'exception sans dépendance externe"
  - "Imports triés stdlib → tiers → projet, aucun import inutilisé"
  - "Capture exhaustive des exceptions système (FileNotFoundError, CalledProcessError, TimeoutExpired, OSError) avec fallback string 'unknown'"
  - "pyproject.toml : [tool.pytest.ini_options] avec asyncio_mode='auto' et pythonpath=['.']"
pitfalls_avoided:
  - Ne pas lancer un vrai serveur uvicorn dans les tests (lent, fragile) — ASGITransport suffit
  - Ne pas faire d'appel git/subprocess à chaque requête — cache au module-load une seule fois
  - Ne pas utiliser > strict pour la monotonicité du temps (utiliser >=) car deux appels in-process peuvent avoir le même timestamp
  - Ne pas oublier les __init__.py vides quand pythonpath=['.'] est utilisé sans pip install -e
  - Ne pas laisser ambigu le mode pytest-asyncio — soit auto en config, soit @pytest.mark.asyncio explicite (idéalement les deux pour portabilité)
example_template: |
  # src/api/<name>.py
  from fastapi import APIRouter
  CONSTANT: str = "value"
  router: APIRouter = APIRouter()

  @router.get("/<name>")
  async def handler() -> dict[str, str]:
      return {"key": CONSTANT, ...}

  # tests/test_<name>.py
  @pytest.fixture
  def app() -> FastAPI:
      a = FastAPI(); a.include_router(router); return a

  @pytest.mark.asyncio
  async def test_endpoint_contract(app):
      async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
          r = await c.get("/<name>")
      assert r.status_code == 200
      assert set(r.json().keys()) == {"key", ...}
sources_count: 2
```
```

</details>
