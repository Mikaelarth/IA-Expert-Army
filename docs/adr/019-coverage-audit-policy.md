# ADR-019 — Politique de couverture de tests : audit honnête + seuils par module

**Statut :** Accepted
**Date :** 2026-05-15
**Commits associés :** Sprint JJJ

## Contexte

Le README affichait `coverage-90%` sans qu'on ait jamais lancé `pytest --cov` complet sur le projet récent. Le risque : le badge devient un **mensonge non vérifié** (anti-pattern classique d'un projet jeune qui croît vite).

Au déclenchement Sprint JJJ, le vrai chiffre était **91% sur 491 tests** — le badge tenait, mais 4 modules étaient sous-couverts à un niveau préoccupant :

| Module | Coverage | Pourquoi c'est un problème |
|---|---|---|
| `src/core/tracing.py` | 64% | Module critique pour observabilité prod ; path Langfuse actif jamais testé |
| `src/mcp_servers/memory_search.py` | 73% | Serveur MCP exposé à des LLMs tiers, surface d'erreur publique |
| `src/sandbox/runner.py` | 84% | Garde-fou sécurité ; error paths Docker non testés |
| `src/tools/sandbox_validate.py` | 79% | Helper visible au user (rendu console) |

## Décision

### 1. Mesurer avant d'annoncer

Le badge `coverage-XX%` du README est **mesuré explicitement** avant chaque MAJ, via :
```bash
uv run pytest --cov=src --cov-report=term-missing tests/unit/ tests/integration/
```

Si le projet doit revendiquer X% de couverture, on doit avoir vu le chiffre dans la sortie pytest récente (pas une estimation, pas un souvenir).

### 2. Seuils minimaux par catégorie de module

| Catégorie | Seuil minimal | Justification |
|---|---|---|
| `src/core/*` | ≥ 90% | Modules fondamentaux ; tout bug ici impacte tout le système |
| `src/orchestrator/*` | ≥ 85% | Logique métier centrale ; complexité élevée, chemins multiples |
| `src/sandbox/*` | ≥ 90% | Garde-fou sécurité ; un bug = vuln runtime |
| `src/tools/*` | ≥ 90% | Petits modules utilitaires ; pas d'excuse pour ne pas tester |
| `src/mcp_servers/*` | ≥ 85% | Surface publique exposée à des LLMs externes |
| `src/guilds/*` | ≥ 85% | Workflows guildes, déjà couverts via les tests d'intégration |
| `src/learning/*` | ≥ 85% | Mining + RAG ; logique de scoring testable |
| `src/api/*` | ≥ 90% | Endpoints publics (FastAPI) |

**Global** : ≥ 90%.

Si un module passe sous le seuil, soit on remonte la couverture, soit on documente pourquoi (par exemple : "main()/serve() bloquent sur stdin, impossible à tester unitaire sans démarrer un client MCP réel" → accepté avec note).

### 3. Action Sprint JJJ — combler les 4 trous identifiés

**3a — `tracing.py` 64→89%** (+25 pts)
- Ajout 5 tests couvrant le **path actif Langfuse** jamais testé avant (mock du SDK Langfuse via `monkeypatch.setattr` + faux module dans `sys.modules`).
- Couvre désormais : init avec credentials valides + SDK importable, observe forward vers décorateur Langfuse, fallback v2/v3, exception au moment de `Langfuse(...)`.
- Restant : lignes 51-59 (`_try_import_langfuse` body avec import langfuse). Non-testable proprement sans installer langfuse réel — accepté.

**3b — `memory_search.py` 73→85%** (+12 pts)
- Ajout 11 tests couvrant les error paths jamais touchés :
  - Frontmatter corrompu skippé (et loggé) au lieu de crash
  - Exception top-level dans chaque handler (`list_recent_missions`, `get_mission_summary`, `list_recent_meta_missions`, `get_meta_mission_summary`)
  - `search_skills` path "with query" (sémantique vs récence)
  - `serve` smoke test (existence + type async)
- Restant : `serve()` body 507-509 (`async with stdio_server()` bloque sur stdin). Non-testable unitairement. Accepté.

**3c — `sandbox/runner.py` 84→95%** (+11 pts)
- Ajout 5 tests couvrant :
  - `SandboxUnavailable` raised si `docker.from_env()` lève `DockerException`
  - `image_exists` False sur `DockerException` autre que `ImageNotFound`
  - `image_exists` avec override `image=` custom
  - Cleanup `container.remove()` lève `NotFound` (déjà gone) → swallow silencieux
  - Cleanup lève `DockerException` (perm) → log warning, run termine normalement
- Restant : ligne 35-38 (try/except ImportError sur l'import docker au top du module). Non-testable sans manipulation lourde de `sys.modules`. Accepté.

**3d — `sandbox_validate.py` 79→100%** (+21 pts)
- Ajout 6 tests couvrant `print_sandbox_result` :
  - Panel vert sur exit_code=0
  - Panel rouge sur exit_code≠0 + section STDERR
  - Pas de section STDOUT/STDERR si vides
  - Troncature stdout > 80 lignes (garde les 80 dernières)
  - Troncature stderr > 2000 chars (garde les 2000 derniers)
  - Default Console créé si `console=None`

### 4. Politique pour le futur

- **Nouveau module avec < seuil de sa catégorie : PR refusée** (sauf justification écrite dans la description PR).
- **Régression de couverture > 2 pts sur un module : PR refusée** (le CI affichera le delta).
- **Lancement périodique de l'audit complet** : à chaque release majeure (v0.X.0) ou tous les 10 sprints.
- **Tests d'erreur paths sont des tests de première classe** — pas des nice-to-have. Un module qui ne teste que les happy paths n'est PAS prêt pour la prod.

## Conséquences

**Positives** :
- Badge README désormais **mesuré, pas estimé** → 93% (vrai chiffre observable)
- 4 modules critiques renforcés (+27 tests régression)
- Politique explicite empêche la dérive future
- Habitude installée : `pytest --cov` AVANT chaque commit de release

**Négatives** :
- Seuils par catégorie ajoutent une étape de revue PR (mitigation : CI peut automatiser le check)
- Les tests d'erreur paths sont parfois pénibles à écrire (mocks complexes)
- 100% de couverture **n'est pas un objectif** — la qualité d'un test compte plus que sa présence. Un test mécanique sans assertion réelle vaut zéro.

**À surveiller** :
- Que la couverture **ne baisse pas** silencieusement sur les futurs sprints
- Que les modules à 85% restent stables (vector_memory, file_memory, pattern_miner sont solides)

## Modules restant sous-couverts (acceptés)

Ces lignes ne sont **pas comblables proprement** et sont acceptées comme exceptions :

| Module | Lignes | Pourquoi non-comblable |
|---|---|---|
| `src/core/tracing.py:51-59` | 9 | `_try_import_langfuse` body — nécessiterait d'installer langfuse réel |
| `src/core/logging.py:18, 34-35` | 3 | `sys.stdout.reconfigure(...)` Windows-specific au boot |
| `src/mcp_servers/memory_search.py:507-509` | 3 | `serve()` body bloque sur `stdio_server()` (stdin) |
| `src/sandbox/runner.py:35-38, 90` | 5 | Import `docker` au top + branche `_DOCKER_AVAILABLE=False` |
| `src/guilds/*/workflow.py:~10 lignes/module` | ~30 | Branches de repair loop très spécifiques |

**Total accepté** : ~50 lignes / 2961 → ~1.7% du codebase. Acceptable.

## Alternatives considérées

1. **Viser 100% à tout prix** : refusé. Anti-pattern — produit des tests vides pour cocher la case. La culture du test doit être "tester ce qui peut casser", pas "couvrir chaque ligne".

2. **Lancer `coverage` en mode strict (`fail_under = 90`) dans pyproject.toml** : à envisager dans un futur sprint (Sprint KKK ?). Pour l'instant on garde la politique en revue manuelle pour éviter les faux positifs sur des tests intégration lents.

3. **Mesurer aussi la couverture des branches (`--cov-branch`)** : pertinent mais ajoute du bruit. À considérer après stabilisation des seuils par module.

## Sources

- Output `pytest --cov=src --cov-report=term-missing` du 2026-05-15 (commit dcdd2fd) — base de référence 91%
- Output du 2026-05-15 (commit Sprint JJJ) — 93% après le sprint
- Coverage best practices (Martin Fowler, "TestCoverage" — https://martinfowler.com/bliki/TestCoverage.html)
- ADR-005 (saturation detection) — pattern "test ce qui peut effectivement casser en prod"
