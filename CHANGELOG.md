# Changelog

Tous les changements notables du projet IA-Expert-Army sont documentés ici.

Format inspiré de [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — Polish marathon (sessions 11–12)
- `CHANGELOG.md` (ce fichier).
- ADR-008 : trade-off `read_only=False` du sandbox formalisé.
- `scripts/health_check.py` : validation globale en une commande
  (Python, deps, env, mémoire, Docker, sandbox, Langfuse, Chroma).
- `justfile` : raccourcis cross-platform pour les commandes courantes
  (`just test`, `just health`, `just mine`, etc.).
- Filtre du `DeprecationWarning` chromadb dans `pyproject.toml` pour
  garder les runs de tests propres.

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
