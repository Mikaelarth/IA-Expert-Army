# scripts/ — inventaire et statut

Tous les scripts CLI Python à la racine de `scripts/`. Chacun a un statut
explicite : `STABLE` (utilisé en daily ops), `DEV` (outil de développement,
pas pour la prod), ou `INFRA` (jobs schedulés, cf. ADR-024).

Pour découvrir les options d'un script :

```bash
uv run python scripts/<script>.py --help
```

## Inventaire (22 scripts, 2026-05-22)

### Cycle de vie d'une mission

| Script | Statut | Recipe `just` | Rôle |
|---|---|---|---|
| [`run_mission.py`](run_mission.py) | STABLE | `just mission` | Lance une mission (router → guilde → archivage). C'est l'entrée principale CLI. |
| [`apply_mission.py`](apply_mission.py) | STABLE | `just apply` | Applique sur disque les fichiers d'une mission archivée + valide en sandbox. |
| [`autonomous_run.py`](autonomous_run.py) | STABLE | _aucune_ | Boucle autonome qui dépile des missions d'une queue YAML — exécuté typiquement en cron VPS. Pas de recette `just` parce que c'est un mode opérateur, pas un usage interactif. Cf. ADR-010 §autonomous. |

### Observabilité / état du système

| Script | Statut | Recipe `just` | Rôle |
|---|---|---|---|
| [`health_check.py`](health_check.py) | STABLE | `just health` / `just health-quick` | Diagnostic 18 checks (Ollama, FileMemory, Chroma, sandbox, budget…). |
| [`check_setup.py`](check_setup.py) | STABLE | _aucune_ | Vérifie le setup initial (clés API legacy, structure data/). À retirer post-bascule Ollama complète (cf. ADR-025). |
| [`check_sandbox.py`](check_sandbox.py) | STABLE | `just sandbox-build` (avec `--build`) | Build + smoke-test l'image `iaa-sandbox:latest`. |
| [`daily_digest.py`](daily_digest.py) | STABLE | `just digest` | Génère un digest agrégé des missions du jour. |

### Garde-fous opérateur

| Script | Statut | Recipe `just` | Rôle |
|---|---|---|---|
| [`budget.py`](budget.py) | STABLE | `just budget` | Lit/réinitialise l'état du `BudgetController` (data/budget_state.json). |
| [`killswitch.py`](killswitch.py) | STABLE | `just killswitch-on` / `just killswitch-off` | Engage/dégage la sentinelle data/.killswitch (refus de tout nouvelle mission). |
| [`approvals.py`](approvals.py) | STABLE | _aucune_ | Décide manuellement d'une demande d'approbation en attente (HITL, cf. ADR-014). |

### Apprentissage continu

| Script | Statut | Recipe `just` | Rôle |
|---|---|---|---|
| [`nightly_learning.py`](nightly_learning.py) | INFRA | _aucune_ | Job nightly qui lance PatternMiner sur les épisodes récents et écrit les skills extraites. Exécuté typiquement en cron VPS (3 h du matin). |
| [`reindex_episodes.py`](reindex_episodes.py) | DEV | `just reindex` | Re-construit l'index Chroma depuis les `.md` disque. À utiliser après corruption du vector store. |

### Backup / disaster recovery

| Script | Statut | Recipe `just` | Rôle |
|---|---|---|---|
| [`backup.py`](backup.py) | STABLE | `just backup` / `just backup-full` | Crée un tarball horodaté de data/ + skills/ dans data/backups/. |
| [`restore.py`](restore.py) | STABLE | `just restore` | Restaure depuis un tarball. Mesuré 3.99 s end-to-end Session 6. |

### Probes et outils de mesure (Session 5)

| Script | Statut | Recipe `just` | Rôle |
|---|---|---|---|
| [`probe_reviewer.py`](probe_reviewer.py) | DEV | _aucune_ | Mesure directement la résorption du bug Session 2 (Reviewer v0.3.0 doit retourner NEEDS_CHANGES sur le code Session 2). Utilisé par la page GUI **🔬 Probes**. |
| [`probe_sandbox.py`](probe_sandbox.py) | DEV | _aucune_ | Smoke test rapide de la sandbox Docker (pytest dans un container isolé). |
| [`sandbox_run_pytest.py`](sandbox_run_pytest.py) | DEV | _aucune_ | Wrapper bas niveau qui lance pytest dans la sandbox sur un workspace donné. Utilisé par `apply_mission --validate`. |

### Smoke tests dev

| Script | Statut | Recipe `just` | Rôle |
|---|---|---|---|
| [`hello_agent.py`](hello_agent.py) | DEV | `just hello` | 1er appel Ollama de validation post-bascule. |
| [`smoke_meta_decomposer.py`](smoke_meta_decomposer.py) | DEV | _aucune_ | Smoke test du `MetaDecomposer` (ADR-009) sur une mission cross-guildes type. |

### GUI / infrastructure

| Script | Statut | Recipe `just` | Rôle |
|---|---|---|---|
| [`run_gui.py`](run_gui.py) | STABLE | `just gui` | Launcher Streamlit (subprocess vers `streamlit run src/gui/app.py`). |
| [`run_memory_search_mcp.py`](run_memory_search_mcp.py) | STABLE | _aucune_ | MCP server (6 tools) — exposable à Claude Desktop / Cursor. Cf. README §MCP. |
| [`audit_codebase.py`](audit_codebase.py) | STABLE | `just audit` / `just audit-strict` | 5 règles anti-patterns (FILE_TOO_LONG, NO_DOCSTRING…). Lancé en CI + pre-commit. |

## Politique de maintenance

- Tout script ajouté doit recevoir un **statut** dans ce README dès son
  premier commit.
- Un script `DEV` qui n'a pas tourné depuis 6 mois est candidat à
  l'archivage sous `scripts/_archive/`.
- Les scripts `INFRA` doivent être documentés dans un ADR ou dans
  `docs/operations.md` (cron expressions, périodicité, post-conditions).
