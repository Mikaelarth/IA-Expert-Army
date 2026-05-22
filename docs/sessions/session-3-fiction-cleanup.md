# Session 3 — Nettoyage des fictions architecturales

**Date** : 2026-05-20
**Branche** : `feat/ollama-backend`
**Sprint** : v0.4.0 préparation
**Critère contrat couvert** : #1 (No fictional features in docs)

---

## Contexte

`docs/architecture.md` avait été rédigé en mode "vision" en Phase 0-1 du projet, listant tous les agents et services qu'on **prévoyait** d'implémenter. Au fil des sprints, certains ont été livrés, d'autres reportés sine die, d'autres remplacés. La doc n'avait pas été mise à jour, créant un décalage substantiel entre **promesse documentée** et **réalité du code**.

À l'audit Session 3, **8 agents fictifs** et **4 MCP servers fictifs** étaient listés en `architecture.md` sans une ligne de code correspondante. Plus quelques fonctionnalités infrastructure (Redis non-câblé, Knowledge Graph SQLite, Chief of Staff) qui étaient documentées mais n'avaient jamais été démarrées.

Le critère #1 du contrat Enterprise négocié en Session 0 — **"Aucune fonctionnalité fictive dans la doc"** — exigeait un nettoyage.

---

## Inventaire des fictions résiduelles

### Agents documentés mais absents du code

| Agent | Statut réel | Décision |
|---|---|---|
| `prompt_engineer` | Jamais implémenté | Tagué `⏳ Planifié Phase 6` |
| `data_engineer` | Jamais implémenté | Tagué `⏳ Planifié Phase 6` |
| `frontend_developer` | Jamais implémenté | Tagué `⏳ Planifié Phase 7` |
| `devops_engineer` | Jamais implémenté | Tagué `⏳ Planifié Phase 7` |
| `qa_engineer` | Jamais implémenté | Tagué `⏳ Planifié Phase 5+` |
| `customer_support` | Hors-scope produit | Retiré complètement |
| `community_manager` | Hors-scope produit | Retiré complètement |
| `pr_manager` | Hors-scope produit | Retiré complètement |

### MCP servers documentés mais absents

| MCP | Statut réel | Décision |
|---|---|---|
| `code_search_mcp` | Jamais implémenté | Tagué `⏳ Planifié` |
| `git_history_mcp` | Jamais implémenté | Tagué `⏳ Planifié` |
| `notion_sync_mcp` | Hors-scope produit | Retiré |
| `linear_mcp` | Hors-scope produit | Retiré |

Seul **`memory_search_mcp`** (6 tools) existe réellement, livré Sprint III.

### Infrastructure documentée mais non-câblée

| Composant | Statut réel | Décision |
|---|---|---|
| **Redis** | Container `docker-compose.yml` profile `infra`, MAIS aucun import dans `src/` | Annoté `📌 Phase 5+` dans architecture.md (sera utile pour cache de prompts cross-process) |
| **Knowledge Graph SQLite** | Container `docker-compose.yml`, schéma `data/knowledge_graph.db` jamais créé | Annoté `📌 Phase 6+` (refactor mémoire structurée prévu) |
| **Chief of Staff** | Documenté comme "agent méta de plus haut niveau", aucune classe | Annoté `⏳ Planifié Phase 7` |

---

## Stratégie

Plutôt qu'un grand refactor qui supprimerait des sections entières, on **tague** explicitement chaque entrée fictive avec l'un de :

- `⏳ Planifié <Phase>` — feature à venir, l'ADR pertinent existe ou existera
- `📌 Phase <X>+` — infrastructure présente en compose mais pas câblée dans le code Python
- *(retiré)* — fonctionnalité hors-scope définitive, supprimée

Ça permet à un lecteur de la doc de distinguer instantanément ce qui marche (sans tag), ce qui est promis (tag ⏳), ce qui est infrastructure prête (tag 📌), ce qui est abandonné (retrait sec).

---

## Fichiers touchés

| Fichier | Modifications |
|---|---|
| `docs/architecture.md` | 8 agents tagués/retirés, 4 MCP tagués/retirés, Redis/KG/CoS annotés |
| `docs/runbook.md` | Section "Outils MCP disponibles" : 6 tools `memory_search` listés, 4 fictifs supprimés |
| `docs/getting-started.md` | Étape 5 simplifiée : on liste les agents qui marchent (14), pas ceux qui sont prévus |
| `README.md` | Section "État du projet" : 4 guildes documentées + Chief of Staff retiré (tagué Phase 7) |
| `prompts/README.md` | Liste des agents actuels mise à jour |

---

## Validation

- `mkdocs build --strict` : 0 warning (aucun lien cassé après les retraits)
- Lecture humaine de bout en bout (architecture.md, README.md, getting-started.md) — aucune feature mentionnée sans correspondance dans `src/`
- `grep -rn "Chief of Staff\|knowledge_graph\|prompt_engineer\|customer_support" src/ tests/` — 0 référence orpheline

---

## Décisions retenues

- **Garder Redis + KG en docker-compose** : leurs containers ne coûtent rien à laisser, et un futur sprint pourra les câbler sans re-discuter l'infra. Annotation explicite suffit.
- **Tag `⏳ Planifié`** plutôt que retrait pur : préserve l'intention produit (utile pour les contributeurs futurs qui se demandent "pourquoi pas un frontend_developer ?"). Le tag est honnête : il y a une intention, pas une promesse.
- **Pas d'ADR rétrospectif** pour chaque retrait : la Session 3 documente le nettoyage en bloc. Les futurs ajouts d'agents devront chacun ouvrir un ADR.

---

## Résultats

- **0 fonctionnalité fictive** en doc post-Session 3.
- `mkdocs --strict` propre.
- Critère contrat #1 ✅ validé empiriquement.
- Lecture du README → premier mile : aligné sur le code réel, plus de promesse en l'air.

---

## Suite

→ [Session 4 — Prompt code_reviewer v0.2.0](session-4-prompt-improvement.md)
