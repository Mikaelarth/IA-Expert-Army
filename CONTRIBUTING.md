# Contributing to IA-Expert-Army

Thanks for considering contributing! This project follows opinionated rules
to keep the codebase **« pro et propre »**. They're not arbitrary — each
rule is enforced automatically by CI + pre-commit (3 portes en cascade) and
documented in an ADR.

---

## Quick start (5 min)

```bash
git clone https://github.com/MikaelArth/IA-Expert-Army.git
cd IA-Expert-Army
uv sync                                        # installs deps + Python 3.12+
cp .env.example .env                           # then edit ANTHROPIC_API_KEY
uv run python scripts/health_check.py --quick  # tous les checks verts/skip
uv run pytest tests/unit/                      # all 573 tests must pass
```

Pas envie de configurer une clé API ? Smoke test E2E **sans coût** :

```bash
uv run pytest tests/integration/test_smoke_autonomous.py -v   # 5s, $0
```

---

## Before you push (les 4 commandes obligatoires)

```bash
just test              # 573 tests doivent être verts
just coverage-strict   # ≥ 90% (fail_under bloque sinon)
just audit-strict      # 0 finding (5 règles AST)
just lint              # ruff clean
```

Ou en une commande qui fait tout : `uv run pre-commit run --all-files`.

> Si ces 4 commandes passent vert localement, la CI passera aussi. Si elles
> échouent, la PR sera bloquée — l'enjeu est de ne **rien** négliger.

---

## Pre-commit hooks (recommandé)

Le projet fournit une config [pre-commit](https://pre-commit.com/) qui
automatise tout à chaque `git commit`. Activation locale :

```bash
uv sync                              # installe pre-commit
uv run pre-commit install            # active les hooks Git
uv run pre-commit run --all-files    # premier run sur tout le repo
```

Hooks actifs (cf. `.pre-commit-config.yaml`) :
- **ruff** : lint + auto-fix + format
- **check-yaml / check-toml / check-merge-conflict** : intégrité fichiers
- **check-added-large-files** (>512 KB) : pas de binaires accidentels
- **pytest unit suite** : 560+ tests, toute la suite
- **health-check --quick** : Settings + 4 guildes + mémoire + classifier
- **audit-codebase --strict** : 5 règles d'anti-pattern (cf. ADR-022)

Bypass urgence : `SKIP=audit-codebase git commit -m "..."` ou
`git commit --no-verify` — **fortement déconseillé**, l'enjeu est de ne
**rien** négliger.

---

## Garanties qualité auto-vérifiées (3 portes en cascade)

Pour qu'une régression atterrisse en `main`, il faut bypasser **trois portes** :

| Porte | Mécanisme | ADR |
|---|---|---|
| **Coverage ≥ 90%** | `pyproject.toml` `fail_under = 90` + step CI dédié | [020](docs/adr/020-coverage-ci-automation.md) |
| **Anti-patterns = 0** | 5 règles AST-based (`audit_codebase.py --strict`) | [023](docs/adr/023-audit-ci-pre-commit-integration.md) |
| **Smoke E2E sans coût API** | `FakeAsyncAnthropic` à chaque PR (5s, $0) | [021](docs/adr/021-smoke-e2e-tests.md) |

C'est volontaire et désirable. Si une règle bloque ta PR :
1. **Si tu as un cas légitime** : utilise `# audit: ignore <RULE>` avec
   justification dans le commentaire, ou bumper le seuil avec ADR.
2. **Si la règle est mal calibrée** : ouvre une issue argumentée, on
   discute la modification de la règle (pas du bypass).

---

## Architecture en 30 secondes

Le projet est organisé en **4 couches** ([ADR-001](docs/adr/001-four-layer-architecture.md)) :

```
Couche 4 — Apprentissage  (PatternMiner + SkillExtractor + RAG)
Couche 3 — Infrastructure (FileMemory + VectorMemory + Sandbox + Budget + Notifier)
Couche 2 — 4 Guildes      (Engineering · Research · Creative · Business)
Couche 1 — Direction      (Chief Orchestrator · Quality Guardian · Security Auditor)
```

**Lis les ADRs concernés** avant de proposer un changement structurel.
Index complet : [docs/adr/README.md](docs/adr/README.md) (24 ADRs).

---

## Code conventions

- **Type hints partout** : Python 3.12+ syntax (`list[str]`, `int | None`).
- **Pas de commentaires qui paraphrasent le code** : un commentaire explique
  le *pourquoi*, pas le *quoi*.
- **Imports triés** : stdlib → tiers → projet (auto-sortable via `ruff check
  --select I --fix`).
- **Pas d'effets de bord à l'import** : configuration via `Settings`, pas
  via constantes globales.
- **Pas de `print()`** : utiliser `structlog` via `get_logger()`.
- **Erreurs explicites** : pas de `except: pass`. Un `except` attrape un
  type précis et logge ou re-raise.
- **Tests > 0 assertions** : un test sans `assert` / `pytest.raises` / 
  `mock.assert_*` est détecté par l'audit (cf. ADR-022 règle TEST_NO_ASSERT).
- **TODO avec référence** : `# TODO Sprint XXX:` ou `# TODO #42:` ou
  `# TODO @user 2026-06-01:`. Un TODO orphelin est détecté par l'audit
  (règle ORPHAN_TODO).
- **Opus à justifier** : si tu utilises `model_strategic` (Opus), ajoute un
  commentaire `# Opus : raison...` à proximité (politique ADR-016, règle
  OPUS_WITHOUT_JUSTIFICATION).
- **Pas de prompt hardcodé** : les system prompts vivent dans `prompts/**/*.md`
  (versionnés, diffables). Une string > 300 chars contenant `Tu es` /
  `You are` dans le code Python est détectée (règle HARDCODED_PROMPT).
- **Fichiers ≤ 500 lignes** : au-delà, l'audit suggère un split. Whitelist
  documentée acceptée si justifié (règle FILE_TOO_LONG).

---

## Adding a new agent

1. Crée le system prompt dans `prompts/<guild>/<role>.md` avec YAML
   frontmatter (cf. existing prompts pour le schema). **Le H1 doit suivre
   le pattern `# <Display Name> — System Prompt`** (sinon le smoke E2E
   ne détectera pas l'agent).
2. Subclass `BaseAgent` dans `src/guilds/<guild>/agents.py`. Set
   `DEFAULT_MAX_TOKENS` généreusement (8192 pour reviewers/synthesizers,
   4096 pour planners, 16384 pour developers multi-fichiers). Cf. 
   [ADR-005](docs/adr/005-saturation-detection-and-prevention.md).
3. Ajoute le rôle à `PatternMiner.AGENT_WHITELIST` dans 
   `src/learning/pattern_miner.py` (régression test catch les oublis).
4. Ajoute le rôle au `Workflow` correspondant et mets à jour le
   `MissionRouter` (keywords).
5. Crée `tests/unit/test_<guild>_agents.py` couvrant : model tier,
   max_tokens floor, prompt loads, classifier route correctement.
6. **Sprint OOO** — ajoute une entrée dans `CANON_RESPONSES` dans
   `tests/integration/test_smoke_autonomous.py` + entrée dans
   `_DISPLAY_NAME_TO_AGENT`. Sinon le smoke E2E aura un "unknown agent".
7. **Sprint EEE** — si tu utilises Opus, ajoute un commentaire 
   `# Opus : ...` à proximité de `model=s.model_strategic`. Et si tu
   dépasses 7 agents Opus au total, **change-en un en Sonnet d'abord**
   (cf. test `test_opus_agent_count_under_threshold`).

---

## Adding a new guild

Comme pour les agents, plus :
- Nouveau `<Guild>Workflow` class avec pipeline linéaire + 1× repair loop.
- Nouveau `<Guild>MissionResult` Pydantic model.
- Mise à jour `MissionRouter._build_routing_decision()` et
  `MissionRouter.run()` pour le dispatch.
- Nouveau keyword set dans `_<GUILD>_KEYWORDS`.
- Test de régression pour le routing.
- **Repair loop élargi** : si un reviewer downstream peut critiquer un
  upstream, alors le repair doit ré-exécuter **tous les agents en amont**
  (pattern méta-leçon Sprint PP/SS/WW). Cf. `src/orchestrator/workflow.py`
  ligne 207+ pour l'exemple Engineering.

---

## Adding a new ADR

1. Crée `docs/adr/NNN-titre-court.md` (NNN = numéro suivant).
2. Suis le template existant (Statut / Contexte / Décision / Conséquences /
   Alternatives considérées / Sources).
3. Ajoute l'entrée dans `docs/adr/README.md` (index).
4. Ajoute l'entrée dans `mkdocs.yml` (section `nav.Décisions (ADRs)`).
5. `just docs-build` pour vérifier que le strict mode passe.

---

## Mining policy

Le PatternMiner a 5 filtres d'éligibilité stricts (cf. 
[ADR-006](docs/adr/006-mining-strategy-and-eligibility.md)). **Don't lower
them.** Si ton rôle ne peut pas encore être miné, c'est un signal que tu as
besoin de plus de missions APPROVED, pas de filtres plus laxes.

---

## Cost discipline

Une mission coûte $0.20–$1.50 en Claude API selon la complexité. Le cap par
défaut est $50/jour. Avant une session d'expérimentation lourde :
- Set `DAILY_BUDGET_USD` dans `.env` à une valeur raisonnable.
- Use `just budget` pour monitorer.

Si tu hits le cap mid-session, c'est le BudgetController qui fait son
boulot. Soit bump le cap délibérément, soit wait jusqu'au reset minuit UTC.

Pour **réduire** le coût : politique tier mixing (cf.
[ADR-016](docs/adr/016-tier-mixing-strategy.md)). Tous les agents Opus
doivent être justifiés par commentaire `# Opus : ...`. L'audit le vérifie.

---

## Documentation site

Le projet a un site doc déployé sur GitHub Pages 
(https://mikaelarth.github.io/IA-Expert-Army/, à activer côté Settings).
Sources : `docs/**/*.md` + `mkdocs.yml`.

```bash
just docs-build    # build strict (échoue sur warning) — ce que CI fait
just docs-serve    # live reload sur http://127.0.0.1:8000
```

Si tu ajoutes une nouvelle page, mets à jour `mkdocs.yml` section `nav:`
(sinon ordre alpha qui mélange tout).

---

## Reporting bugs

Open a GitHub issue with :
1. The mission title + description that triggered it.
2. The relevant episode markdown from `data/memory/episodes/`.
3. Whether `saturated: true` appears in any episode metadata (if yes, that's
   almost certainly the cause — see [ADR-005](docs/adr/005-saturation-detection-and-prevention.md)).
4. Output of `just health` (pour les bugs d'environnement).
5. Output of `just audit-strict` (pour les bugs de qualité code).

Pour les **incidents en mode autonome** sur VPS : 
[docs/runbook.md](docs/runbook.md) couvre 14 cas observés en condition
réelle.

---

## Workflow de release

1. Mettre à jour `[Unreleased]` dans `CHANGELOG.md` au fur et à mesure.
2. À la release, déplacer le contenu de `[Unreleased]` vers 
   `[X.Y.Z] — YYYY-MM-DD`.
3. Bumper `version` dans `pyproject.toml`.
4. MAJ badges README (tests count, coverage %).
5. Tag git : `git tag vX.Y.Z` puis `git push origin vX.Y.Z`.
6. Le workflow `docs.yml` redéploie automatiquement le site.

---

## License

By contributing, you agree that your contributions will be licensed under
the [MIT License](LICENSE).
