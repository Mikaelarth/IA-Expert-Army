---
summary: 'Le research_lead produit un plan YAML structuré qui commence systématiquement
  par reformuler

  la "vraie question" sous-jacente (souvent différente de la question littérale),
  décompose en

  5-6 sub_questions avec rationale explicite, liste des sources typées variées, définit
  des

  success_criteria mesurables et nomme explicitement les biais à mitiger.'
tags:
- research-planning
- yaml-output
- question-reformulation
- bias-mitigation
- sub-questions
sources:
- 20260510T151313_35a84f56_research_lead
- 20260510T134803_30a357da_research_lead
- 20260510T152021_e3b5ffdd_research_lead
sources_avg_score: 0.89
extracted_from: 3
skill_id: 20260510T153258_plan_de_recherche_yaml_structur_pour_mis
agent: research_lead
title: Plan de recherche YAML structuré pour missions comparatives
created_at: '2026-05-10T15:32:58.305050+00:00'
---

## Résumé

Le research_lead produit un plan YAML structuré qui commence systématiquement par reformuler
la "vraie question" sous-jacente (souvent différente de la question littérale), décompose en
5-6 sub_questions avec rationale explicite, liste des sources typées variées, définit des
success_criteria mesurables et nomme explicitement les biais à mitiger.

## Patterns clés
- question_reformulation recadre la question naïve en problème stratégique sous-jacent (ex. 'pas X ou Y mais comment optimiser le ratio coût/qualité dans le temps')
- Chaque sub_question est accompagnée d'une rationale qui justifie pourquoi elle est nécessaire (pas juste un découpage thématique)
- Sources typées et diversifiées (docs/papers/benchmarks/community/comparatifs/code) avec expected_signal précis pour chacune
- success_criteria formulés comme livrables vérifiables avec quantifications ("≥ 4 types", "au moins 2 seuils chiffrés", "tableau avec colonnes X/Y/Z")
- risks_of_bias nomme un biais concret + propose une mitigation actionnable (pas juste "attention au biais")
- Une sub_question finale couvre souvent l'évaluation/méta-niveau (méta-évaluation, validation, itération en production)

## Techniques
- Pattern de reformulation : 'La vraie question n'est pas X mais Y' suivi d'un enjeu sous-jacent chiffrable
- IDs stables pour les sub_questions (SQ1, SQ2...) pour permettre le cross-référencement aval
- Distinction explicite des dimensions orthogonales (reference-based vs reference-free, online vs offline, style vs factualité) pour éviter les fausses dichotomies
- {'Sources triangulées': 'croiser docs officielles (biaisées vendor) + papers académiques + retours terrain praticiens nommés (Willison, Husain, Yan, Huyen)'}
- estimated_breadth déclaré (medium/deep) en fin de plan pour calibrer l'effort aval
- Forcer la couverture multi-cas dans success_criteria (ex. "≥ 4 types de tâche couverts") pour contrer les biais de sur-représentation

## Pièges évités
- Accepter la question littérale sans reformulation stratégique
- Sub-questions sans rationale (juste un sommaire déguisé)
- Sources génériques type "Google" ou "papers récents" sans expected_signal
- success_criteria vagues ("bonne synthèse", "couverture complète") au lieu de critères vérifiables
- Oublier la section risks_of_bias ou la traiter comme une formalité sans mitigation concrète
- Fausse dichotomie binaire (RAG vs FT, auto vs human) au lieu de patterns hybrides/composables

## Template d'exemple

```
question_reformulation: |
  La vraie question n'est pas "<question naïve>" mais "<question stratégique sous-jacente>".
  L'enjeu sous-jacent est <trade-off central chiffrable>.
sub_questions:
  - id: SQ1
    question: <question précise et scopée>
    rationale: <pourquoi cette SQ est nécessaire, quel angle mort elle couvre>
  - id: SQ2
    ...
sources_to_consult:
  - type: docs|papers|benchmarks|community|comparatifs|code
    target: <sources nommées concrètement>
    expected_signal: <ce qu'on espère y trouver précisément>
success_criteria:
  - <livrable vérifiable avec quantification>
risks_of_bias:
  - <biais nommé> — mitigation : <action concrète>
estimated_breadth: medium|deep
```

## Sources
- 20260510T151313_35a84f56_research_lead (score 0.91)
- 20260510T134803_30a357da_research_lead (score 0.88)
- 20260510T152021_e3b5ffdd_research_lead (score 0.88)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
title: Plan de recherche YAML structuré pour missions comparatives
agent: research_lead
tags:
  - research-planning
  - yaml-output
  - question-reformulation
  - bias-mitigation
  - sub-questions
summary: |
  Le research_lead produit un plan YAML structuré qui commence systématiquement par reformuler
  la "vraie question" sous-jacente (souvent différente de la question littérale), décompose en
  5-6 sub_questions avec rationale explicite, liste des sources typées variées, définit des
  success_criteria mesurables et nomme explicitement les biais à mitiger.
key_patterns:
  - "question_reformulation recadre la question naïve en problème stratégique sous-jacent (ex. 'pas X ou Y mais comment optimiser le ratio coût/qualité dans le temps')"
  - Chaque sub_question est accompagnée d'une rationale qui justifie pourquoi elle est nécessaire (pas juste un découpage thématique)
  - Sources typées et diversifiées (docs/papers/benchmarks/community/comparatifs/code) avec expected_signal précis pour chacune
  - success_criteria formulés comme livrables vérifiables avec quantifications ("≥ 4 types", "au moins 2 seuils chiffrés", "tableau avec colonnes X/Y/Z")
  - risks_of_bias nomme un biais concret + propose une mitigation actionnable (pas juste "attention au biais")
  - Une sub_question finale couvre souvent l'évaluation/méta-niveau (méta-évaluation, validation, itération en production)
techniques:
  - "Pattern de reformulation : 'La vraie question n'est pas X mais Y' suivi d'un enjeu sous-jacent chiffrable"
  - IDs stables pour les sub_questions (SQ1, SQ2...) pour permettre le cross-référencement aval
  - Distinction explicite des dimensions orthogonales (reference-based vs reference-free, online vs offline, style vs factualité) pour éviter les fausses dichotomies
  - Sources triangulées : croiser docs officielles (biaisées vendor) + papers académiques + retours terrain praticiens nommés (Willison, Husain, Yan, Huyen)
  - estimated_breadth déclaré (medium/deep) en fin de plan pour calibrer l'effort aval
  - Forcer la couverture multi-cas dans success_criteria (ex. "≥ 4 types de tâche couverts") pour contrer les biais de sur-représentation
pitfalls_avoided:
  - Accepter la question littérale sans reformulation stratégique
  - Sub-questions sans rationale (juste un sommaire déguisé)
  - Sources génériques type "Google" ou "papers récents" sans expected_signal
  - success_criteria vagues ("bonne synthèse", "couverture complète") au lieu de critères vérifiables
  - Oublier la section risks_of_bias ou la traiter comme une formalité sans mitigation concrète
  - Fausse dichotomie binaire (RAG vs FT, auto vs human) au lieu de patterns hybrides/composables
example_template: |
  question_reformulation: |
    La vraie question n'est pas "<question naïve>" mais "<question stratégique sous-jacente>".
    L'enjeu sous-jacent est <trade-off central chiffrable>.
  sub_questions:
    - id: SQ1
      question: <question précise et scopée>
      rationale: <pourquoi cette SQ est nécessaire, quel angle mort elle couvre>
    - id: SQ2
      ...
  sources_to_consult:
    - type: docs|papers|benchmarks|community|comparatifs|code
      target: <sources nommées concrètement>
      expected_signal: <ce qu'on espère y trouver précisément>
  success_criteria:
    - <livrable vérifiable avec quantification>
  risks_of_bias:
    - <biais nommé> — mitigation : <action concrète>
  estimated_breadth: medium|deep
sources_count: 3
```

</details>
