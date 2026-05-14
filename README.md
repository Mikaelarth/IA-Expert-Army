# IA Expert Army

> Une armée d'agents IA experts spécialisés qui collaborent comme une entreprise distribuée :
> mémoire partagée vivante, évolution par expérience, autonomie sécurisée.

[![CI](https://github.com/MikaelArth/IA-Expert-Army/actions/workflows/ci.yml/badge.svg)](https://github.com/MikaelArth/IA-Expert-Army/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-261%20passing-brightgreen)](tests/unit/)
[![Python](https://img.shields.io/badge/python-3.12+-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Guildes](https://img.shields.io/badge/guildes-4%20+%20cross--guildes-blueviolet)](#les-4-guildes)
[![Skills](https://img.shields.io/badge/skills-16%20auto--générées-orange)](skills/)

**Auteur :** MikaelArth (Mike Arthur) · **Démarré :** 2026-05-10

---

## Pourquoi IA-Expert-Army

Plutôt qu'**un** agent IA généraliste, **une équipe** d'agents spécialisés qui se passent le travail comme une PME — avec une **mémoire partagée qui s'enrichit à chaque mission** et un système qui **refuse de produire du travail médiocre par construction** (sandbox Docker, mining strict, parser tolérant 3-tiers, saturation auto-détectée).

**Promesse vérifiable** :

```bash
uv run python scripts/run_mission.py \
  --title "Endpoint /info diagnostic" \
  --description "Crée un endpoint FastAPI..." \
  --apply --validate
# → mission APPROVED 0.93 → 2 fichiers écrits → 3/3 pytest dans sandbox PASSED
# → "Boucle qualité fermée : mission APPROVED + apply OK + sandbox pytest OK."
```

Une commande. Code généré, écrit sur disque, validé en sandbox isolé, tout en 100s.

---

## Architecture en 4 couches

```
┌─────────────────────────────────────────────────────────────────────┐
│  4. Apprentissage     · PatternMiner + SkillExtractor + RAG sémantique
├─────────────────────────────────────────────────────────────────────┤
│  3. Infrastructure    · FileMemory · VectorMemory · SkillsLibrary
│                       · Sandbox Docker · BudgetController · Killswitch
│                       · Daily digest · MCP server (memory_search)
├─────────────────────────────────────────────────────────────────────┤
│  2. 4 Guildes         · Engineering (4 agents : architect/dev/reviewer/orchestrator)
│                       · Research    (4 agents : lead/watch/synthesizer/reviewer)
│                       · Creative    (3 agents : strategist/copywriter/editor)
│                       · Business    (3 agents : PM/analyst/legal)
├─────────────────────────────────────────────────────────────────────┤
│  1. Direction         · Chief Orchestrator + Quality Guardian
└─────────────────────────────────────────────────────────────────────┘
```

Voir [docs/architecture.md](docs/architecture.md) pour le détail, et [docs/adr/](docs/adr/) pour les 7 ADRs documentant les décisions structurantes.

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

## Démarrage rapide (5 min)

### 1. Prérequis

- **Python 3.12+** (sera installé par uv si absent)
- [**uv**](https://github.com/astral-sh/uv) — package manager Python
- **Docker Desktop** (pour le sandbox de validation)
- **Git**
- Une clé API Anthropic ([console.anthropic.com](https://console.anthropic.com))

### 2. Installation

```powershell
git clone <repo-url> IA-Expert-Army
cd IA-Expert-Army
uv sync                    # installe toutes les dépendances
copy .env.example .env     # crée ton fichier d'environnement
notepad .env               # colle ta clé ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Vérifier l'installation

```powershell
uv run python scripts/check_setup.py
```

Tous les contrôles doivent être verts.

### 4. Lancer le premier agent (smoke test, ~$0.03)

```powershell
uv run python scripts/hello_agent.py
```

Le Chief Orchestrator se présente.

### 5. Lancer une vraie mission (boucle qualité fermée, ~$0.50)

```powershell
# Optionnel : build l'image sandbox une fois (~3 min)
uv run python scripts/check_sandbox.py --build

# Mission Engineering → code → apply → sandbox pytest
uv run python scripts/run_mission.py `
  --title "Endpoint /uptime" `
  --description "Crée un endpoint FastAPI GET /uptime qui retourne {seconds: float} via time.monotonic. Inclus tests pytest." `
  --apply --validate
```

---

## Outils CLI principaux

| Script | Usage |
|---|---|
| `scripts/run_mission.py` | Lance une mission live (auto-routée vers la bonne guilde) avec `--apply --validate` |
| `scripts/apply_mission.py` | Re-applique ou re-valide une mission archivée |
| `scripts/sandbox_run_pytest.py` | Lance pytest dans le sandbox sur des fichiers existants |
| `scripts/nightly_learning.py` | Mine les épisodes APPROVED en skills réutilisables |
| `scripts/budget.py` / `killswitch.py` / `daily_digest.py` | Garde-fous d'autonomie |
| `scripts/run_memory_search_mcp.py` | Expose la mémoire à des LLMs tiers via MCP |

Tous supportent `--help`.

---

## Garde-fous (mode autonome)

Le système est conçu pour tourner de manière autonome. Les **10 garde-fous non négociables** ([ADR-003](docs/adr/003-autonomy-with-guardrails.md)) :

1. ✅ **Sandbox Docker** pour toute exécution de code (network=none, non-root, mem/cpu/pid limits)
2. ✅ **Filesystem restreint** (whitelist `src/`, `tests/`, `scripts/`, `docs/`, `prompts/`, `skills/`)
3. ✅ **Pas d'accès réseau** dans le sandbox (whitelist explicite si besoin)
4. ✅ **Hard cap budget** API journalier (refus prouvé en condition réelle)
5. 🚧 **Circuit breakers** sur taux d'erreur (Phase 6+)
6. 🚧 **Approbation humaine** pour deploy prod / envois externes (Phase 6+)
7. ✅ **Logs immutables** Langfuse (stack opérationnelle)
8. ✅ **Killswitch global** (sentinel file)
9. ✅ **Daily digest** CLI
10. ✅ **Backups** automatiques via versioning Git

---

## Apprentissage par expérience

Le système ne se contente pas d'exécuter — il **apprend de ses succès**. À chaque mission APPROVED non-saturée, ses épisodes sont indexés dans une mémoire vectorielle. Périodiquement, le `PatternMiner` analyse les meilleurs épisodes par rôle et fait extraire par Opus une **skill réutilisable**. À la mission suivante, l'agent retrouve sa propre skill via RAG sémantique et l'applique.

**Preuve textuelle observable en production** (mission Research « Rate limiting d'API LLM ») :

> *"**Précédents appliqués : Skill 1 (findings YAML structuré)** : chaque SQ a 5-7 findings atomiques, confidence + sources nommées."*

L'agent `tech_watch` cite la skill que le système a auto-générée à partir de ses propres missions précédentes. Voir [ADR-004](docs/adr/004-learning-strategy.md) et [ADR-006](docs/adr/006-mining-strategy-and-eligibility.md).

---

## Structure du projet

```
IA-Expert-Army/
├── src/
│   ├── orchestrator/       # Couche 1 — Chief Orchestrator + MissionRouter
│   ├── guilds/             # Couche 2 — 4 guildes spécialisées
│   ├── memory/             # Couche 3 — FileMemory + VectorMemory
│   ├── learning/           # Couche 4 — PatternMiner + SkillExtractor
│   ├── sandbox/            # Sandbox Docker runner
│   ├── mcp_servers/        # Serveurs MCP custom
│   ├── tools/              # apply_files + sandbox_validate
│   └── core/               # config + logging + budget + killswitch + tracing
├── prompts/                # System prompts versionnés (markdown + frontmatter)
├── skills/                 # Procédures réussies auto-extraites (markdown)
├── docs/                   # README + architecture + 7 ADRs
├── scripts/                # CLI tools
├── tests/                  # 212 tests pytest (unit + integration)
├── infra/docker/           # Dockerfile sandbox
└── docker-compose.yml      # Langfuse + Redis + Chroma (profile-gated)
```

---

## État du projet

| Capacité | Statut | Détails |
|---|---|---|
| 4 guildes avec boucle d'apprentissage | ✅ | Engineering, Research, Creative, Business |
| Sandbox Docker validé en réel | ✅ | `run_mission --apply --validate` end-to-end |
| BudgetController prouvé en condition réelle | ✅ | Refus mission en cap atteint |
| Langfuse v3 self-hosted | ✅ | Stack démarrable, instrumentation `@observe` opt-in |
| MCP server `memory_search` | ✅ | Exposable à Claude Desktop / Cursor |
| Tests régression | ✅ | 212 verts, jamais de régression silencieuse |
| ADRs documentés | ✅ | 7 ADRs structurants |

**~$19 d'API consommés** sur 16 missions APPROVED (score moyen 0.89). Le système est opérationnel pour de l'usage réel, pas juste de la démo.

---

## Contribuer

Voir [CONTRIBUTING.md](CONTRIBUTING.md). En 30 secondes : `uv sync` + `uv run pytest tests/unit/` doit être vert avant tout PR.

---

## Licence

[MIT](LICENSE) — libre d'usage commercial et personnel, attribution requise.
