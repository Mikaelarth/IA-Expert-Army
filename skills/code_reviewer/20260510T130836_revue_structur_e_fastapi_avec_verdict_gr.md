---
summary: 'Revue de code Python/FastAPI structurée en YAML avec verdict + quality_score,
  forces explicites,

  et issues hiérarchisées par sévérité (blocker/major/minor/nit). Approuve quand l''alignement

  architectural est respecté et les tests couvrent les branches critiques, en signalant
  les

  pièges subtils (sérialisation JSON, monkeypatching, ordre d''imports) sans bloquer
  pour du nit.'
tags:
- code-review
- fastapi
- python
- testing
- severity-grading
sources:
- 20260510T122228_4fd70396_code_reviewer
- 20260510T124137_b0d6e871_code_reviewer
sources_avg_score: 0.0
extracted_from: 2
skill_id: 20260510T130836_revue_structur_e_fastapi_avec_verdict_gr
agent: code_reviewer
title: Revue structurée FastAPI avec verdict gradué
created_at: '2026-05-10T13:08:36.167479+00:00'
---

## Résumé

Revue de code Python/FastAPI structurée en YAML avec verdict + quality_score, forces explicites,
et issues hiérarchisées par sévérité (blocker/major/minor/nit). Approuve quand l'alignement
architectural est respecté et les tests couvrent les branches critiques, en signalant les
pièges subtils (sérialisation JSON, monkeypatching, ordre d'imports) sans bloquer pour du nit.

## Patterns clés
- Verdict APPROVED même avec issues, tant qu'aucune n'est blocker/major et required_actions est vide
- quality_score élevé (0.92-0.93) corrélé à un alignement strict avec la proposition d'architecture
- Strengths listés en premier et nommément : alignement archi, couverture exceptions, conventions imports, type hints, docstrings
- Issues triées par sévérité décroissante, chacune avec file/line/category/message/suggestion
- Catégories d'issues récurrentes : correctness, tests, conventions, lisibility
- Suggestions toujours accompagnées d'un snippet de code concret prêt à coller

## Techniques
- Détecter les pièges JSON typing (int vs float, ex. 0.0 sérialisé en 0)
- Vérifier la cible du monkeypatch (module d'usage vs module d'origine) pour résistance au refactor
- Contrôler l'ordre des imports (stdlib → tiers → projet, alphabétique intra-groupe)
- Vérifier l'usage d'APIs non-dépréciées (ex. ASGITransport pour httpx>=0.27)
- Évaluer l'exhaustivité des branches d'exceptions testées vs spécifiées
- Suggérer __all__ pour modules à frontière publique/privée explicite

## Pièges évités
- Bloquer un PR pour des nits stylistiques (ordre imports, helpers manquants)
- Approuver sans citer précisément file+line+catégorie pour chaque issue
- Donner un message d'issue sans suggestion de correctif concret
- Confondre minor (correctness avec edge case réel) et nit (préférence de style)
- Oublier de saluer les bons choix : la section strengths n'est pas optionnelle

## Template d'exemple

```
verdict: APPROVED  # ou CHANGES_REQUESTED / REJECTED
quality_score: 0.92
summary: |
  <2-4 lignes : alignement archi, couverture, choix techniques, niveau d'issues>
strengths:
  - "<choix architectural respecté précisément>"
  - "<robustesse / couverture exceptions>"
  - "<convention de code / type hints / docstrings>"
issues:
  - severity: minor  # blocker | major | minor | nit
    file: <path>
    line: <int|null>
    category: correctness  # correctness | tests | conventions | lisibility | security | perf
    message: |
      <explication du problème + pourquoi c'est un piège réel>
    suggestion: |
      <snippet de code corrigé prêt à coller>
required_actions: []  # rempli uniquement si verdict != APPROVED
```

## Sources
- 20260510T122228_4fd70396_code_reviewer (score n/a)
- 20260510T124137_b0d6e871_code_reviewer (score n/a)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
```yaml
title: Revue structurée FastAPI avec verdict gradué
agent: code_reviewer
tags:
  - code-review
  - fastapi
  - python
  - testing
  - severity-grading
summary: |
  Revue de code Python/FastAPI structurée en YAML avec verdict + quality_score, forces explicites,
  et issues hiérarchisées par sévérité (blocker/major/minor/nit). Approuve quand l'alignement
  architectural est respecté et les tests couvrent les branches critiques, en signalant les
  pièges subtils (sérialisation JSON, monkeypatching, ordre d'imports) sans bloquer pour du nit.
key_patterns:
  - "Verdict APPROVED même avec issues, tant qu'aucune n'est blocker/major et required_actions est vide"
  - "quality_score élevé (0.92-0.93) corrélé à un alignement strict avec la proposition d'architecture"
  - "Strengths listés en premier et nommément : alignement archi, couverture exceptions, conventions imports, type hints, docstrings"
  - "Issues triées par sévérité décroissante, chacune avec file/line/category/message/suggestion"
  - "Catégories d'issues récurrentes : correctness, tests, conventions, lisibility"
  - "Suggestions toujours accompagnées d'un snippet de code concret prêt à coller"
techniques:
  - "Détecter les pièges JSON typing (int vs float, ex. 0.0 sérialisé en 0)"
  - "Vérifier la cible du monkeypatch (module d'usage vs module d'origine) pour résistance au refactor"
  - "Contrôler l'ordre des imports (stdlib → tiers → projet, alphabétique intra-groupe)"
  - "Vérifier l'usage d'APIs non-dépréciées (ex. ASGITransport pour httpx>=0.27)"
  - "Évaluer l'exhaustivité des branches d'exceptions testées vs spécifiées"
  - "Suggérer __all__ pour modules à frontière publique/privée explicite"
pitfalls_avoided:
  - "Bloquer un PR pour des nits stylistiques (ordre imports, helpers manquants)"
  - "Approuver sans citer précisément file+line+catégorie pour chaque issue"
  - "Donner un message d'issue sans suggestion de correctif concret"
  - "Confondre minor (correctness avec edge case réel) et nit (préférence de style)"
  - "Oublier de saluer les bons choix : la section strengths n'est pas optionnelle"
example_template: |
  verdict: APPROVED  # ou CHANGES_REQUESTED / REJECTED
  quality_score: 0.92
  summary: |
    <2-4 lignes : alignement archi, couverture, choix techniques, niveau d'issues>
  strengths:
    - "<choix architectural respecté précisément>"
    - "<robustesse / couverture exceptions>"
    - "<convention de code / type hints / docstrings>"
  issues:
    - severity: minor  # blocker | major | minor | nit
      file: <path>
      line: <int|null>
      category: correctness  # correctness | tests | conventions | lisibility | security | perf
      message: |
        <explication du problème + pourquoi c'est un piège réel>
      suggestion: |
        <snippet de code corrigé prêt à coller>
  required_actions: []  # rempli uniquement si verdict != APPROVED
sources_count: 2
```
```

</details>
