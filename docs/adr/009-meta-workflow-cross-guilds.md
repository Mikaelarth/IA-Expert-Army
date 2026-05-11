# ADR-009 — MetaWorkflow cross-guildes (Phase 7)

**Statut :** Accepted
**Date :** 2026-05-11 (introduit commits `239ada6` séquentiel + `bb29a6d` parallélisation)

## Contexte

Le plan d'architecture (cf. master plan + ADR-001) promet un cas d'usage central :

> *« Mission test : crée un produit SaaS complet — code Engineering + landing page Creative + business plan Business. »*

Jusqu'en Phase 6 inclusive, le `MissionRouter` ne pouvait dispatcher qu'à **une seule guilde par mission**. Une mission qui couvrait plusieurs domaines obligeait l'utilisateur à :

1. Couper manuellement la mission en N sous-missions.
2. Lancer N commandes séquentiellement.
3. Re-injecter manuellement les livrables amont dans la description aval.
4. Compiler les résultats.

C'était fonctionnel mais sans le bénéfice « armée d'agents qui collaborent », et le pitch principal du framework ne tenait pas debout.

## Décision

Introduire un **`MetaWorkflow`** qui orchestre une mission cross-domaine en 3 étapes :

1. **Décomposition** — un agent `MetaDecomposer` (Claude Opus, prompt strict) reçoit la mission et produit en YAML une liste de 2 à 4 sous-missions, chacune routée vers **une seule** guilde, avec un graphe de dépendances `depends_on` minimal.
2. **Dispatch parallèle par niveaux** — `_level_order` calcule les niveaux du DAG (Kahn modifié), puis pour chaque niveau, `asyncio.gather` lance toutes les sous-missions du niveau en parallèle via le `MissionRouter` existant. Le contexte amont (résumé des sous-missions des niveaux précédents) est injecté en haut de la description aval avant exécution.
3. **Agrégation** — un `MetaMissionResult` collecte coût total, score moyen, verdict global (REJECTED si une sub-mission rejette, APPROVED ssi toutes approuvées, NEEDS_CHANGES sinon), et un récap markdown persisté dans `data/memory/meta_missions/<uuid>.md`.

### Pourquoi NE PAS dupliquer la logique de routage

Le `MetaWorkflow` **réutilise** `MissionRouter.run(force_guild=...)` plutôt que d'invoquer directement les workflows de guilde. Bénéfices :
- Tous les garde-fous (`BudgetController`, `Killswitch`, RAG, sandbox, learning loop) restent en place sans duplication.
- Chaque sub-mission produit un `UnifiedMissionResult` standard archivé dans `data/memory/missions/` — donc utilisable par `list_recent_missions` MCP, le PatternMiner nightly, etc.
- Si une guilde change ses internals, le MetaWorkflow ne casse pas.

### Pourquoi parallélisation par niveaux et non topologique pure

La v1 du MetaWorkflow utilisait `_topological_order` et exécutait séquentiellement (commit `239ada6`). Sur la mission canonique water-tracker du 2026-05-11 (cf. mission `2180093b…`), les 3 sub-missions étaient indépendantes (`depends_on=[]` toutes les 3), mais elles tournaient quand même en série : engineering 108s → creative 78s → business 422s = **625s total**. Avec `_level_order` + `asyncio.gather`, ce même cas devient **1 niveau de 3 en parallèle** ≈ max(108, 78, 422) = ~422s, soit -32 %. Sur des patterns diamond (1 → {2, 3} → 4), le gain dépasse 50 %.

### Tolérance aux échecs en parallèle

`asyncio.gather(*coros, return_exceptions=True)` : l'échec d'une sub-mission **ne tue pas les autres** du même niveau. Elles finissent leur travail, leurs épisodes sont archivés, et le `MetaWorkflow` lève après coup avec un message agrégé listant les échecs. Rationale : ne pas perdre du travail déjà payé en API.

## Conséquences

**Positives :**
- Premier vrai support « une armée qui collabore » : 3 guildes produisent des livrables cohérents en parallèle.
- Le `MetaDecomposer` adapte sa stratégie selon le contexte (diamond vs all-parallel vs chaîne) — pas de schéma figé.
- Coût additionnel limité : ~$0.11 pour la décomposition Opus, négligeable face aux ~$0.50–1.50 d'une sub-mission.
- Pas de duplication de code : le `MissionRouter` reste l'unique point d'entrée vers les guildes.

**Négatives / à surveiller :**
- **Budget non strictement précis en mode parallèle** : si plusieurs sub-missions chargent le `BudgetController` simultanément, le read-modify-write sur `data/budget_state.json` n'est pas verrouillé. Imprécision typique = quelques cents. Le hard-cap reste robuste car le killswitch bloque le **prochain** appel (pas le courant). Mitigation future : verrou fichier `fcntl`/portable.
- **Limite 2-4 sub-missions hardcodée dans le décomposeur** : volontaire pour éviter les missions ingérables. Si on en a besoin plus tard (5+), c'est un changement de prompt + bump de la garde dans `_parse_decomposition`.
- **Non-déterminisme du décomposeur** : Opus peut produire des décompositions différentes pour la même mission (observé : water-tracker décomposé en diamond la 1ʳᵉ fois, all-parallel la 2ᵉ fois). C'est une feature (Opus s'adapte) mais rend les benchmarks de coût/durée moins comparables. Mitigation : versionner les meilleurs prompts via le système A/B (ADR-007).

## Alternatives considérées

- **Heuristique mots-clés multi-guildes pour la décomposition** (sans appel LLM) : rejeté → trop fragile. Identifier que « lance un SaaS » = engineering + creative + business demande du raisonnement sémantique, pas du keyword counting. Le coût additionnel de $0.11 par décomposition est largement justifié.
- **Approche LangGraph stateful** : reportée. LangGraph est dans le tech stack (ADR-002) mais sera adopté quand on aura besoin de **conversation persistante** entre sub-missions (Phase 8+). Pour le MVP v1/v2, asyncio.gather + dict des résultats suffit.
- **Décomposeur Sonnet au lieu d'Opus** : testé mentalement, rejeté → la qualité du choix de guildes + des dépendances dépend d'un raisonnement subtil (ex. « la roadmap doit-elle vraiment être amont du code, ou pas ? »). Opus produit des décompositions plus défendables. Le coût additionnel de la décomposition stratégique vaut l'investissement.
- **Génération de skill « MetaDecomposition pattern X » par le PatternMiner** : pour plus tard. Si l'apprentissage produit des skills sur les patterns de décomposition qui fonctionnent bien, on les injectera dans le prompt du MetaDecomposer.

## Pour la suite

- **v3 (Phase 8)** : conversation continue entre sub-missions (LangGraph) — si certaines missions nécessitent un dialogue itératif inter-guildes (ex. engineering qui demande clarification à business en cours de route).
- **Métriques** : ajouter au daily_digest un compteur « meta-missions exécutées aujourd'hui » + coût moyen + durée moyenne par pattern (all-parallel/diamond/chain).
- **MCP** : exposer un tool `list_recent_meta_missions(limit, verdict?)` similaire à `list_recent_missions`, pour la consommation par Claude Desktop.
- **CI** : ajouter un test d'intégration optionnel `pytest -m meta` qui lance le MetaDecomposer avec une mock fixture YAML (sans coût API) pour valider que le wiring `_decompose → _level_order → router.run → _aggregate` reste cohérent.
