# IA Expert Army

> Une armée d'agents IA experts spécialisés qui collaborent comme une entreprise distribuée :
> mémoire partagée vivante, évolution par expérience, autonomie pilotée.

**Statut :** Phase 0 — Fondations
**Stack :** Python 3.12 · Claude Agent SDK · LangGraph · Chroma · Redis · Langfuse · Docker
**Auteur :** MikaelArth (Mike Arthur)
**Démarrage :** 2026-05-10

---

## Vision

Un système multi-agents en **4 couches** :

```
┌─────────────────────────────────────────────────┐
│  4. Apprentissage & Évolution                   │  ← outcomes, patterns, few-shot, refinement
├─────────────────────────────────────────────────┤
│  3. Infrastructure partagée                     │  ← mémoire, MCP, bus, sandbox, observabilité
├─────────────────────────────────────────────────┤
│  2. Les 4 Guildes spécialisées                  │  ← Engineering · Research · Creative · Business
├─────────────────────────────────────────────────┤
│  1. Comité de direction                         │  ← Chief Orchestrator · Quality Guardian
└─────────────────────────────────────────────────┘
```

Voir [docs/architecture.md](docs/architecture.md) pour le détail complet.

---

## Démarrage rapide (Phase 0)

### 1. Prérequis

- Python 3.12+ (sera installé par uv si absent)
- [uv](https://github.com/astral-sh/uv) (package manager Python)
- Docker Desktop
- Git
- Une clé API Anthropic ([console.anthropic.com](https://console.anthropic.com))

### 2. Installation

```powershell
# Depuis D:\PROJETS\IA-Expert-Army
uv sync                    # installe les dépendances Phase 0
copy .env.example .env     # crée ton fichier d'environnement
notepad .env               # édite et colle ta clé API Anthropic
```

### 3. Vérifier l'installation

```powershell
uv run python scripts\check_setup.py
```

### 4. Lancer le premier agent

```powershell
uv run python scripts\hello_agent.py
```

Tu devrais voir une réponse de Claude se présentant comme le premier agent de l'IA-Expert-Army.

---

## Phases du projet

| Phase | Nom | Statut |
|-------|-----|--------|
| 0 | Fondations | 🚧 En cours |
| 1 | MVP : 3 agents + mémoire simple | À venir |
| 2 | Mémoire intelligente + Vector DB | À venir |
| 3 | Infrastructure complète + sandbox | À venir |
| 4 | 4 Guildes complètes (~25 agents) | À venir |
| 5 | Apprentissage & évolution | À venir |
| 6 | Mode pleinement autonome | À venir |

Plan complet : `C:\Users\HP\.claude\plans\bonjour-je-suis-mke-snoopy-sundae.md`

---

## Structure du projet

```
IA-Expert-Army/
├── src/
│   ├── orchestrator/       # Couche 1 — leadership
│   ├── guilds/             # Couche 2 — agents spécialisés (4 guildes)
│   ├── memory/             # Couche 3 — mémoire à 4 niveaux
│   ├── mcp_servers/        # serveurs MCP custom
│   ├── tools/              # outils partagés
│   ├── learning/           # Couche 4 — apprentissage
│   ├── sandbox/            # exécution sécurisée Docker
│   └── core/               # config, logging, types
├── prompts/                # system prompts versionnés (markdown)
├── skills/                 # procédures réussies (markdown)
├── data/                   # mémoire persistée (gitignorée)
├── infra/                  # docker-compose, k8s, etc.
├── scripts/                # CLI tools (hello, check, run_mission)
├── tests/                  # pytest (unit + integration)
└── docs/                   # documentation
```

---

## Garde-fous (mode autonome)

Le système est conçu pour fonctionner de manière autonome. Les garde-fous **non négociables** :

1. Sandbox Docker pour toute exécution de code
2. Filesystem restreint (whitelist)
3. Pas d'accès réseau par défaut (whitelist explicite)
4. Hard cap budget API journalier
5. Circuit breakers sur taux d'erreur
6. Approbation humaine pour : prod deploy, dépenses > N€, suppressions massives, envois externes
7. Logs immutables (Langfuse)
8. Killswitch global
9. Daily digest envoyé à l'utilisateur
10. Backups automatiques

---

## Licence

Propriétaire — © 2026 MikaelArth. Tous droits réservés.
