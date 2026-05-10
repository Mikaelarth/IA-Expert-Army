---
summary: 'Pour concevoir un endpoint FastAPI simple (metadata, health, version), produire
  une spec YAML structurée

  couvrant understanding/tech_choices/components/data_flow/tests/risks. Privilégier
  un module autonome avec

  APIRouter exporté, constantes module-level pour valeurs calculées une fois, et tests
  httpx+ASGITransport.'
tags:
- fastapi
- api-design
- router
- testing
- pydantic
sources:
- 20260510T122153_4fd70396_software_architect
- 20260510T124045_b0d6e871_software_architect
sources_avg_score: 0.0
extracted_from: 2
skill_id: 20260510T130754_fastapi_metadata_router_design_spec
agent: software_architect
title: FastAPI metadata router design spec
created_at: '2026-05-10T13:07:54.243579+00:00'
---

## Résumé

Pour concevoir un endpoint FastAPI simple (metadata, health, version), produire une spec YAML structurée
couvrant understanding/tech_choices/components/data_flow/tests/risks. Privilégier un module autonome avec
APIRouter exporté, constantes module-level pour valeurs calculées une fois, et tests httpx+ASGITransport.

## Patterns clés
- Spec YAML en 6 sections fixes (understanding, tech_choices, components, data_flow, tests_to_write, risks) — structure systématique et complète
- {'Un fichier = un router isolé dans src/api/<feature>.py exposant `router': "APIRouter` montable sur l'app principale"}
- Calculs coûteux (subprocess, time.monotonic baseline) capturés au chargement du module dans des constantes globales, pas à chaque requête
- Spécifier explicitement les types de retour (Pydantic model OU dict[str, str]) et le contrat de schéma JSON dans la spec
- Tests via httpx.AsyncClient + ASGITransport + @pytest.mark.asyncio (pattern in-process sans socket réel)
- Section risks lie chaque risque à sa mitigation concrète (timeout, fallback, regex souple, cast explicite)

## Techniques
- from fastapi import APIRouter; router = APIRouter() puis @router.get('/path')
- httpx>=0.27 : AsyncClient(transport=ASGITransport(app=app), base_url='http://test')
- @pytest.mark.asyncio explicite (pas de dépendance à asyncio_mode=auto)
- Constantes UPPERCASE module-level (VERSION, APP_NAME, START_TIME, _GIT_COMMIT) calculées à l'import
- subprocess.run avec timeout court (2s) + try/except large (FileNotFoundError, CalledProcessError, TimeoutExpired, OSError) → fallback 'unknown'
- Cast explicite float() en ceinture+bretelles même si Pydantic coerce déjà
- Stdlib first (platform, time.monotonic, subprocess) avant lib tierce

## Pièges évités
- Appeler subprocess/git à chaque requête au lieu de cacher au chargement
- Utiliser AsyncClient(app=...) déprécié au lieu d'ASGITransport explicite
- Assertions trop strictes sur formats variables (python_version exact, uptime > 0 au lieu de >= 0)
- Oublier le timeout sur subprocess.run → blocage potentiel
- Manquer les __init__.py / pythonpath qui empêchent `from src.api.x import ...` en test
- Coupler le router à l'app principale (perte de testabilité isolée)

## Template d'exemple

```
understanding: |
  <objectif + contraintes + hypothèses sur la stack>
tech_choices:
  - <lib/pattern> — <justification 1 ligne>
components:
  - name: <router|model|test>
    path: src/api/<feature>.py
    responsibility: <1 phrase>
    public_interface: |
      <signature/snippet 5-10 lignes>
data_flow: |
  1. <chargement module>
  2. <requête → handler>
  3. <test in-process>
tests_to_write:
  - <cas nominal : status + schéma>
  - <verrous contractuels sur valeurs/formats>
risks:
  - <risque> → <mitigation concrète>
```

## Sources
- 20260510T122153_4fd70396_software_architect (score n/a)
- 20260510T124045_b0d6e871_software_architect (score n/a)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
```yaml
title: FastAPI metadata router design spec
agent: software_architect
tags:
  - fastapi
  - api-design
  - router
  - testing
  - pydantic
summary: |
  Pour concevoir un endpoint FastAPI simple (metadata, health, version), produire une spec YAML structurée
  couvrant understanding/tech_choices/components/data_flow/tests/risks. Privilégier un module autonome avec
  APIRouter exporté, constantes module-level pour valeurs calculées une fois, et tests httpx+ASGITransport.
key_patterns:
  - Spec YAML en 6 sections fixes (understanding, tech_choices, components, data_flow, tests_to_write, risks) — structure systématique et complète
  - Un fichier = un router isolé dans src/api/<feature>.py exposant `router: APIRouter` montable sur l'app principale
  - Calculs coûteux (subprocess, time.monotonic baseline) capturés au chargement du module dans des constantes globales, pas à chaque requête
  - Spécifier explicitement les types de retour (Pydantic model OU dict[str, str]) et le contrat de schéma JSON dans la spec
  - Tests via httpx.AsyncClient + ASGITransport + @pytest.mark.asyncio (pattern in-process sans socket réel)
  - Section risks lie chaque risque à sa mitigation concrète (timeout, fallback, regex souple, cast explicite)
techniques:
  - "from fastapi import APIRouter; router = APIRouter() puis @router.get('/path')"
  - "httpx>=0.27 : AsyncClient(transport=ASGITransport(app=app), base_url='http://test')"
  - "@pytest.mark.asyncio explicite (pas de dépendance à asyncio_mode=auto)"
  - "Constantes UPPERCASE module-level (VERSION, APP_NAME, START_TIME, _GIT_COMMIT) calculées à l'import"
  - "subprocess.run avec timeout court (2s) + try/except large (FileNotFoundError, CalledProcessError, TimeoutExpired, OSError) → fallback 'unknown'"
  - "Cast explicite float() en ceinture+bretelles même si Pydantic coerce déjà"
  - "Stdlib first (platform, time.monotonic, subprocess) avant lib tierce"
pitfalls_avoided:
  - Appeler subprocess/git à chaque requête au lieu de cacher au chargement
  - Utiliser AsyncClient(app=...) déprécié au lieu d'ASGITransport explicite
  - Assertions trop strictes sur formats variables (python_version exact, uptime > 0 au lieu de >= 0)
  - Oublier le timeout sur subprocess.run → blocage potentiel
  - Manquer les __init__.py / pythonpath qui empêchent `from src.api.x import ...` en test
  - Coupler le router à l'app principale (perte de testabilité isolée)
example_template: |
  understanding: |
    <objectif + contraintes + hypothèses sur la stack>
  tech_choices:
    - <lib/pattern> — <justification 1 ligne>
  components:
    - name: <router|model|test>
      path: src/api/<feature>.py
      responsibility: <1 phrase>
      public_interface: |
        <signature/snippet 5-10 lignes>
  data_flow: |
    1. <chargement module>
    2. <requête → handler>
    3. <test in-process>
  tests_to_write:
    - <cas nominal : status + schéma>
    - <verrous contractuels sur valeurs/formats>
  risks:
    - <risque> → <mitigation concrète>
sources_count: 2
```
```

</details>
