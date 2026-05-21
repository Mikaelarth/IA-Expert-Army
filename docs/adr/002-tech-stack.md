# ADR-002 — Stack technique : Python + Claude Agent SDK + Chroma + Docker

**Statut :** Partiellement superseded par [ADR-025](025-bascule-anthropic-to-ollama.md) — la dépendance SDK Anthropic / Claude API est retirée depuis v0.4.0 (bascule Ollama local via SDK `openai` pointé sur localhost:11434/v1). Le reste de la stack reste valide : Python 3.12+ / uv / Chroma / Docker / Pydantic v2 / structlog. Les mentions "Bus Redis pubsub Phase 3+" et "SQLite Phase 1 → PostgreSQL Phase 3+" sont restées à l'état de vision (cf. tableau État d'implémentation dans [architecture.md](../architecture.md)).
**Date :** 2026-05-10

## Contexte

Choisir une stack pour un projet d'agents IA en 2026, qui soit :
- Mature (production-ready, communauté active)
- Bien outillée pour Anthropic Claude (cible principale du projet)
- Compatible avec un déploiement local-first (l'utilisateur veut la maîtrise)
- Ouverte (pas de vendor lock-in autre que Anthropic API)

Une recherche web mai 2026 a confirmé les rangs production : **LangGraph #1**, **Claude Agent SDK #2**, **CrewAI #3**.

## Décision

| Composant | Choix | Justification |
|---|---|---|
| **Langage** | Python 3.12+ | Écosystème IA le plus riche (Anthropic SDK, Chroma, Pydantic, structlog…). |
| **Package manager** | uv (Astral) | 10–100× plus rapide que pip, gère aussi l'install Python. |
| **SDK Claude** | `anthropic` (officiel) puis `claude-agent-sdk` | Démarrage simple sur l'API basique, montée vers SDK officiel quand on intègre MCP. |
| **Orchestration stateful (futur)** | LangGraph | Pour workflows DAG complexes (Phase 3+). En Phase 1 : chaîne linéaire custom suffit. |
| **Vector DB** | Chroma (PersistentClient, in-process) | Pas de container Docker à gérer en Phase 2. Migration Qdrant en Phase 3+ si besoin de scale. |
| **DB structurée** | SQLite (Phase 1) → PostgreSQL (Phase 3+) | Démarrage local, migration progressive. |
| **Bus messages (Phase 3+)** | Redis pubsub | Léger, fiable, async natif. |
| **Sandbox** | Docker + docker-py | Standard de l'industrie, isolement éprouvé. |
| **Observabilité (Phase 3+)** | Langfuse self-hosted | Open-source, traçage complet, gratuit en local. |
| **Validation typée** | Pydantic v2 | Déjà standard dans l'écosystème FastAPI/LangChain. |
| **Logging** | structlog | JSON ou console, processeurs composables. |
| **Tests** | pytest + pytest-asyncio | Standard Python. |

## Conséquences

**Positives :**
- Stack 100% open-source côté infrastructure ; seul Anthropic API est payant et propriétaire.
- Écosystème riche : chaque brique a alternatives si une tombe.
- Local-first : tout le pipeline tourne sur la machine de l'utilisateur sans cloud.
- L'utilisateur peut versionner mémoire, skills, prompts dans Git.

**Négatives / à surveiller :**
- Python 3.14 a été installé par uv (dispo) — quelques libs (chromadb) font des deprecation warnings sur `asyncio.iscoroutinefunction` (Py 3.16). Pas bloquant mais à monitorer.
- Vendor lock-in Anthropic : si Claude devient indisponible/cher, refactor majeur. Mitigation : abstraire les appels LLM derrière une interface, possibilité de plugger Llama local en Phase 3+.
- Stack assez dense (Python + Docker + Chroma + Redis + Langfuse) — attention à ne pas multiplier les briques avant d'en avoir besoin réel.

## Alternatives considérées

- **TypeScript/Node.js :** rejeté → écosystème IA moins riche, perte d'accès à des libs Python clés (chromadb, langgraph).
- **Framework tiers seul (CrewAI ou LangGraph dès le départ) :** rejeté → trop opinioné pour un projet greenfield, on perd le contrôle fin sur la mémoire et les workflows.
- **Construire entièrement from scratch sur API brute :** rejeté → réinvente la roue (subagents, MCP, schémas de retry…).
- **Pinecone/Qdrant cloud pour la mémoire vectorielle :** rejeté → contraire au principe local-first et coût additionnel.
