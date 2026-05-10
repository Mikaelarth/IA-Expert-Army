---
summary: 'Le research_lead efficace commence par reformuler la question pour exposer
  l''enjeu sous-jacent

  (souvent mal posé en binaire), décompose en 5-6 sous-questions orthogonales avec
  rationale explicite,

  puis liste des sources typées avec signal attendu concret. Il termine par des success_criteria

  vérifiables et anticipe les biais de sources.'
tags:
- research-planning
- question-decomposition
- source-strategy
- greenfield-decisions
- bias-mitigation
sources:
- 20260510T134803_30a357da_research_lead
- 20260510T143534_5e1e3cc7_research_lead
sources_avg_score: 0.875
extracted_from: 2
skill_id: 20260510T144648_plan_de_recherche_agentique_avec_reformu
agent: research_lead
title: Plan de recherche agentique avec reformulation critique
created_at: '2026-05-10T14:46:48.583906+00:00'
---

## Résumé

Le research_lead efficace commence par reformuler la question pour exposer l'enjeu sous-jacent
(souvent mal posé en binaire), décompose en 5-6 sous-questions orthogonales avec rationale explicite,
puis liste des sources typées avec signal attendu concret. Il termine par des success_criteria
vérifiables et anticipe les biais de sources.

## Patterns clés
- {'Reformulation qui recadre la question': 'déconstruit les fausses dichotomies ("X ou Y ?" → "comment optimiser le ratio sous-jacent ?") et nomme l\'enjeu réel'}
- Décomposition en 5-6 sub_questions avec id (SQ1-SQ6), chacune avec un rationale qui justifie pourquoi cette question est nécessaire et pas redondante
- Sources typées (papers, docs, community, benchmarks, comparatifs, code) avec target précis ET expected_signal explicite — pas juste "regarder X"
- Success_criteria mesurables et exigeants (chiffres concrets, distinctions claires, pas de "ça dépend")
- La sortie finale demandée par la mission (tableau, N décisions, seuils) est anticipée dans les critères de succès

## Techniques
- {'Format YAML strict avec sections fixes': 'question_reformulation, sub_questions, sources_to_consult, success_criteria, (risks_of_bias), estimated_breadth'}
- Chaque sub_question = id + question + rationale ; le rationale explicite POURQUOI cette découpe (évite redondance, isole un axe critique)
- {'Chaque source = type + target (sources nommées': "Anthropic, arXiv, Langfuse, GitHub repos >1k stars) + expected_signal (ce qu'on cherche concrètement)"}
- Distinguer dimensions qu'on croit unifiées (ex. "qualité" → style/format vs factualité vs raisonnement ; "framework" vs "pattern conceptuel")
- {'Mitigation explicite des biais': "surreprésentation d'un écosystème, biais récence, sources marketing déguisées, biais vendor"}

## Pièges évités
- Accepter la question telle quelle sans reformuler l'enjeu sous-jacent
- Sous-questions vagues ou qui se chevauchent, sans rationale
- Sources génériques ("chercher sur Google", "lire des papers") sans cible nommée ni signal attendu
- Critères de succès flous qui permettent une réponse "ça dépend" non actionnable
- Ignorer les biais structurels des sources (hype cycle, marketing, écosystème dominant)

## Template d'exemple

```
question_reformulation: |
  <recadre l'enjeu réel, démonte les fausses dichotomies, nomme l'objectif sous-jacent>
sub_questions:
  - id: SQ1
    question: <question précise et orthogonale>
    rationale: <pourquoi cette découpe, quel angle elle isole>
  - id: SQ2
    ...
sources_to_consult:
  - type: papers|docs|community|benchmarks|comparatifs|code
    target: <sources nommées et précises>
    expected_signal: <ce qu'on espère y trouver concrètement>
success_criteria:
  - <critère vérifiable, chiffré ou structurel>
  - <couvre explicitement les livrables demandés par la mission>
risks_of_bias:
  - <biais identifié> → mitigation : <action concrète>
estimated_breadth: shallow|standard|deep
```

## Sources
- 20260510T134803_30a357da_research_lead (score 0.88)
- 20260510T143534_5e1e3cc7_research_lead (score 0.87)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
title: Plan de recherche agentique avec reformulation critique
agent: research_lead
tags:
  - research-planning
  - question-decomposition
  - source-strategy
  - greenfield-decisions
  - bias-mitigation
summary: |
  Le research_lead efficace commence par reformuler la question pour exposer l'enjeu sous-jacent
  (souvent mal posé en binaire), décompose en 5-6 sous-questions orthogonales avec rationale explicite,
  puis liste des sources typées avec signal attendu concret. Il termine par des success_criteria
  vérifiables et anticipe les biais de sources.
key_patterns:
  - Reformulation qui recadre la question : déconstruit les fausses dichotomies ("X ou Y ?" → "comment optimiser le ratio sous-jacent ?") et nomme l'enjeu réel
  - Décomposition en 5-6 sub_questions avec id (SQ1-SQ6), chacune avec un rationale qui justifie pourquoi cette question est nécessaire et pas redondante
  - Sources typées (papers, docs, community, benchmarks, comparatifs, code) avec target précis ET expected_signal explicite — pas juste "regarder X"
  - Success_criteria mesurables et exigeants (chiffres concrets, distinctions claires, pas de "ça dépend")
  - La sortie finale demandée par la mission (tableau, N décisions, seuils) est anticipée dans les critères de succès
techniques:
  - Format YAML strict avec sections fixes : question_reformulation, sub_questions, sources_to_consult, success_criteria, (risks_of_bias), estimated_breadth
  - Chaque sub_question = id + question + rationale ; le rationale explicite POURQUOI cette découpe (évite redondance, isole un axe critique)
  - Chaque source = type + target (sources nommées : Anthropic, arXiv, Langfuse, GitHub repos >1k stars) + expected_signal (ce qu'on cherche concrètement)
  - Distinguer dimensions qu'on croit unifiées (ex. "qualité" → style/format vs factualité vs raisonnement ; "framework" vs "pattern conceptuel")
  - Mitigation explicite des biais : surreprésentation d'un écosystème, biais récence, sources marketing déguisées, biais vendor
pitfalls_avoided:
  - Accepter la question telle quelle sans reformuler l'enjeu sous-jacent
  - Sous-questions vagues ou qui se chevauchent, sans rationale
  - Sources génériques ("chercher sur Google", "lire des papers") sans cible nommée ni signal attendu
  - Critères de succès flous qui permettent une réponse "ça dépend" non actionnable
  - Ignorer les biais structurels des sources (hype cycle, marketing, écosystème dominant)
example_template: |
  question_reformulation: |
    <recadre l'enjeu réel, démonte les fausses dichotomies, nomme l'objectif sous-jacent>
  sub_questions:
    - id: SQ1
      question: <question précise et orthogonale>
      rationale: <pourquoi cette découpe, quel angle elle isole>
    - id: SQ2
      ...
  sources_to_consult:
    - type: papers|docs|community|benchmarks|comparatifs|code
      target: <sources nommées et précises>
      expected_signal: <ce qu'on espère y trouver concrètement>
  success_criteria:
    - <critère vérifiable, chiffré ou structurel>
    - <couvre explicitement les livrables demandés par la mission>
  risks_of_bias:
    - <biais identifié> → mitigation : <action concrète>
  estimated_breadth: shallow|standard|deep
sources_count: 2
```

</details>
