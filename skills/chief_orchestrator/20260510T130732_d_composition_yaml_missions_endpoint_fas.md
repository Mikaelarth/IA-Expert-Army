---
summary: 'Pour une mission "implémenter un endpoint FastAPI + test", le chief_orchestrator
  produit

  un YAML structuré avec mission_understanding détaillé, 3-4 tâches séquentielles
  (router →

  test → vérif config → validation), et une section risks_and_mitigations couvrant
  les pièges

  techniques connus (httpx versions, subprocess, types Pydantic, pytest-asyncio config).'
tags:
- fastapi
- decomposition
- yaml
- endpoint
- test-async
sources:
- 20260510T122127_4fd70396_chief_orchestrator
- 20260510T124011_b0d6e871_chief_orchestrator
sources_avg_score: 0.0
extracted_from: 2
skill_id: 20260510T130732_d_composition_yaml_missions_endpoint_fas
agent: chief_orchestrator
title: Décomposition YAML missions endpoint FastAPI
created_at: '2026-05-10T13:07:32.695391+00:00'
---

## Résumé

Pour une mission "implémenter un endpoint FastAPI + test", le chief_orchestrator produit
un YAML structuré avec mission_understanding détaillé, 3-4 tâches séquentielles (router →
test → vérif config → validation), et une section risks_and_mitigations couvrant les pièges
techniques connus (httpx versions, subprocess, types Pydantic, pytest-asyncio config).

## Patterns clés
- mission_understanding réécrit la spec en clarifiant types exacts, valeurs littérales et contraintes implicites (ex. format regex, fallback)
- Décomposition en 3-4 tâches courtes : T1 implémentation router, T2 test async, T3 vérif config/intégration, T4 optionnel quality_guardian
- Dépendances explicites via depends_on créant une chaîne linéaire claire (T1 → T2 → T3 → T4)
- Assignation cohérente : backend_dev pour le code, qa_engineer pour les tests, quality_guardian pour la revue finale
- risks_and_mitigations liste 4-5 pièges techniques précis avec leur parade concrète, pas des risques génériques
- Réutilisation explicite du contexte des missions précédentes similaires (cite le /health précédent dans /version)

## Techniques
- Spécifier ASGITransport(app=app) explicitement (httpx >= 0.27) plutôt que AsyncClient(app=...) deprecated
- Forcer types stricts : float(...) explicite, regex souple pour python_version, set-equality pour clés JSON
- Patterns de robustesse : timeout subprocess + try/except large + valeur fallback ('unknown')
- Caching module-level pour calculs one-shot (START_TIME, git_commit) afin d'éviter side-effects répétés
- Assertions de test portant sur type/format plutôt que valeur exacte quand la valeur peut varier (git_commit, uptime)
- Estimations explicites : estimated_cost_usd et estimated_duration_minutes en fin de YAML

## Pièges évités
- Ne pas oublier la configuration pytest-asyncio (sinon test silencieusement skipped)
- Ne pas asserter une valeur exacte sur des champs dynamiques (commit hash, version Python) → test flaky
- Ne pas laisser subprocess git bloquer indéfiniment ou crasher en environnement Docker sans .git
- Ne pas utiliser l'API httpx deprecated (AsyncClient(app=...))
- Ne pas créer d'imports circulaires : router autonome dans son propre fichier

## Template d'exemple

```
mission_understanding: |
  <reformulation précise de la spec avec types exacts et contraintes>
decomposition:
  - id: T1
    title: Implémenter <composant>
    assigned_to: engineering.backend_dev
    depends_on: []
    deliverable: |
      <fichier + contenu attendu en bullets>
  - id: T2
    title: Écrire le test
    assigned_to: engineering.qa_engineer
    depends_on: [T1]
    deliverable: |
      <fichier test + assertions précises>
  - id: T3
    title: Validation finale
    assigned_to: engineering.quality_guardian
    depends_on: [T1, T2]
    deliverable: <revue + checklist>
risks_and_mitigations:
  - "<piège technique précis> → <parade concrète>"
estimated_cost_usd: 0.05
estimated_duration_minutes: 5
```

## Sources
- 20260510T122127_4fd70396_chief_orchestrator (score n/a)
- 20260510T124011_b0d6e871_chief_orchestrator (score n/a)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
```yaml
title: Décomposition YAML missions endpoint FastAPI
agent: chief_orchestrator
tags:
  - fastapi
  - decomposition
  - yaml
  - endpoint
  - test-async
summary: |
  Pour une mission "implémenter un endpoint FastAPI + test", le chief_orchestrator produit
  un YAML structuré avec mission_understanding détaillé, 3-4 tâches séquentielles (router →
  test → vérif config → validation), et une section risks_and_mitigations couvrant les pièges
  techniques connus (httpx versions, subprocess, types Pydantic, pytest-asyncio config).
key_patterns:
  - "mission_understanding réécrit la spec en clarifiant types exacts, valeurs littérales et contraintes implicites (ex. format regex, fallback)"
  - "Décomposition en 3-4 tâches courtes : T1 implémentation router, T2 test async, T3 vérif config/intégration, T4 optionnel quality_guardian"
  - "Dépendances explicites via depends_on créant une chaîne linéaire claire (T1 → T2 → T3 → T4)"
  - "Assignation cohérente : backend_dev pour le code, qa_engineer pour les tests, quality_guardian pour la revue finale"
  - "risks_and_mitigations liste 4-5 pièges techniques précis avec leur parade concrète, pas des risques génériques"
  - "Réutilisation explicite du contexte des missions précédentes similaires (cite le /health précédent dans /version)"
techniques:
  - "Spécifier ASGITransport(app=app) explicitement (httpx >= 0.27) plutôt que AsyncClient(app=...) deprecated"
  - "Forcer types stricts : float(...) explicite, regex souple pour python_version, set-equality pour clés JSON"
  - "Patterns de robustesse : timeout subprocess + try/except large + valeur fallback ('unknown')"
  - "Caching module-level pour calculs one-shot (START_TIME, git_commit) afin d'éviter side-effects répétés"
  - "Assertions de test portant sur type/format plutôt que valeur exacte quand la valeur peut varier (git_commit, uptime)"
  - "Estimations explicites : estimated_cost_usd et estimated_duration_minutes en fin de YAML"
pitfalls_avoided:
  - "Ne pas oublier la configuration pytest-asyncio (sinon test silencieusement skipped)"
  - "Ne pas asserter une valeur exacte sur des champs dynamiques (commit hash, version Python) → test flaky"
  - "Ne pas laisser subprocess git bloquer indéfiniment ou crasher en environnement Docker sans .git"
  - "Ne pas utiliser l'API httpx deprecated (AsyncClient(app=...))"
  - "Ne pas créer d'imports circulaires : router autonome dans son propre fichier"
example_template: |
  mission_understanding: |
    <reformulation précise de la spec avec types exacts et contraintes>
  decomposition:
    - id: T1
      title: Implémenter <composant>
      assigned_to: engineering.backend_dev
      depends_on: []
      deliverable: |
        <fichier + contenu attendu en bullets>
    - id: T2
      title: Écrire le test
      assigned_to: engineering.qa_engineer
      depends_on: [T1]
      deliverable: |
        <fichier test + assertions précises>
    - id: T3
      title: Validation finale
      assigned_to: engineering.quality_guardian
      depends_on: [T1, T2]
      deliverable: <revue + checklist>
  risks_and_mitigations:
    - "<piège technique précis> → <parade concrète>"
  estimated_cost_usd: 0.05
  estimated_duration_minutes: 5
sources_count: 2
```
```

</details>
