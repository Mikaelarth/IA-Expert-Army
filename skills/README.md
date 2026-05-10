# Skills Library

> Bibliothèque de **procédures réussies** que les agents apprennent et réutilisent.

## Pourquoi cette bibliothèque ?

Les LLM ne mettent pas à jour leurs poids à l'exécution. Cette skills library est notre
**substitut à l'apprentissage** : elle stocke les procédures qui ont mené à des succès
mesurables (quality_score ≥ 0.85), et les agents les consultent (RAG) avant d'agir.

## Format d'une skill

Un fichier markdown par skill, avec frontmatter YAML :

```markdown
---
guild: engineering            # engineering | research | creative | business | orchestrator
role: backend_developer       # rôle qui a appris cette skill
task_type: api_endpoint       # catégorie sémantique
quality_score: 0.94           # score moyen sur les missions où elle a été appliquée
tags: [fastapi, sqlalchemy, async]
created_at: 2026-06-01
last_used_at: 2026-09-12
times_used: 17
times_succeeded: 16
---

## Contexte
<Quand cette skill s'applique>

## Approche gagnante
1. ...
2. ...

## Code clé / template
```python
...
```

## Pièges connus
- ...

## Sources d'apprentissage
- mission:abc123 (score 0.97)
- mission:def456 (score 0.91)
```

## Cycle de vie d'une skill

1. **Observation** : Pattern Mining (Couche 4) détecte une séquence répétée à fort succès.
2. **Création** : un agent (ou l'orchestrateur) rédige la skill et la commit ici.
3. **Adoption** : la skill est injectée en few-shot dans les agents pertinents.
4. **Mesure** : son taux de succès est tracké dans Langfuse.
5. **Évolution** : si le score baisse, elle est révisée ou retirée.
6. **Versioning** : chaque modification est un commit Git, pour audit complet.

## Statut actuel

Phase 0 — bibliothèque vide. Premières skills attendues à partir de la Phase 5.
