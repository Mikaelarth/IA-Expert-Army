# Changelog

Tous les changements notables du projet IA-Expert-Army sont documentés ici.

Format inspiré de [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.0] — 2026-05-22 — Audit zéro-dette : 21 findings résorbés en 4 vagues

Version dédiée à la résorption méthodique de la dette technique identifiée par
l'audit d'introspection du 2026-05-22 (cf. réponse "étude rigoureuse" dans la
session de release). **21 findings traités**, structurés en 4 commits cohérents :

### Vague 1 — Quick wins cosmétiques + DX (8 findings)

- **E1** README.md L235 disait « 5 pages » Streamlit → corrigé en « 6 pages »
- **E2** docs/adr/README.md indexe désormais ADR-025/026/027/028
- **E4** pyproject.toml retire ruff/mypy du PEP 621 — source de vérité unique [dependency-groups]
- **E5** justfile `gui` ajoute `uv sync --group gui --quiet` (idempotent)
- **E6** scripts/README.md créé : inventaire des 22 scripts avec statut STABLE/DEV/INFRA
- **E8** Commentaire whitelist PatternMiner clarifié (security_auditor transverse, prompt dans orchestrator/)
- **L6** BudgetController.__init__ émet un warning si `daily_budget <= 0` (rappel mode no-op)
- **L7** mypy activé en pre-commit, scope `src/core/` (plan d'extension progressive documenté)

### Vague 2 — Bugs latents (3 findings)

- **E3** chromadb aligné partout sur >=1.5.9 (deps base, optional `memory`, docker-compose 1.0.13)
- **L11** PatternMiner dédup : nouveau `_already_mined_sources()` exclut les épisodes déjà sourceurs d'une skill
- **L12** Nouveau `tests/integration/test_migrate_invariants.py` (5 tests cross-plateforme) — complète `test_migrate_vps.py` qui skip sur Windows

### Vague 3 — Carences structurelles (6 findings)

- **L8** CI ajoute un step `docker build sandbox.Dockerfile` (validation Dockerfile, pas de run)
- **L5** Filtre self-referential skills : `sources_mission_ids` persisté + `exclude_mission_ids` dans `search_skills`, câblé dans `BaseAgent._retrieve_skills`
- **L4** `nightly_learning.py --git-commit` : commit auto des skills extraites, traçabilité + rollback granulaire
- **L2** Quality Guardian sémantique clarifiée — nouveau property `qg_blocks_release` (informatif, n'override jamais `final_verdict`)
- **L1** HITL approvals câblé dans `apply_files()` via paramètre `approval_store` optionnel (audit trail sur overwrite avec `force=True`)
- **L9** Nouveau `LLMGuildClassifier` (Qwen 14B) avec fallback automatique sur héuristique ; opt-in via `Settings.use_llm_classifier`

### Vague 4 — Documentation + tests E2E (3 findings)

- **E7** [ADR-028](docs/adr/028-langfuse-self-hosted-deferred.md) — Langfuse self-hosted v3 officiellement gelé (cloud uniquement supporté), docker-compose annoté DEFERRED avec conditions de réactivation
- **E9** Sessions 1 & 3 documentées (`docs/sessions/session-1-test-suite-stabilization.md` et `session-3-fiction-cleanup.md`)
- **L3** Nouveau `tests/integration/test_e2e_ollama_live.py` (2 tests slow, opt-in `OLLAMA_E2E=1`) + workflow `.github/workflows/nightly-e2e.yml` (cron quotidien 3h UTC + manual dispatch)

### Findings non-corrigés (analyse intentionnelle)

- **L10 (chemins d'erreur API)** : déjà couvert par `test_api_version.py:67-100` (4 chemins de fallback testés). Le rapport audit a sur-estimé le risque.

### Métriques release

- Tests : **616 passing** (+13), 6 skipped (suite "fast"), 2 slow opt-in (nightly E2E)
- Coverage : maintenue ≥ 90 % (la cible `fail_under=90` reste)
- ADRs : 27 → **28** (ADR-028 Langfuse deferred)
- Sessions documentées : 4 → **6** (sessions 1 et 3 ajoutées)
- mypy `src/core/` : type-clean (0 erreur, hook pre-commit actif)
- Audit codebase : **0 finding**

### Décisions stratégiques tranchées

| ID | Question | Décision |
|---|---|---|
| L1 HITL | Câbler ou retirer ? | **Câblé** non-bloquant sur `apply_files --force` ; rétrocompat 100% (sans `approval_store`, comportement inchangé) |
| L2 QG | Informatif ou bloquant ? | **Informatif clarifié** (property `qg_blocks_release` pour les callers prudents). Migration vers bloquant = bump majeur, pas avant. |
| L9 Classifier | LLM ou heuristique ? | **Les deux** — opt-in via `Settings.use_llm_classifier`. Fallback automatique. |
| E7 Langfuse v3 | Continuer le debug ou geler ? | **Gelé** (ADR-028). Cloud Langfuse = canal recommandé. |

### Limites connues (post-v0.7.0)

- Le LLM classifier ajoute ~0.5-2 s au routage si activé. Sur missions très longues (20-40 min), le surcoût relatif est négligeable mais à connaître.
- L'audit trail HITL via `apply_files` n'est appelé QUE si le caller passe un `approval_store`. Ni `apply_mission.py` ni la GUI ne le font par défaut — c'est volontaire pour la rétrocompat. À câbler dans un prochain sprint si on veut un audit trail systématique.
- Nightly E2E Ollama : sur GitHub-hosted runners, les tests skip silencieusement (Ollama absent). Pour validation réelle, run sur self-hosted runner avec Ollama installé ou en local via `OLLAMA_E2E=1 uv run pytest -m slow`.

## [0.6.0] — 2026-05-21 — Setup Wizard click-to-go (ADR-027)

Onboarding zéro-terminal : tout le diagnostic + tous les fixes faisables sans
élévation administrateur sont accessibles depuis une nouvelle page GUI
**🛠 Setup**. Pour les composants qui exigent un installeur système (Ollama,
Docker Desktop, uv), un bouton ouvre la page de téléchargement officielle —
on guide, on n'installe pas à la place de l'OS.

### Added

- **Page `0_🛠_Setup.py`** (premier élément de la sidebar Streamlit, préfixe `0_`)
  qui affiche en temps réel l'état de 10 composants et propose une action
  par composant manquant/arrêté :
  1. Python ≥ 3.12 (toujours OK puisque la GUI tourne)
  2. `uv` (bouton **Télécharger uv** → URL officielle)
  3. Ollama installé (bouton **Télécharger Ollama**)
  4. Ollama daemon démarré (bouton **▶ Démarrer le daemon** → fork `ollama serve` détaché)
  5-7. 3 modèles Qwen2.5 (bouton **⬇ Pull `<nom>`** → `POST /api/pull` en streaming avec barre de progression)
  8. Docker daemon (bouton **▶ Démarrer Docker Desktop** sur Windows)
  9. Image sandbox `iaa-sandbox:latest` (bouton **🐳 Build l'image** → `docker build` avec log live)
  10. Fichier `.env` (bouton **📄 Créer `.env`** → copie depuis `.env.example`)
- **Service `src/gui/services/setup_runner.py`** qui concentre toute la logique
  hors-UI : 10 détections (`detect_all()`), 5 actions (`start_ollama_daemon`,
  `pull_model` streaming, `build_sandbox_image` streaming, `create_env_from_example`,
  `start_docker_desktop`), helpers `read_env_content` / `write_env_content` pour
  l'éditeur inline.
- **Éditeur `.env` inline** dans la page Setup — modifier `MODEL_STRATEGIC` ou
  `DAILY_BUDGET_USD` sans quitter la GUI (relance Streamlit pour appliquer).
- **18 tests unitaires** dans `tests/unit/test_setup_runner.py` couvrant chaque
  détecteur en mockant `urlopen` et `shutil.which` (jamais de subprocess
  réel ni de pull Ollama dans les tests).
- **1 smoke test AppTest** dans `tests/unit/test_gui_smoke.py::test_page_setup_renders`
  qui vérifie que la page render même sur une machine sans Ollama/Docker.
- **ADR-027** documentant la décision, le scope réaliste (auto-pull, build,
  start daemon faisable sans UAC) vs hors-périmètre (auto-install Ollama
  ou Docker Desktop = UAC requis, donc on délègue à l'URL officielle).

### Changed

- Version `0.5.0` → `0.6.0` (minor : nouvelle feature majeure, pas de breaking).
- `mkdocs.yml` : nav enrichie avec ADR-027.

### Comment l'utiliser

```bash
uv sync --group gui      # une seule fois
just gui                 # lance Streamlit
```

Puis ouvre `http://127.0.0.1:8501/Setup` — la page Setup montre directement
ce qui manque et propose les actions adaptées.

### Limites connues / Phase 2

- Pas d'auto-install d'Ollama ni de Docker Desktop : requiert UAC sur Windows,
  fragile cross-version. Le bouton **Télécharger** ouvre l'URL officielle.
- Le pull d'un modèle 32B (~20 Go) prend plusieurs heures sur ADSL. Fermer
  la page Streamlit **n'interrompt pas** le pull côté daemon Ollama — il
  faut `ollama stop` dans un terminal pour annuler proprement.
- Après édition de `.env`, il faut relancer Streamlit pour que
  `get_settings()` recharge (`@lru_cache` ne se purge pas tout seul).

## [0.5.0] — 2026-05-21 — Interface GUI Streamlit (ADR-026)

Première version avec interface graphique. Le projet reste 100 % utilisable
en CLI ; la GUI est une couche **opt-in** qui n'ajoute aucune dépendance au
parcours utilisateur par défaut.

### Added

- **5 pages Streamlit multipages** dans `src/gui/pages/` :
  - 🚀 **Mission** — formulaire (titre + description + guild override + `--apply` + `--validate` + `--force`) avec spinner pendant les 20-40 min de génération Qwen 32B local, affichage du verdict, score, fichiers écrits, résultat sandbox.
  - 📜 **Historique** — liste filtrable (par guilde, par verdict) des missions archivées dans `data/memory/missions/*.md`, avec détail au clic.
  - 🧠 **Skills** — explorateur des skills auto-extraites par agent, avec body markdown complet.
  - 🏥 **Health** — lance `scripts/health_check.py --quick` (ou complet avec Docker+Ollama) en subprocess + affichage table OK/WARN/FAIL/SKIP.
  - 🔬 **Probes** — lance `probe_reviewer.py` et `probe_sandbox.py` à la demande + browser des probes archivées dans `data/probes/`.
- **2 services partagés** dans `src/gui/services/` :
  - `memory_browser.py` — wrappers FileMemory pour list/detail missions+skills, parsing frontmatter YAML, formatage durée/datetime.
  - `mission_runner.py` — wrap MissionRouter avec `MissionRunRequest` / `MissionRunOutcome` consolidé (incl. apply + sandbox).
- **`scripts/run_gui.py`** — launcher qui invoque `streamlit run src/gui/app.py` en subprocess (Streamlit a besoin du fichier app comme entry direct pour découvrir le dossier `pages/`).
- **`just gui`** — recipe pour lancer la GUI en une commande.
- **8 smoke tests** dans `tests/unit/test_gui_smoke.py` via `streamlit.testing.v1.AppTest` — chaque page render sans exception + services partagés valident leur output.
- **ADR-026** — décision d'adopter Streamlit (alternatives évaluées : FastAPI+React, Gradio, Textual, tkinter).

### Changed

- `pyproject.toml` : nouveau groupe `[dependency-groups].gui` avec `streamlit>=1.40.0`. Opt-in via `uv sync --group gui` (~30 packages, ~50 Mo). La CLI fonctionne sans Streamlit installé.
- `justfile` : recipe `gui` ajoutée.
- Version `0.4.1` → `0.5.0` (minor : nouvelle feature majeure, pas de breaking change).

### Usage

```bash
uv sync --group gui                  # installe streamlit + deps (à faire une fois)
just gui                              # ou: uv run python scripts/run_gui.py
# Ouvre http://127.0.0.1:8501 dans le navigateur
```

### Architecture & sécurité

- **Pas de couche REST** entre GUI et backend. Streamlit tourne dans le même process Python, importe directement `MissionRouter`, `FileMemory`, `SkillsLibrary`. Choix assumé pour usage perso (cf. ADR-026).
- **Bind localhost only** par défaut (`--server.address 127.0.0.1`). Pas d'auth (usage perso).
- **Pas de streaming live des logs en MVP** : spinner bloquant pendant les 20-40 min de génération. Phase 2 ajoutera `st.status` + log streaming si besoin (action tracée dans ADR-026).

### Limites connues / Phase 2

- Le formulaire Mission bloque l'UI pendant la génération (spinner). Tu peux ouvrir un autre onglet entre-temps, mais pas relancer une mission tant que la première n'a pas fini.
- Pas d'édition de prompts depuis l'UI (faut éditer `prompts/**/*.md` à la main).
- Pas de mode autonome (queue) dans l'UI — faut continuer à utiliser `scripts/autonomous_run.py`.
- Pas d'auth multi-utilisateur.

Toutes adressables si un besoin concret apparaît.

## [0.4.1] — 2026-05-21 — Correctif dette CI tooling (post-livraison v0.4.0)

Patch release qui adresse la cause racine des 3 runs CI échoués
immédiatement après le merge `feat/ollama-backend` → `main` :

- Ruff vivait dans `[project.optional-dependencies].dev` (PEP 621 legacy)
  mais PAS dans `[dependency-groups].dev` (PEP 735, ce qu'`uv sync`
  utilise par défaut). Conséquence : pour un nouveau clone du repo,
  `uv sync` n'installait pas ruff → le pre-commit local échouait
  silencieusement (hook skip) → le dev poussait du code mal formaté
  / avec violations lint que la CI rejetait.
- `pre-commit install` n'était pas explicitement marqué obligatoire
  dans les onboarding docs.

### Changed

- `pyproject.toml` : `ruff>=0.15.12` ajouté dans `[dependency-groups].dev`.
  `uv sync` (sans `--extra dev`) installe désormais ruff automatiquement.
- `CONTRIBUTING.md` : section "Quick start" enrichie d'une commande
  obligatoire `uv run pre-commit install` avec encadré explicatif
  référençant les 3 runs CI échoués de v0.4.0.
- `docs/getting-started.md` : étape 1 enrichie de `pre-commit install`
  marquée OBLIGATOIRE + URL du repo passée à la casse canonique
  (`Mikaelarth` au lieu de `MikaelArth`).
- Version bumpée 0.4.0 → 0.4.1.

### Why v0.4.1 ne couvre pas plus

L'incident CI a aussi révélé 5 violations ruff accumulées Sessions 4-6
(S310, SIM102, 2× SIM105, UP042) + 1 fail check-yaml (mkdocs.yml tags
Python) + 4 trailing whitespace + 1 fail check_ollama_daemon en CI.
Tous ces fixes sont déjà sur main dans les commits `fa2c9ec`, `2d48061`,
`fac58f9`. La v0.4.1 retient juste le correctif tooling **préventif** qui
empêche la récurrence pour tout futur contributeur.

## [0.4.0] — 2026-05-21 — Bascule Ollama local + contrat 7 critères validé

**BREAKING CHANGE** : retrait complet de la dépendance Anthropic. Tous les
appels LLM passent désormais par Ollama local via son endpoint OpenAI-
compatible (`http://localhost:11434/v1`). Voir [ADR-025](docs/adr/025-bascule-anthropic-to-ollama.md)
pour le rationale, le mapping de modèles et les trade-offs assumés.

Cette version est livrée à l'issue de **6 sessions de travail rigoureux**
(2026-05-20 → 2026-05-21) sur la branche `feat/ollama-backend`. Elle remplit
le contrat **7 critères qualité Entreprise** négocié avec l'auteur en
Session 0 — chaque critère validé par une mesure empirique reproductible
et documentée dans `docs/sessions/`.

### Sessions 1-6 — Synthèse

| Session | Apport | Mesure / preuve |
|---|---|---|
| **1** — Suite verte post-bascule | 31 échecs initiaux → 0 en 7 lots de fix. Bug `BudgetController` Windows race corrigé. | 567 passed, coverage 92.7%, audit 0 finding |
| **2** — Première mission réelle Ollama | Mission slugify exécutée end-to-end sur Qwen2.5 32B local. | APPROVED 0.93 en 21 min / $0 (baseline Claude : 0.94 en 12 min / $0.50) |
| **3** — Nettoyage des fictions | `architecture.md` aligné avec le code : 8 agents fictifs + 4 MCP fictifs + Redis non-câblé + KG SQLite + Chief of Staff tagués `⏳ Planifié`. 5 docs annexes mises à jour. | mkdocs `--strict` 0 warning |
| **4** — Prompt code_reviewer v0.2.0 | Section "Vérification des tests — exécution mentale obligatoire" + protocole 3 étapes. | Mission re-jouée APPROVED 0.95 ; Reviewer mentionne explicitement "Chaque test a été exécuté mentalement" |
| **5** — Reviewer v0.3.0 + probe déterministe + HITL clarifié | Section "Conformité spec" ajoutée + nouveau `scripts/probe_reviewer.py` qui mesure directement la résorption du bug Session 2. ADR-014 amendé sur statut HITL. | Reviewer v0.3.0 retourne `NEEDS_CHANGES` 0.75 sur le code Session 2 inchangé (vs `APPROVED` 0.93 avant) — **preuve directe que la boucle d'amélioration des prompts fonctionne** |
| **6** — Recovery + sandbox + Langfuse | Backup/restore testé bout en bout. SandboxRunner probé sur code réel. Statut Langfuse v3 clarifié partout. | backup+restore = 3.99 s (vs seuil 600 s), sandbox pytest exit 0 en 0.91 s, observabilité 3-niveaux ✅✅⛔ documentée |

### Contrat 7 critères — état final

| # | Critère | Statut | Session preuve |
|---|---|---|---|
| 1 | Aucune feature fictive en doc | ✅ | 3 |
| 2 | Tests réellement verts | ✅ | 1+4+5 |
| 3 | Aucun garde-fou neutralisé silencieusement | ✅ | 5 (HITL clarifié) |
| 4 | Validation empirique avant promesse | ✅ | 2+4+5 (3 missions documentées + boucle prompt prouvée) |
| 5 | Sécurité par défaut | ✅ | 6 (sandbox probe) |
| 6 | Observable sans deviner | ✅ | 6 (Langfuse 3-niveaux) |
| 7 | Recoverable en < 10 min | ✅ | 6 (3.99 s mesurées) |

### Détail des changements techniques

### Migration

Pré-requis : installer Ollama (https://ollama.com) puis pull les 3 modèles
par défaut :

```bash
ollama pull qwen2.5:32b           # model_strategic
ollama pull qwen2.5-coder:32b     # model_operational
ollama pull qwen2.5:14b           # model_bulk
```

Adapter `.env` (les variables `ANTHROPIC_*` deviennent `OLLAMA_*`, défauts
sensés pour démarrer) — cf. `.env.example` regénéré.

### Changed

- `pyproject.toml` : `anthropic>=0.40.0` → `openai>=1.50.0`. Version `0.2.0` → `0.4.0`.
- `src/core/config.py` : `anthropic_api_key/max_retries/timeout` → `ollama_base_url/api_key/max_retries/timeout`. Défauts modèles Qwen2.5. `daily_budget_usd` défaut `0.0` (Ollama gratuit).
- `src/orchestrator/base_agent.py` : `AsyncAnthropic` → `AsyncOpenAI`. Adaptation du shape (`chat.completions.create`, `choices[0].message.content`, `usage.prompt_tokens/completion_tokens`, `finish_reason="length"` pour saturation).
- 9 agents (`src/orchestrator/agents/*.py`, `src/guilds/*/agents.py`, `src/learning/skill_extractor.py`, `src/orchestrator/quality_guardian.py`, `src/orchestrator/meta_workflow.py`) : signature `client: AsyncAnthropic` → `AsyncOpenAI`.
- `src/core/pricing.py` : `estimate_cost()` retourne toujours 0 (structure conservée pour retour cloud futur).
- `src/core/audit.py` : règle `OPUS_WITHOUT_JUSTIFICATION` désactivée par défaut (plus de tier payant à protéger).
- `scripts/hello_agent.py`, `scripts/check_setup.py`, `scripts/health_check.py` : adaptés. Nouveau check `check_ollama_daemon` qui ping `/api/tags` et vérifie que les 3 modèles configurés sont pullés.
- `tests/integration/test_smoke_autonomous.py` : `FakeAsyncAnthropic` → `FakeAsyncOpenAI` (mock du shape `chat.completions.create`, détection d'agent par H1 inchangée).
- `tests/unit/test_base_agent.py` et `tests/unit/test_config.py` : réécritures complètes.
- `.github/workflows/ci.yml` : variable d'env `ANTHROPIC_API_KEY` retirée.

### Removed

- Dépendance `anthropic>=0.40.0`.
- Settings `anthropic_api_key`, `anthropic_max_retries`, `anthropic_timeout_seconds`.
- Pricing par token Claude (Opus/Sonnet/Haiku) — conservé code-wise mais retourne 0.

### Trade-offs assumés (cf. ADR-025)

- **Qualité** : QualityGuardian et BusinessAnalyst dégradés (qwen2.5:32b ≈ Sonnet, pas Opus). À valider sur 3-5 missions réelles ; fallback Llama 3.3 70B si besoin.
- **Latence** : mission étalon attendue à 25-40 min vs 12 min Sonnet (selon hardware).
- **Coût** : $0 par mission.
- **Souveraineté** : 100% local.

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
- **Engineering > 1000 lignes** : non testé, dette tracée publiquement dans
  README (zone de confort). Sprint FFF planifié — décomposition livraison
  automatique en sous-missions.
- **Vague 2 tier mixing** (ADR-016) : ChiefOrchestrator + ResearchLead +
  ContentStrategist sont candidats à passer Opus → Sonnet, mais bloqué tant
  qu'on n'a pas validé sur 5 missions live d'observation.

## [0.3.0-alpha] — 2026-05-15 — Mode autonome production-ready (Sprints EEE → RRR)

11 sprints de consolidation : économie API, déploiement VPS, notifications
mobiles, garanties qualité auto-vérifiées en CI, smoke E2E sans coût, audit
anti-pattern AST-based, doc utilisateur consolidée, site mkdocs déployé.

### Added — Sprint RRR : Site mkdocs sur GitHub Pages (commit `dd94855`)

- `mkdocs.yml` avec theme **mkdocs-material** : mode sombre/clair auto,
  recherche client-side multi-langue, copy-to-clipboard, Mermaid plugin.
- `docs/index.md` : page d'accueil dédiée au site (hero + 3 cartes + CTA),
  séparée du README GitHub (objectifs distincts).
- `.github/workflows/docs.yml` : déploiement auto sur push main (paths
  filtrés), via `actions/deploy-pages@v4` dans env `github-pages`.
- 3 recipes justfile : `docs-build` (strict), `docs-serve` (live reload),
  `docs-clean`.
- 3 bugs trouvés/fixés grâce au strict mode : ancres avec accents (slugify),
  lien `../README.md` cross-dir, liens `adr/` ambigus.
- ADR-024 documente design + 5 alternatives écartées.

### Added — Sprint PPP : Doc utilisateur consolidée (commit `192ad26`)

- `docs/getting-started.md` (184 lignes) : démarrage 5 min, smoke test
  étape 4 sans coût API, troubleshooting démarrage (6 cas typiques).
- `docs/operations.md` (360 lignes) : vue unifiée mode autonome 24/7 sur
  VPS (11 sections : autonome, deploy, garde-fous, notifications, monitoring,
  économie, migration, backup, systemd, commandes, incidents).
- README.md condensé (226 → 207 lignes) : section "En 3 liens" en tête,
  démarrage express en 5 lignes, "Garanties de qualité auto-vérifiées"
  (3 portes), badges enrichis (Audit, ADRs).

### Added — Sprint QQQ : Audit en CI + pre-commit (commit `3212528`)

- Step CI dédié dans `.github/workflows/ci.yml` lance
  `audit_codebase.py --strict` → bloque PR si findings.
- Hook pre-commit `audit-codebase` (1-2s, skippable via
  `SKIP=audit-codebase`).
- Bugfix tolérance ±2 lignes pour ORPHAN_TODO : ruff format peut déplacer
  `# audit: ignore` d'1 ligne, le détecteur cherche désormais sur fenêtre.
- ADR-023 documente "3 portes en cascade" (pre-commit + CI + branch
  protection).

### Added — Sprint LLL : Anti-pattern checker AST-based (commit `328a8d7`)

- `src/core/audit.py` : 5 règles AST-based — FILE_TOO_LONG (>500 lignes),
  TEST_NO_ASSERT (assert/raises/assert_*/fail/skip), ORPHAN_TODO (sans
  référence #issue / Sprint XXX / ADR-NNN / @user / date),
  OPUS_WITHOUT_JUSTIFICATION (commentaire `# Opus :` à ±3 lignes),
  HARDCODED_PROMPT (Assign str > 300 chars avec indicateurs prompt).
- `scripts/audit_codebase.py` : CLI Rich + flags `--rule`, `--strict`,
  `--json`, `--verbose`, `--max-lines`.
- Whitelisting via `# audit: ignore <RULE>` à la ligne du finding.
- 34 tests unitaires + 4 recipes justfile (`audit`, `audit-strict`,
  `audit-verbose`, `audit-rule X`).
- Bug critique trouvé : 1ère implémentation regex de TEST_NO_ASSERT
  → 466 faux positifs sur 539 vrais tests. Fix : passage à `ast.parse()`
  + `ast.walk()`. Pareil pour HARDCODED_PROMPT (matchait docstrings de
  modules) — switch AST exclut naturellement.
- Validation empirique : 487 findings initiaux → 13 vrais positifs →
  0 finding après corrections + whitelists.
- 5 corrections OPUS : Architect, ChiefOrchestrator, ResearchLead,
  ContentStrategist, hello_agent — commentaires `# Opus : ...` ajoutés.
- 1 correction TEST_NO_ASSERT : `assert out is None` ajouté.
- 5 whitelists FILE_TOO_LONG (memory_search.py + 4 tests longs cohérents).
- ADR-022 documente design.

### Added — Sprint OOO : Smoke tests E2E sans coût API (commit `bdd7d23`)

- `tests/integration/test_smoke_autonomous.py` (11 tests, 5s, $0) :
  - `test_engineering_workflow_smoke_e2e` : mission slugify, 4 agents
    enchaînés, 2 fichiers extraits, 4 épisodes archivés.
  - `test_research_workflow_smoke_e2e` : ResearchLead → TechWatch →
    Synthesizer → Reviewer.
  - `test_router_dispatches_engineering_correctly` : routing auto.
  - `test_router_force_guild_overrides_classifier` : force_guild gagne.
  - 6 tests paramétrés `test_detect_agent_name`.
- `FakeAsyncAnthropic` : drop-in replacement, détecte agent via H1 prompt
  (`# <Display Name> — System Prompt`).
- CANON_RESPONSES pour 9 agents (format copié-collé du PATTERN observé sur
  vraies missions APPROVED dans `data/memory/missions/`).
- Bug critique trouvé : 1ère détection par mots-clés produisait des faux
  positifs (le prompt CodeReviewer contient "Backend Developer" en
  référence amont → détecté comme backend_developer). Fix : matcher sur
  le H1 standard via regex, ignorer le corps.
- ADR-021 documente le design + 4 alternatives écartées.

### Added — Sprint NNN : Health check étendu (commit `7e08f5e`)

- 5 nouveaux checks dans `scripts/health_check.py` :
  `check_vps_config`, `check_coverage_config`, `check_notifier_config`,
  `check_deploy_scripts`, `check_adrs_index`.
- Flag `--full` + `--notify-test` (envoie message test via webhook).
- 11 tests unitaires `tests/unit/test_health_check.py`.

### Added — Sprint KKK : Coverage CI automation (commit `e841924`)

- `pyproject.toml` `[tool.coverage.report]` : `fail_under = 90`, precision 1,
  show_missing, exclude_lines patterns.
- Step CI `Coverage gate (90% global, fail on regression)` dans
  `.github/workflows/ci.yml`.
- Upload artifact `coverage.xml` (rétention 30 jours).
- 3 recipes justfile : `coverage`, `coverage-strict`, `coverage-html`.
- ADR-020 documente "workflow d'évolution du seuil" + 5 alternatives.

### Added — Sprint JJJ : Audit honnête couverture (commit `4c99a4c`)

- Vraie mesure : 91% global mesurée vs 90% annoncée (badge tenait honnêtement).
- 4 modules sous-couverts identifiés et comblés :
  - `tracing.py` 64 → 89% (+5 tests path Langfuse actif mocké)
  - `memory_search.py` 73 → 85% (+11 tests error paths)
  - `sandbox/runner.py` 84 → 95% (+5 tests Docker errors)
  - `sandbox_validate.py` 79 → 100% (+6 tests print_sandbox_result)
- 27 nouveaux tests, total : 491 → 517 (+26).
- ADR-019 documente politique "mesurer avant d'annoncer" + seuils par
  catégorie de module (core ≥90%, sandbox ≥90%, orchestrator ≥85%, etc.).

### Added — Sprint HHH : Notifier mobile + round-trip migrate_vps (commit `1bb692e`)

- `src/core/notifier.py` : Notifier class avec auto-détection backend depuis
  l'URL (Discord embeds, Slack blocks, Telegram markdown, generic JSON).
  POST via urllib stdlib (zéro nouvelle dep). Échec gracieux garanti.
- 4 niveaux : INFO / SUCCESS / WARNING / CRITICAL avec emojis + couleurs.
- 31 tests unitaires couvrant détection, payloads, échecs HTTP/réseau/timeout,
  truncation, helpers.
- Settings : `NOTIFY_WEBHOOK_URL` + `NOTIFY_BACKEND` (Literal validé).
- Intégration `daily_digest.py --notify` + `autonomous_run.py --notify`.
- Test round-trip `tests/integration/test_migrate_vps.py` (6 tests E2E).
- **3 bugs critiques fixés dans `migrate_vps.sh`** révélés par le test :
  manifest JSON cassé par paths Windows (`C:\...`), `tar` interprétait `C:`
  comme host SSH (fix `--force-local`), `sha256sum` mode texte/binaire
  incohérent sur Windows (fix génération via python3).
- ADR-018 documente design notifications + 5 alternatives écartées.

### Added — Sprint GGG : Toolkit VPS multi-profile (commit `427ad46`)

- `scripts/deploy_vps.sh` : provisioning idempotent Ubuntu 22.04+ en 5 min
  (apt + Docker + uv + clone + user iaa-army + .env + sandbox build).
  Auto-détection profil VPS depuis `/proc/meminfo` (≤9G=vps1, ≤14G=vps2,
  sinon vps3).
- `scripts/migrate_vps.sh` : actions `export | import | verify | list-content`.
  Snapshot atomique (killswitch engagé), manifest JSON + checksums sha256,
  backup pré-migration auto, permissions correctes (chown iaa-army).
- Settings adaptables : `enable_sandbox` (kill-switch), `vps_profile`
  (Literal informatif).
- `docs/deploy.md` (393 lignes) : 10 sections (choix VPS, install, .env,
  vérifs, migration, systemd, sécu, monitoring, troubleshooting).
- `docs/runbook.md` : +2 sections (#13 migration échouée, #14 sandbox
  désactivé).
- ADR-017 documente décisions + 5 alternatives (Ansible, Terraform, etc.).

### Added — Sprint EEE.v1 : Tier mixing initial (commit `dcdd2fd`)

- SkillExtractor (mining nightly) : Opus → Sonnet.
- MetaDecomposer (cross-guildes) : Opus → Sonnet.
- 19 tests régression assertant tier exact par agent.
- Test méta `test_opus_agent_count_under_threshold` plafonne à 7 Opus max.
- ADR-016 documente 4 catégories d'agents + vague 1/vague 2.
- Économie attendue : ~10-20% sur missions cross-guildes.

### Added — Sprint DDD : Mission étalon FastAPI (commit `607e791`)

- BackendDeveloper `DEFAULT_MAX_TOKENS` : 4096 → 16384.
- Parser fallback élargi `_RECOGNIZED_TOP_LEVEL_FIELDS` (verdict, verdict_qg,
  verdict_sec, etc.) — Sprint DDD.bis fix critique.
- Mission étalon mini-API FastAPI complète (JWT + CRUD + tests + Docker)
  APPROVED 0.93 en 12 min / $1.74 — preuve zone confort 400-500 lignes
  multi-fichiers.
- ADR-015 documente findings empiriques.

### Stats — fin v0.3.0-alpha

- **Tests** : 415 → 573 (+158), 0 régression
- **Coverage** : 93% mesurée + gardée par CI (fail_under=90)
- **Audit** : 0 finding sur le codebase (5 règles AST gardées CI + pre-commit)
- **ADRs** : 15 → 24 (+9 : 015 à 024)
- **Docs utilisateur** : 3 (getting-started + operations + architecture) +
  site mkdocs déployable
- **Notifier** : 4 backends (Discord/Slack/Telegram/generic)
- **Toolkit VPS** : 2 scripts shell testés round-trip (6 tests intégration)
- **Économie API** : ~10-20% sur cross-guildes (tier mixing vague 1)
- **Bugs critiques fixés en passant** : 8 (3 migrate_vps + 1 détection agent
  smoke + 1 ORPHAN_TODO tolérance + 3 mkdocs strict)
- **Workflows CI** : 1 → 2 (test + docs)
- **Garanties auto-vérifiées** : 3 portes (coverage + anti-patterns +
  smoke E2E)

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

[Unreleased]: https://github.com/MikaelArth/IA-Expert-Army/compare/v0.3.0-alpha...HEAD
[0.3.0-alpha]: https://github.com/MikaelArth/IA-Expert-Army/compare/v0.2.0...v0.3.0-alpha
[0.2.0]: https://github.com/MikaelArth/IA-Expert-Army/compare/v0.1.0-rc1...v0.2.0
[0.1.0-rc1]: https://github.com/MikaelArth/IA-Expert-Army/releases/tag/v0.1.0-rc1
