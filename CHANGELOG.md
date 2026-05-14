# Changelog

Tous les changements notables du projet IA-Expert-Army sont documentés ici.

Format inspiré de [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Technical debt

- **Typage mypy** : `strict = true` génère 85 erreurs sur la base (passage à
  mypy 2.0 Sprint UU.5). Désactivé temporairement avec opt-in granulaire
  (`check_untyped_defs`, `warn_unused_ignores`, `no_implicit_optional`,
  `warn_redundant_casts`). Mypy reste lançable via `just typecheck` mais
  n'est PAS dans pre-commit (sinon ça bloque tout). Plan de réactivation :
  module par module via `--strict src/<module>.py`. Cf. dette
  `[tool.mypy]` dans `pyproject.toml`.
- **Couverture meta-mission `verdict?` filter** : `list_recent_meta_missions`
  MCP n'expose pas encore un filtre verdict optionnel (mentionné dans
  ADR-009 "Pour la suite" — pas critique mais nice-to-have).

## [0.2.0] — 2026-05-14 — Phase 6+7 livrées + audit qualité (Sprint UU)

### Added — Sprint UU : Audit qualité + clean-up (session 13)

#### Sprint UU.4 — Boost couverture workflows Research + Creative
- `tests/unit/test_research_creative_workflows.py` (+13 tests symétriques
  aux suites Business/Engineering).
- Coverage Research workflow : **30% → 89%** (+59 pts).
- Coverage Creative workflow : **31% → 88%** (+57 pts).
- **Coverage global : 84% → 90%** (+6 pts).

#### Sprint UU.1 — Mypy clean
- `types-PyYAML` ajouté en dev dep.
- 5 `type: ignore` inutilisés retirés (tracing.py, sandbox/runner.py).
- `Returning Any` corrigé via `cast()` explicite (tracing.py).
- `get_logger` annoté `-> Any` (compromis structlog sans stub propre).
- Mypy 1.5.1 (Python 3.11 global) → mypy 2.0.0 dans le venv via
  `dependency-groups`.

#### Sprint UU.2 — S-rules (sécurité bandit-like)
- `S` ajouté à `[tool.ruff.lint].select`.
- `per-file-ignores` pour tests (S101/S105/S106/S108/S110/S311) et
  scripts (S101) — légitimes par contexte.
- 2× `except: continue` → `log.warning + continue` dans MCP server
  (S112, vrai bug : on perdait silencieusement les erreurs de parsing).
- `noqa` documentés sur findings légitimes : `/tmp` tmpfs sandbox (S108),
  Langfuse localhost health (S310), `git rev-parse` PATH-resolved (S607).

#### Sprint UU.3 — `src/api/` intégré au filet de sécurité
- `tests/test_version.py` + `tests/test_info.py` (12 tests qui passaient
  mais jamais exécutés en CI/pre-commit car hors de `tests/unit/`)
  déplacés vers `tests/unit/test_api_version.py` + `test_api_info.py`.
- Décision : `src/api/` (FastAPI endpoints version/info) gardé comme
  module utilitaire pour intégration future REST.

#### Sprint UU.6 — Release v0.2.0
- Version bumpée 0.1.0 → 0.2.0 dans `pyproject.toml`.
- Section `[Unreleased]` fermée comme `[0.2.0]`.
- Tag git `v0.2.0`.

### Added — Phase 6 validation : autonomous harness (session 13, Sprint C)

#### Sprint C — `scripts/autonomous_run.py` (commit `fcad011`)
- Harness exécutable concrétisant le critère Phase 6 « mission longue
  24h sans dérive, dans budget » du master plan.
- Queue YAML de missions (`data/autonomous_queue_smoke.yml` fourni) +
  loop séquentiel via `MissionRouter`.
- **5 garde-fous** évalués entre chaque mission (pure function testée) :
  1. Budget floor (par défaut $5)
  2. Killswitch clear
  3. Error rate < 30% sur fenêtre glissante N=5
  4. Saturation rate < 20% sur fenêtre glissante N=5
  5. Quality moving average ≥ 0.70 (anti-dérive sémantique)
- Stop gracieux : rapport markdown produit dans `data/autonomous_runs/`,
  exit code 0 (queue épuisée) ou 3 (garde-fou déclenché).
- ADR-010 documente le protocole + alternatives rejetées + procédure
  pour un vrai run 24h.
- **Smoke run validé 3/3 APPROVED** ($1.00, 5 min, quality 0.94 avg).

#### Sprint TT — Daily digest enrichi (commit `bed80fc`)
- Section « Meta-missions cross-guildes (Phase 7) » ajoutée au rapport
  quotidien (count, score moyen, coût/durée cumulés, verdicts, guildes
  traversées + table par meta-mission).
- Helpers `_meta_missions_for_date`, `_compute_meta_stats`.

#### Sprint SS — Engineering repair loop élargi (commit `dde4529`)
- Pattern méta-leçon de Sprint PP appliqué au `Workflow` Engineering.
- Repair loop = Architect v2 → Developer v2 → Reviewer v2 (au lieu de
  Developer seul). Évite les oscillations NEEDS_CHANGES quand le verdict
  porte sur l'architecture.
- +5 tests symétriques de ceux de `BusinessWorkflow`.

### Added — Phase 7 : MetaWorkflow cross-guildes + DevX (session 13)

#### Phase 7 — MetaWorkflow (commits `239ada6`, `bb29a6d`, `f0ccb60`)
- `MetaWorkflow` orchestrant 2–4 sous-missions cross-guildes via
  `MetaDecomposer` (Opus) → `MissionRouter.run(force_guild=...)` →
  agrégation `MetaMissionResult`.
- v1 séquentielle puis v2 parallélisée par niveaux DAG
  (`_level_order` + `asyncio.gather`, -37% durée mesurée sur
  water-tracker).
- Flag `--meta` dans `scripts/run_mission.py` (incompatible avec
  `--apply`/`--validate`/`--guild`).
- **3 missions réelles cross-guildes** validées (water-tracker v1/v2/v3),
  convergence APPROVED après les fixes en cascade.
- Repair loop business élargi : PM + BA + Legal au lieu de BA seul
  (résout les NEEDS_CHANGES éternels où le verdict portait sur le plan
  PM, pas l'analyse BA).
- ADR-009 documentant tous les choix, trade-offs et apprentissages.

#### Sprint OO.bis — Fix saturation (commit `e46c275`)
- `BusinessAnalyst.DEFAULT_MAX_TOKENS` : 6144 → 8192 (incident 7
  référencé dans ADR-005). Première saturation observée sur un repair
  loop, première sur la Business Guild.

#### Sprint QQ — MCP meta-tools (commit `7977516`)
- `list_recent_meta_missions(limit)` et `get_meta_mission_summary(id)`
  exposés via le serveur MCP — symétrie complète avec les outils
  mission single-guild. Le serveur expose désormais **6 outils**.
- Helpers `FileMemory.list_meta_missions()` /
  `write_meta_mission_summary()` / `get_meta_mission_summary()`.

#### DevX (commits `82223cd`, `cd60c45`, `e695924`, `bfc84bd`)
- Pre-commit hooks (`ruff` + `check-yaml/toml` + pytest unit +
  health-check), aligné `ruff-pre-commit v0.15.12` avec le venv.
- Migration `class X(str, Enum)` → `StrEnum` (UP042, Python 3.11+).
- GitHub Actions CI : workflow lint + tests + health-check sur push/PR
  vers `main`. Stratégie DRY (délègue à `.pre-commit-config.yaml`).
- 2 nouveaux outils MCP : `list_recent_missions(limit, guild?)` et
  `get_mission_summary(mission_id)`.

### Added — Polish marathon (sessions 11–12)
- `CHANGELOG.md` (ce fichier).
- ADR-008 : trade-off `read_only=False` du sandbox formalisé.
- `scripts/health_check.py` : validation globale en une commande
  (Python, deps, env, mémoire, Docker, sandbox, Langfuse, Chroma).
- `justfile` : raccourcis cross-platform pour les commandes courantes
  (`just test`, `just health`, `just mine`, etc.).
- Filtre du `DeprecationWarning` chromadb dans `pyproject.toml` pour
  garder les runs de tests propres.

### Fixed
- `BaseAgent.run` effectivement décoré avec `@observe` (la promesse était
  faite mais l'Edit avait silencieusement échoué — régression test
  `test_base_agent_observe.py` lit le fichier source pour vérifier).
- 12 erreurs ruff résiduelles (raise-from, ternary, contextlib.suppress,
  ValidationError typé pour pytest.raises, conventions de naming).

### Stats
- **Tests** : 212 → 294 (+82) en passant Phase 7 + Sprint C + DevX.
- **Skills auto-générées** : 16.
- **ADRs** : 8 → 10.
- **MCP tools** : 2 → 6.
- **Phases couvertes** : 0–7 livrées, **Phase 6 validable** via
  `scripts/autonomous_run.py`.
- **Budget API session 13** : ~$10 (3 missions cross-guildes + 1 smoke
  decomposer + 1 smoke autonomous).

## [0.1.0-rc1] — 2026-05-10 — Open-source ready

### Added

#### Phase 0 — Fondations (commit `cc3f6ca`)
- Structure projet 4 couches + Python 3.12 via `uv` + Docker.
- Settings type-safe (pydantic-settings), structlog, types Pydantic.
- `hello_agent.py` first end-to-end Claude API call.

#### Phase 1 — MVP 4 agents Engineering (commit `ec8cffd`)
- `BaseAgent` + ChiefOrchestrator + SoftwareArchitect + BackendDeveloper
  + CodeReviewer.
- `FileMemory` (markdown + frontmatter) + workflow linéaire.
- 1 mission test `/health` APPROVED 0.93.

#### Phase 1.5 — Polish (commit `f03f480`)
- Parser ligne-à-ligne pour `extract_files` (fix blocs vides).
- Mode `--apply` sécurisé avec whitelist de dossiers.

#### Phase 2 — VectorMemory + RAG (commit `997fbb6`)
- Chroma `PersistentClient` in-process.
- Auto-indexation des épisodes + injection few-shot dans les agents.
- Mission `/version` → l'Architect cite spontanément `/health`.

#### Phase 1.6 + 3 — apply_mission + Sandbox Docker (commit `3e04f9b`)
- `apply_mission.py` pour ré-appliquer une mission archivée.
- `SandboxRunner` Docker isolé (no-net, non-root, mem/cpu/pid limits).
- `infra/docker/sandbox.Dockerfile` + image `iaa-sandbox:latest`.

#### Phase 5 — Pattern mining (commit `e164dc7`)
- `PatternMiner` + `SkillExtractor` (Opus) + `SkillsLibrary`.
- 4 skills Engineering auto-générées dès la 1ʳᵉ exécution.

#### Sprint 1 — Polish + ADRs (commit `62041a4`)
- Propagation `quality_score` aux épisodes.
- Fix YAML doublé dans body skill, recherche sémantique skills.
- ADR-001 à ADR-004.

#### Phase 6 MVP — Garde-fous autonomie (commit `6b04122`)
- `BudgetController` (cap journalier auto-reset).
- `Killswitch` (sentinel file).
- `daily_digest.py` (rapport markdown).

#### Phase 4 — Research Guild + multi-guild routing (commit `9c85f23`)
- ResearchLead + TechWatch + DocumentSynthesizer + ResearchReviewer.
- `MissionRouter` + `HeuristicGuildClassifier`.
- Première démonstration multi-domaine end-to-end.

#### Détection saturation + parser tolérant (commits `b61e3da`, `6dd5bd3`)
- `BaseAgent` détecte `stop_reason="max_tokens"` ou tokens_out ≥ 99% max.
- `extract_yaml` 3-tiers : strict → préprocessing → fallback regex.

#### Creative Guild + Business Guild MVP (commits `44e7d2c`, `83f8b53`)
- ContentStrategist + Copywriter + Editor.
- ProjectManager + BusinessAnalyst + LegalReviewer.
- 4 guildes opérationnelles avec boucle d'apprentissage prouvée par
  citation textuelle.

#### Polish session 5 (commits `62041a4`, `e5a10e5`, `e164dc7`, etc.)
- 6 ADRs structurants (architecture, stack, autonomie, apprentissage,
  saturation, mining).

#### Sprint X — Boucle qualité fermée (commit `d62d260`)
- `run_mission --apply --validate` : agents → code → sandbox pytest
  en UNE commande.
- Module partagé `src/tools/sandbox_validate.py`.
- Mission `/info` APPROVED 0.93 + sandbox 3/3 PASSED.

#### Langfuse v3 stack + MCP server (commit `50a5ffe`)
- Langfuse self-hosted opérationnel sur localhost:3000.
- `src/mcp_servers/memory_search.py` : `search_episodes` +
  `search_skills` exposés via stdio JSON-RPC.

#### Tracing + open-source readiness (commits `581771b`, `7a67bd9`)
- `src/core/tracing.py` : `@observe` opt-in (NO-OP sans credentials).
- `BaseAgent.run` + `MissionRouter.run` instrumentés.
- LICENSE MIT + CONTRIBUTING.md + README pro avec badges.
- Fix régression : décorateur manquant sur `BaseAgent.run` corrigé +
  test de régression qui inspecte le fichier source.

### Stats à la sortie 0.1.0-rc1

- **38 commits Git** sur `main`
- **214 tests pytest** verts
- **4 guildes opérationnelles** (Engineering, Research, Creative, Business)
- **15 missions APPROVED** en condition réelle (score moyen 0.89)
- **14 skills auto-générées** (4 Engineering + 4 Research + 3 Creative
  + 3 Business)
- **8 ADRs** structurants
- **~$19** d'API consommés sur l'ensemble du développement

## [0.0.x] — Pré-historique

Sessions de bootstrap (cf. plan stratégique
`C:\Users\HP\.claude\plans\bonjour-je-suis-mke-snoopy-sundae.md`) :
définition de la vision, choix de stack, ADRs initiaux.

---

[Unreleased]: https://github.com/MikaelArth/IA-Expert-Army/compare/v0.1.0-rc1...HEAD
[0.1.0-rc1]: https://github.com/MikaelArth/IA-Expert-Army/releases/tag/v0.1.0-rc1
