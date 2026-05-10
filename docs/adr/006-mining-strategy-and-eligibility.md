# ADR-006 — Stratégie de mining et critères d'éligibilité des épisodes

**Statut :** Accepted
**Date :** 2026-05-10

## Contexte

Le PatternMiner (couche 4) extrait automatiquement des skills réutilisables depuis les épisodes passés. La qualité des skills produites dépend ENTIÈREMENT de la qualité des épisodes utilisés en input. Un seul épisode pollué (output tronqué, mission rejetée, contenu incohérent) peut générer une skill nuisible qui pollue ensuite TOUTES les futures missions de cet agent.

Plusieurs incidents ont validé cette préoccupation :
- Initialement, le filtre acceptait les épisodes de missions REJECTED (le `success` au niveau de l'agent individuel ne reflète pas le verdict global). Résultat : pollution potentielle.
- Les épisodes saturés (output tronqué) passaient également si leur quality_score n'était pas explicitement bas.
- Le whitelist était tenu manuellement → 2 oublis observés (Research puis Creative non whitelistés à leur introduction).

## Décision

**4 critères stricts cumulatifs** d'éligibilité au mining, appliqués dans `PatternMiner._load_eligible_episodes()` :

```python
# Filtre 1 : exécution agent réussie au niveau API
if not meta.get("success"):
    continue

# Filtre 2 : pas d'output tronqué
if meta.get("saturated") is True:
    continue

# Filtre 3 : si la mission a été reviewée, elle DOIT être APPROVED
final_verdict = meta.get("final_verdict")
if final_verdict and final_verdict != "APPROVED":
    continue

# Filtre 4 : agent dans le whitelist explicite
agent = meta.get("agent", "")
if agent not in self.agents:
    continue

# Filtre 5 : si quality_score présent, doit être >= min_quality (défaut 0.85)
score = meta.get("quality_score")
if isinstance(score, (int, float)) and score < self.min_quality:
    continue
```

**Règle complémentaire** : `min_episodes >= 2` par défaut. Une skill basée sur un seul échantillon serait juste une généralisation hâtive — on attend au moins 2 missions réussies du même agent avant d'extraire un pattern.

## Conséquences

**Positives :**
- Les 11 skills auto-générées à ce jour sont toutes basées sur des épisodes APPROVED non-saturés. Aucune pollution observée en production.
- Quand un agent ne peut pas être miné (ex. document_synthesizer pendant longtemps : tous ses épisodes saturés à 4096 avant le fix), le système le SIGNALE au lieu de produire une skill médiocre.
- L'utilisateur peut auditer à tout moment quels épisodes nourrissent chaque skill (frontmatter `sources` + sources_avg_score).

**Négatives / à surveiller :**
- Le filtrage est strict → période de "froid" pour les nouvelles guildes (besoin de 2+ missions APPROVED avant le 1er mining). Acceptable.
- Le `min_quality=0.85` par défaut rejette des épisodes "moyennement bons" (0.80-0.84) qui pourraient porter de l'information utile. Trade-off conscient en faveur de la qualité.

## Whitelist des agents minés

Maintenu manuellement dans `PatternMiner.AGENT_WHITELIST`. Convention : à chaque nouvelle guilde, ajouter ses agents ET ajouter un test de régression `test_whitelist_includes_all_<guild>_agents`.

```python
AGENT_WHITELIST: tuple[str, ...] = (
    "chief_orchestrator",  # Direction
    "software_architect", "backend_developer", "code_reviewer",  # Engineering
    "research_lead", "tech_watch", "document_synthesizer", "research_reviewer",  # Research
    "content_strategist", "copywriter", "editor",  # Creative
    "project_manager", "business_analyst", "legal_reviewer",  # Business
)
```

**Phase 5+** : passer à un chargement dynamique depuis les workflows pour éliminer le risque d'oubli (déjà arrivé deux fois).

## Boucle d'apprentissage validée

À ce jour (sessions 1-5), la boucle `mission → mémoire → mining → skill → injection → réutilisation citée par l'agent` est observable en production sur **3 guildes sur 4** :

- **Engineering** : Architect mission `/ready` cite skill « FastAPI metadata router design spec »
- **Research** : Tech Watch mission « Rate limiting » cite explicitement « **Skill 1 (findings YAML structuré)** : chaque SQ a 5-7 findings atomiques »
- **Creative** : Content Strategist mission « Argumentaire CTO » cite la boucle elle-même comme preuve

**Business** : skills générées à cette session (5), pas encore validation directe d'auto-citation observée — attendue en prochaine mission Business.

## Alternatives considérées

- **Mining sur tous les épisodes (filtre lâche) :** rejeté → pollution garantie par les 30%+ d'épisodes problématiques observés.
- **Apprentissage par renforcement (RLHF/DPO sur les feedbacks) :** considéré → reporté en Phase 5++. Nécessite infrastructure ML séparée et beaucoup plus de données.
- **Skills extraites manuellement par l'utilisateur :** rejeté → contredit l'objectif d'auto-amélioration sans intervention.
