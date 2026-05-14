# ADR-005 — Détection et prévention de la saturation max_tokens

**Statut :** Accepted
**Date :** 2026-05-10

## Contexte

Six incidents de saturation silencieuse ont été observés en production entre les sessions 2 et 5, tous suivant le même schéma :

1. Un agent reçoit un prompt complexe (mission riche, ou input contenant déjà la sortie d'agents précédents).
2. Sa génération est coupée par l'API Anthropic à `max_tokens` exactement (signal explicite `stop_reason: max_tokens`).
3. La sortie est syntaxiquement incomplète (YAML tronqué mid-issue, Markdown coupé à mi-section).
4. Le parser downstream retourne `None`.
5. Le workflow dégrade au verdict default `REJECTED` ou `(no summary)`.
6. La mission est rejetée, **bien que le contenu soit de qualité jusqu'au point de coupure**.

Liste des incidents :

| Incident | Mission | Agent saturé | max_tokens initial | Coût perdu |
|---|---|---|---|---|
| 1 | 359bfa08 | research_reviewer | 2048 | $0.38 |
| 2 | 7b5759b1 | tech_watch | 4096 | $0.35 |
| 3 | 7c98893b | (chain — eng misroutée) | — | $0.78 |
| 4 | 38fd387d | research_reviewer | 4096 | $0.54 |
| 5 | mining bis | skill_extractor | 2048 | $0.63 |
| 6 | 5e1e3cc7 (×2) | document_synthesizer | 4096 | (mission OK mais episodes filtrés) |
| 7 | cc670899 (water-tracker meta) | business_analyst | 6144 (repair loop) | ~$0.78 |
| 8 | 70652f89 (mission étalon DDD) | backend_developer | 4096 (×2 itérations) | ~$0.18 |

**Total dépenses brûlées en saturation : ~$3.64.**

**Note incident 7 (2026-05-11)** : première saturation observée sur un **repair loop**, et sur la **Business Guild**. Contexte : la mission cross-guildes water-tracker (cf. ADR-009 si créé pour le MetaWorkflow) a fait passer la business à 1 boucle de repair. À la 2ᵉ passe, le `business_analyst` reçoit en input le verdict legal complet (~5919 tokens out, riche en `required_actions`) + son analyse v1 + tâche originale = 21404 tokens IN. Output capé à 6144 → analyse tronquée → blockers de conformité (CGU, Privacy Policy, DPA) recommandés en BA mais non gravés dans les Definition of Done des milestones — exactement le détail qu'aurait précisé la fin tronquée. Verdict figé NEEDS_CHANGES, coût gaspillé du repair ~$0.78. Fix : bump à 8192 (aligné avec les reviewers). Leçon : **les agents Business saturent aussi sur missions multi-passes** — la liste historique focalisée Research/Creative était incomplète.

**Note incident 8 (2026-05-14)** : première saturation observée sur le `backend_developer` (Engineering), et premier cas où la saturation se reproduit **identiquement** sur les 2 itérations du repair loop. Contexte : mission étalon DDD (FastAPI todo-list complet avec JWT + CRUD + tests + Dockerfile, ~10 fichiers attendus). À la 1ʳᵉ passe Developer = `tokens_out=4096`, `stop_reason=max_tokens` → conftest.py tronqué + tests/test_*.py manquants + Dockerfile absent. À la 2ᵉ passe (repair) = exactement la même saturation. Le QG a correctement détecté le pattern : *« troncature systématique sur 2 itérations consécutives — signal d'un problème de génération non résolu, qui devrait être adressé par décomposition de livraison plutôt qu'en re-tentant le même format »*. Fix immédiat : bump `BackendDeveloper.DEFAULT_MAX_TOKENS` 4096 → 16384. Fix architectural plus large (décomposition de livraison) tracé dans ADR-015. Leçon : **les développeurs de code multi-fichiers ont besoin d'au moins 16k tokens**, et **le repair loop ne suffit pas pour les saturations** — il faut une stratégie de découpe explicite.

## Décision

Trois mécanismes complémentaires, ordonnés du plus préventif au plus curatif.

### 1. Calibration par défaut généreuse (préventif)

Tous les agents qui produisent du YAML structuré ou du Markdown long ont `DEFAULT_MAX_TOKENS = 8192` minimum. Les agents qui produisent un YAML court (plan stratégique synthétique) sont à 3072–4096. La règle : **partir haut, descendre seulement si on observe une consommation systématiquement basse + un coût significatif à diminuer**.

Valeurs actuelles (mai 2026) :

| Agent | max_tokens | Justification |
|---|---|---|
| Backend Developer | **16384** | Code multi-fichiers (jusqu'à ~10 modules + tests + Dockerfile) — incident 8 |
| Tous les Reviewers | 8192 | YAML avec 6+ issues détaillées + suggestions + analyse repair-loop |
| Tous les Synthesizers (DocSynth, Copywriter) | 8192 | Markdown long (TL;DR + N sections + sources/notes) |
| Tech Watch | 8192 | Findings YAML pour 3-6 sous-questions × 5-7 findings |
| ResearchLead, ContentStrategist | 3072–4096 | Plan/Brief structuré mais court |
| ProjectManager | 4096 | Plan avec 3-6 milestones + risks + checkpoints |
| BusinessAnalyst | 8192 | Analyse économique + survit aux repair loops (incident 7) |
| Chief Orchestrator | 2048 | Décomposition courte |
| Skill Extractor | 4096 | YAML structuré, input parfois énorme (3+ épisodes) |
| MetaDecomposer | 4096 | Décomposition courte (YAML 2-4 sub-missions + rationale) |

### 2. Détection explicite + warning (curatif léger)

`BaseAgent._detect_saturation()` déclenche un WARNING structlog visible et persiste un flag `saturated: True` dans le metadata d'épisode quand :
- `stop_reason == "max_tokens"` (signal API explicite), OU
- `tokens_out >= max_tokens × 99%` (garde-fou défensif)

**Le flag est persistant** : tout système downstream peut filtrer ces épisodes (notamment le PatternMiner qui les exclut du training).

### 3. Tests de régression sur chaque seuil (qualité durable)

Chaque `DEFAULT_MAX_TOKENS` a un test pytest dédié qui assert le minimum empirique avec une docstring citant l'incident qui a motivé la valeur. Exemple :

```python
def test_research_reviewer_max_tokens_high_enough_for_detailed_reviews(...):
    """Régression : 2 incidents successifs de saturation
      - 2048 (mission 359bfa08) → bumped to 4096
      - 4096 (mission 38fd387d, repair loop + 8 issues) → bumped to 8192
    Minimum sûr empirique : 8192."""
    assert agent.max_tokens >= 8192
```

Si quelqu'un tente de baisser (par souci de coût p.ex.), le test échoue avec un pointeur direct vers l'incident historique.

## Conséquences

**Positives :**
- Plus aucune mission perdue silencieusement à la saturation depuis le commit `b61e3da`. Le warning rend le diagnostic immédiat.
- Le PatternMiner ne génère plus de skills pollués par du contenu tronqué.
- Le coût marginal par mission a augmenté (+10-30% sur les agents bumped) mais reste largement compensé par la non-perte des missions ratées.

**Négatives / à surveiller :**
- Pour les agents bumped à 8192, une mission qui n'utiliserait que 1500 tokens paie quand même le tarif `max_tokens × pricing` ? **Non** — Anthropic facture les tokens RÉELLEMENT générés, pas le `max_tokens` demandé. Le risque est purement latence (modèle peut prendre légèrement plus de temps à décider d'arrêter).
- Si un nouvel agent est ajouté sans test régression sur ses max_tokens, on peut reproduire le bug. Mitigation : convention `DEFAULT_MAX_TOKENS = N` + lint manuel à chaque ajout d'agent.

## Alternatives considérées

- **Streaming + détection mid-flow :** rejeté → complexité accrue, gain marginal vs warning post-call.
- **Retry automatique avec max_tokens augmenté quand saturé :** considéré → rejeté pour Phase 4 car retry double le coût et ne garantit pas la non-saturation. À reconsidérer en Phase 5+ avec une stratégie adaptative.
- **JSON mode strict (Anthropic) :** considéré → reporté. Forcerait certains schémas mais n'élimine pas le problème de troncature. Le parser tolérant 3-tiers (commit `6dd5bd3`) résout déjà 90% des cas observés.

## Pour la suite

Quand une 5ᵉ guilde ou de nouveaux agents sont ajoutés, la procédure est :
1. Démarrer à 8192 par défaut pour reviewer/synthesizer/long-form, 4096 pour planner/strategist court.
2. Observer 5+ missions réelles avec saturation tracking activé.
3. Ajouter un test régression `assert max_tokens >= N` avec citation d'incident.
4. Documenter ici (mise à jour de cet ADR) si une nouvelle valeur empirique émerge.
