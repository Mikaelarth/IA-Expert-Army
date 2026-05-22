# IA Expert Army

> Une armée d'agents IA experts spécialisés qui collaborent comme une entreprise distribuée :
> mémoire partagée vivante, évolution par expérience, autonomie sécurisée.

[![CI](https://github.com/MikaelArth/IA-Expert-Army/actions/workflows/ci.yml/badge.svg)](https://github.com/MikaelArth/IA-Expert-Army/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.6.0-blue)](CHANGELOG.md)
[![GUI](https://img.shields.io/badge/GUI-Streamlit-FF4B4B)](docs/adr/026-gui-streamlit.md)
[![Setup Wizard](https://img.shields.io/badge/setup-click--to--go-blueviolet)](docs/adr/027-setup-wizard-gui.md)
[![Tests](https://img.shields.io/badge/tests-592%20passing-brightgreen)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-91%25-brightgreen)](docs/adr/020-coverage-ci-automation.md)
[![Audit](https://img.shields.io/badge/audit-0%20findings-brightgreen)](docs/adr/022-codebase-audit-rules.md)
[![Backend](https://img.shields.io/badge/LLM-Ollama%20local-purple)](docs/adr/025-bascule-anthropic-to-ollama.md)
[![Python](https://img.shields.io/badge/python-3.12+-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![ADRs](https://img.shields.io/badge/ADRs-27-blueviolet)](docs/adr/)
[![Skills](https://img.shields.io/badge/skills-16%20auto--générées-orange)](skills/)

**Auteur :** MikaelArth (Mike Arthur) · **Démarré :** 2026-05-10 · **v0.6.0** : 2026-05-21

---

## En 3 liens

| Tu veux… | Va voir |
|---|---|
| **Démarrer en 5 minutes** | [docs/getting-started.md](docs/getting-started.md) |
| **Tourner en autonome 24/7 sur VPS** | [docs/operations.md](docs/operations.md) |
| **Comprendre l'architecture en 4 couches** | [docs/architecture.md](docs/architecture.md) |

Et pour les décisions structurantes : [27 ADRs](docs/adr/) · pour les incidents : [docs/runbook.md](docs/runbook.md) · pour l'historique des sessions de qualité v0.4.0 → v0.6.0 : [docs/sessions/](docs/sessions/).

---

## Pourquoi IA-Expert-Army

Plutôt qu'**un** agent IA généraliste, **une équipe** d'agents spécialisés qui se passent le travail comme une PME — avec :

- ✅ **Mémoire partagée vivante** qui s'enrichit à chaque mission (RAG sémantique sur les épisodes passés)
- ✅ **Apprentissage par expérience** : skills auto-extraites des meilleurs épisodes, citées par les agents dans leurs futures missions
- ✅ **Autonomie sécurisée** : 5 garde-fous non-négociables (budget cap, killswitch, error rate, saturation, quality drift)
- ✅ **Boucle qualité fermée** : code généré → écrit sur disque → validé en sandbox Docker isolé, en une commande

**Promesse vérifiable** (mesurée Session 2 sur Qwen2.5 32B local) :

```bash
uv run python scripts/run_mission.py \
  --title "Crée la fonction slugify utilitaire" \
  --description "Implémente slugify(text: str) -> str. Tests pytest pour cas canoniques + edge cases." \
  --apply
# → mission APPROVED 0.93 → 2 fichiers écrits sur disque → $0 (local)
# → Reviewer v0.3.0 (Session 5) refuse même les tests buggy via exécution mentale obligatoire
```

Une commande. ~21 min sur Qwen2.5 32B local (vs 12 min sur Claude Sonnet, $0 vs $0.50).
Validation sandbox Docker testée Session 6 : pytest exit 0 en 0.91 s en container isolé
(`network=none`, `user=nobody`).

---

## Démarrage express

```bash
# 1. Installer Ollama (backend LLM local, gratuit) : https://ollama.com
ollama pull qwen2.5:32b              # model_strategic (~20 Go)
ollama pull qwen2.5-coder:32b        # model_operational (~20 Go)
ollama pull qwen2.5:14b              # model_bulk (~9 Go)

# 2. Cloner + setup
git clone https://github.com/MikaelArth/IA-Expert-Army.git
cd IA-Expert-Army
uv sync                              # installe les dépendances Python (~30s)
cp .env.example .env                 # défauts Ollama OK out-of-the-box
uv run python scripts/health_check.py --quick    # tout doit être vert/skip
uv run pytest tests/integration/test_smoke_autonomous.py -v   # smoke E2E en 5s, $0
```

Bascule **v0.4.0** (ADR-025) : plus de dépendance Anthropic, tout tourne en local.

Pour démarrer une vraie mission : suivre [docs/getting-started.md](docs/getting-started.md).

**Préférence GUI** ? Depuis v0.5.0 ([ADR-026](docs/adr/026-gui-streamlit.md)) :

```bash
uv sync --group gui     # installe Streamlit (~50 Mo, opt-in)
just gui                # http://127.0.0.1:8501
```

6 pages : 🛠 **Setup** · 🚀 Mission · 📜 Historique · 🧠 Skills · 🏥 Health · 🔬 Probes.

**Onboarding zéro-terminal** (v0.6.0, [ADR-027](docs/adr/027-setup-wizard-gui.md)) : la page **🛠 Setup** détecte automatiquement ce qui manque (Ollama daemon, modèles Qwen2.5, image sandbox Docker, fichier `.env`) et propose un fix d'un clic — démarrer le daemon, pull un modèle avec barre de progression, build l'image sandbox, créer `.env` depuis `.env.example`. Pour les installeurs système (Ollama, Docker Desktop, uv), un bouton ouvre l'URL officielle.

---

## Zone de confort empiriquement validée

| Type de mission | État | Preuve |
|---|---|---|
| Engineering simple (50-200 lignes) | ✅ converge confortablement | slugify (Session 2 Ollama APPROVED 0.93), /ping, /version, /info — historique baseline Claude APPROVED 0.91-0.97 |
| Research / Creative / Business | ✅ converge | Pydantic v1 vs v2, water-tracker landing, roadmap (baseline Claude — non re-mesuré post-bascule Ollama) |
| Cross-guildes meta-missions | ✅ converge | water-tracker APPROVED 0.92 (3 sous-missions, baseline Claude) |
| **Engineering 400-500 lignes multi-fichiers** | ✅ converge sur baseline Claude (avec QG + SecurityAuditor) | **mini-API FastAPI complète (JWT + CRUD + tests + Docker) — APPROVED 0.93 en 12 min / $1.74** ([ADR-015 Sprint DDD.ter](docs/adr/015-etalon-mission-findings.md)). Non re-mesuré sur Ollama 32B local — durée estimée ×2-3. |
| Engineering > 1000 lignes | ⏳ Non testé, dette tracée | Sprint FFF planifié (décomposition livraison automatique) |
| **Probe Reviewer déterministe (Session 5 v0.3.0)** | ✅ Bug Session 2 détecté en `NEEDS_CHANGES 0.75` en 7 min 30 | [Probe Session 5](docs/sessions/session-5-reviewer-v0-3-0-probe-hitl.md) — preuve reproductible via `scripts/probe_reviewer.py` |

---

## Architecture en 4 couches

```
┌─────────────────────────────────────────────────────────────────────┐
│  4. Apprentissage     · PatternMiner + SkillExtractor + RAG sémantique
├─────────────────────────────────────────────────────────────────────┤
│  3. Infrastructure    · FileMemory · VectorMemory · SkillsLibrary
│                       · Sandbox Docker · BudgetController · Killswitch
│                       · Notifier (Discord/Slack/Telegram) · MCP server
├─────────────────────────────────────────────────────────────────────┤
│  2. 4 Guildes         · Engineering (4 agents : architect/dev/reviewer/orchestrator)
│                       · Research    (4 agents : lead/watch/synthesizer/reviewer)
│                       · Creative    (3 agents : strategist/copywriter/editor)
│                       · Business    (3 agents : PM/analyst/legal)
├─────────────────────────────────────────────────────────────────────┤
│  1. Direction         · Chief Orchestrator + Quality Guardian + Security Auditor
└─────────────────────────────────────────────────────────────────────┘
```

Détails complets + diagrammes Mermaid : [docs/architecture.md](docs/architecture.md).

---

## Les 4 guildes

| Guilde | Domaine | Output type | Boucle d'apprentissage |
|---|---|---|---|
| **Engineering** | Code, tests, infra | Fichiers Python (apply + sandbox) | ✅ Citations en prod |
| **Research** | Synthèse, veille, analyse | Markdown structuré + sources | ✅ Citations en prod |
| **Creative** | Contenu (landing, email, blog) | Markdown rédactionnel | ✅ Citations en prod |
| **Business** | Roadmap, viabilité, conformité | YAML structuré (plan + KPIs + verdict) | ✅ Citations en prod |

Boucle d'apprentissage = un agent **cite explicitement** sa propre skill auto-générée par le PatternMiner dans une nouvelle mission. Observable dans les logs / épisodes.

---

## Outils CLI principaux

| Script | Usage |
|---|---|
| `scripts/run_mission.py` | Lance une mission live (auto-routée vers la bonne guilde) avec `--apply --validate` |
| `scripts/autonomous_run.py` | Mode autonome (queue YAML + 5 garde-fous) |
| `scripts/daily_digest.py` | Rapport quotidien (`--notify` envoie sur Discord/Telegram) |
| `scripts/nightly_learning.py` | Mine les épisodes APPROVED en skills réutilisables |
| `scripts/budget.py` / `killswitch.py` / `health_check.py` | Garde-fous + diagnostic |
| `scripts/audit_codebase.py` | Audit anti-pattern (5 règles AST-based) |
| `scripts/deploy_vps.sh` / `migrate_vps.sh` | Toolkit VPS (Ubuntu 22.04+) |
| `scripts/run_memory_search_mcp.py` | Expose la mémoire à des LLMs tiers via MCP |

Tous supportent `--help`. Recipes raccourcies dans le `justfile` (`just <cmd>`).

---

## Garanties de qualité (auto-vérifiées)

Le projet est **auto-protégé contre la dérive silencieuse** par 3 garde-fous croisés en CI :

| Garde-fou | Mécanisme | Sprint |
|---|---|---|
| **Coverage ≥ 90%** | `pyproject.toml` `fail_under = 90` + step CI dédié | [JJJ/KKK](docs/adr/020-coverage-ci-automation.md) |
| **Anti-patterns = 0** | 5 règles AST-based (`audit_codebase.py --strict`) en CI + pre-commit | [LLL/QQQ](docs/adr/023-audit-ci-pre-commit-integration.md) |
| **Tests E2E sans coût API** | `FakeAsyncAnthropic` simule la chaîne complète en 5s à chaque PR | [OOO](docs/adr/021-smoke-e2e-tests.md) |

Pour qu'une régression atterrisse en `main`, il faut explicitement bypasser **trois portes** (pre-commit local + CI step + branch protection). Beaucoup plus dur de dériver.

---

## Apprentissage par expérience

À chaque mission APPROVED non-saturée, ses épisodes sont indexés dans une mémoire vectorielle Chroma. Périodiquement, le `PatternMiner` analyse les meilleurs épisodes par rôle et fait extraire une **skill réutilisable**. À la mission suivante, l'agent retrouve sa propre skill via RAG sémantique et l'applique.

**Preuve textuelle observable en production** (mission Research « Rate limiting d'API LLM ») :

> *"**Précédents appliqués : Skill 1 (findings YAML structuré)** : chaque SQ a 5-7 findings atomiques, confidence + sources nommées."*

L'agent `tech_watch` cite la skill que le système a auto-générée à partir de ses propres missions précédentes. Voir [ADR-004](docs/adr/004-learning-strategy.md) et [ADR-006](docs/adr/006-mining-strategy-and-eligibility.md).

---

## Structure du projet

```
IA-Expert-Army/
├── src/
│   ├── orchestrator/       # Couche 1 — Chief Orchestrator + MissionRouter + QG
│   ├── guilds/             # Couche 2 — 4 guildes spécialisées
│   ├── memory/             # Couche 3 — FileMemory + VectorMemory
│   ├── learning/           # Couche 4 — PatternMiner + SkillExtractor
│   ├── sandbox/            # Sandbox Docker runner
│   ├── mcp_servers/        # Serveurs MCP custom (memory_search)
│   ├── tools/              # apply_files + sandbox_validate
│   └── core/               # config, logging, budget, killswitch, tracing,
│                           # notifier, audit, backup, approvals
├── prompts/                # System prompts versionnés (markdown + frontmatter)
├── skills/                 # Procédures réussies auto-extraites (markdown)
├── docs/                   # Getting Started + Operations + Architecture + 23 ADRs
├── scripts/                # CLI tools (Python + bash deploy/migrate)
├── tests/
│   ├── unit/               # Tests unitaires (~560)
│   └── integration/        # Smoke E2E + round-trip (~13)
├── infra/docker/           # Dockerfile sandbox
└── docker-compose.yml      # Langfuse + Redis + Chroma (profile-gated)
```

---

## État du projet (v0.6.0)

| Capacité | Statut | Détails |
|---|---|---|
| Backend LLM local (Ollama) | ✅ v0.4.0 | `qwen2.5:32b` + `qwen2.5-coder:32b` + `qwen2.5:14b`, $0/mission |
| 4 guildes avec boucle d'apprentissage | ✅ | Engineering, Research, Creative, Business |
| Sandbox Docker validé en réel | ✅ Session 6 | pytest exit 0 en 0.91 s, isolation `network=none` + `user=nobody` prouvée |
| Quality Guardian (peer review méta) | ✅ | Opt-in `ENABLE_QUALITY_GUARDIAN=true` |
| Security Auditor (OWASP) | ✅ | Opt-in `ENABLE_SECURITY_AUDITOR=true` |
| CodeReviewer v0.3.0 (exécution mentale + conformité spec) | ✅ Session 5 | Mesure directe : refuse les tests buggy là où v0.1.0 validait |
| HITL approvals | ✅ Primitive livrée, ⛔ pas un garde-fou auto | Cf. [ADR-014](docs/adr/014-hitl-approvals.md) amendement Session 5 |
| BudgetController | ✅ No-op si cap≤0 (Ollama gratuit) | Explicite via property `is_disabled`, sortie de doute |
| Notifier mobile multi-backend | ✅ | Discord/Slack/Telegram/generic |
| Toolkit VPS (deploy + migrate) | ✅ | Round-trip testé + bugs Windows fixés |
| Backup + Restore < 10 min | ✅ Session 6 | Mesuré 3.99 s (~150× sous seuil) |
| Coverage gardé par CI | ✅ | 91% / fail_under=90 |
| Audit anti-patterns en CI + pre-commit | ✅ | 5 règles, 0 finding actuel |
| Smoke tests E2E sans LLM réel | ✅ | 11 tests Engineering + Research |
| Smoke tests GUI Streamlit | ✅ v0.5.0+ | 9 tests `AppTest`, chaque page render sans crash |
| Langfuse | ✅ Cloud opt-in / ⛔ self-hosted v3 incomplet | Cf. [architecture.md](docs/architecture.md) section Observabilité |
| MCP server `memory_search` (6 tools) | ✅ | Exposable à Claude Desktop / Cursor |
| **GUI Streamlit** | ✅ v0.5.0+ | 6 pages : Setup / Mission / Historique / Skills / Health / Probes — `just gui` |
| **Setup Wizard click-to-go** | ✅ v0.6.0 | Page Setup : 10 détections + actions auto (start daemon, pull modèle streaming, build sandbox, créer `.env`) — [ADR-027](docs/adr/027-setup-wizard-gui.md) |
| Tests régression | ✅ | **592 verts** (91% coverage mesurée) |
| ADRs documentés | ✅ | **27 ADRs** structurants |

**Coût total API consommé** : ~$19 sur les 16 missions Claude pré-bascule (score moyen 0.89). **Depuis Ollama (v0.4.0)** : $0. Le système est opérationnel pour de l'usage perso quotidien via GUI.

---

## Contribuer

```bash
uv sync                       # install
just test                     # 573 tests doivent être verts
just coverage-strict          # ≥ 90% obligatoire
just audit-strict             # 0 finding obligatoire
```

Voir [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Licence

[MIT](LICENSE) — libre d'usage commercial et personnel, attribution requise.
