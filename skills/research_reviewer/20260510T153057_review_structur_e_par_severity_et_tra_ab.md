---
summary: 'Le research_reviewer évalue une synthèse en produisant un verdict YAML structuré
  qui combine

  un score quantitatif, un résumé calibré, des forces sourcées, et des issues classées
  par

  severity (blocker/major/minor/nit) × catégorie (pertinence, exactitude, sourcing,
  epistemic_honesty,

  structure, concision). Chaque issue cite une location précise, explique le mécanisme
  du problème,

  et propose une suggestion actionnable. Les required_actions distinguent ce qui bloque
  du polish.'
tags:
- review
- synthesis-quality
- epistemic-honesty
- sourcing
- structured-feedback
sources:
- 20260510T151650_35a84f56_research_reviewer
- 20260510T151849_35a84f56_research_reviewer
- 20260510T135047_30a357da_research_reviewer
sources_avg_score: 0.9
extracted_from: 3
skill_id: 20260510T153057_review_structur_e_par_severity_et_tra_ab
agent: research_reviewer
title: Review structurée par severity et traçabilité
created_at: '2026-05-10T15:30:57.744846+00:00'
---

## Résumé

Le research_reviewer évalue une synthèse en produisant un verdict YAML structuré qui combine
un score quantitatif, un résumé calibré, des forces sourcées, et des issues classées par
severity (blocker/major/minor/nit) × catégorie (pertinence, exactitude, sourcing, epistemic_honesty,
structure, concision). Chaque issue cite une location précise, explique le mécanisme du problème,
et propose une suggestion actionnable. Les required_actions distinguent ce qui bloque du polish.

## Patterns clés
- Verdict binaire clair (APPROVED / NEEDS_CHANGES) couplé à un quality_score numérique calibré (0.85-0.95)
- Chaque issue tag avec severity + category, plus une location ultra-précise (section, ligne, citation exacte)
- Le message d'issue explique le MÉCANISME causal du problème (pourquoi ça pose problème), pas juste le constat
- Chaque suggestion est actionnable et formulée comme un fix concret, pas une exhortation vague
- Vérification systématique de la traçabilité finding → synthèse (chaque affirmation chiffrée doit citer son SQx-finding-y)
- Détection des fusions/imprécisions techniques (ex: deux concepts distincts mergés en un)
- Détection des promesses non tenues entre TL;DR et corps du document
- Validation de la calibration épistémique (confidence high/medium/low respecté ; ne pas présenter du medium comme du high)

## Techniques
- Cross-checker chaque chiffre/citation de la synthèse contre les findings sources, signaler les attributions ambiguës
- Vérifier que tous les success_criteria explicites du plan sont livrés (livrables manquants = blocker automatique)
- Distinguer constat sourcé vs inférence normative ajoutée par la synthèse (les inferences doivent être marquées)
- Repérer les jugements de valeur non sourcés présentés comme des faits ('le plus négligé', 'convergeront')
- Lister forces ET issues : un review approbatif reste critique ; un review NEEDS_CHANGES reconnaît la qualité
- Final summary qui dit explicitement ce qui bloque vs ce qui est polish, pour orienter le prochain cycle

## Pièges évités
- Ne pas se contenter d'un score global sans décomposition par dimension
- Ne pas mélanger severity (un nit présenté comme major fait perdre du temps ; un blocker noyé dans des minors passe inaperçu)
- Ne pas proposer de suggestions vagues ('améliorer la clarté') — toujours un fix concret
- Ne pas approuver une synthèse tronquée ou incomplète sur les success_criteria, même si la partie livrée est excellente
- Ne pas être dur sans reconnaître les forces : strengths sourcées montrent que la review est calibrée, pas hostile

## Template d'exemple

```
verdict: APPROVED | NEEDS_CHANGES
quality_score: 0.XX
summary: |
  <2-4 phrases : qualité globale, ce qui marche, ce qui bloque ou pas>
strengths:
  - "<Force 1 sourcée vers section précise + finding source>"
  - "<Force 2 ...>"
issues:
  - severity: blocker | major | minor | nit
    category: pertinence | exactitude | sourcing | epistemic_honesty | structure | concision
    location: "Section X — citation/ligne exacte"
    message: |
      <Constat + mécanisme causal du problème>
    suggestion: |
      <Fix concret et actionnable>
required_actions:
  - "[BLOCKER/MAJOR] <action prioritaire>"
  - "<ou : Aucune action bloquante. Polish en passe légère.>"
```

## Sources
- 20260510T151650_35a84f56_research_reviewer (score 0.91)
- 20260510T151849_35a84f56_research_reviewer (score 0.91)
- 20260510T135047_30a357da_research_reviewer (score 0.88)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
title: Review structurée par severity et traçabilité
agent: research_reviewer
tags:
  - review
  - synthesis-quality
  - epistemic-honesty
  - sourcing
  - structured-feedback
summary: |
  Le research_reviewer évalue une synthèse en produisant un verdict YAML structuré qui combine
  un score quantitatif, un résumé calibré, des forces sourcées, et des issues classées par
  severity (blocker/major/minor/nit) × catégorie (pertinence, exactitude, sourcing, epistemic_honesty,
  structure, concision). Chaque issue cite une location précise, explique le mécanisme du problème,
  et propose une suggestion actionnable. Les required_actions distinguent ce qui bloque du polish.
key_patterns:
  - "Verdict binaire clair (APPROVED / NEEDS_CHANGES) couplé à un quality_score numérique calibré (0.85-0.95)"
  - "Chaque issue tag avec severity + category, plus une location ultra-précise (section, ligne, citation exacte)"
  - "Le message d'issue explique le MÉCANISME causal du problème (pourquoi ça pose problème), pas juste le constat"
  - "Chaque suggestion est actionnable et formulée comme un fix concret, pas une exhortation vague"
  - "Vérification systématique de la traçabilité finding → synthèse (chaque affirmation chiffrée doit citer son SQx-finding-y)"
  - "Détection des fusions/imprécisions techniques (ex: deux concepts distincts mergés en un)"
  - "Détection des promesses non tenues entre TL;DR et corps du document"
  - "Validation de la calibration épistémique (confidence high/medium/low respecté ; ne pas présenter du medium comme du high)"
techniques:
  - "Cross-checker chaque chiffre/citation de la synthèse contre les findings sources, signaler les attributions ambiguës"
  - "Vérifier que tous les success_criteria explicites du plan sont livrés (livrables manquants = blocker automatique)"
  - "Distinguer constat sourcé vs inférence normative ajoutée par la synthèse (les inferences doivent être marquées)"
  - "Repérer les jugements de valeur non sourcés présentés comme des faits ('le plus négligé', 'convergeront')"
  - "Lister forces ET issues : un review approbatif reste critique ; un review NEEDS_CHANGES reconnaît la qualité"
  - "Final summary qui dit explicitement ce qui bloque vs ce qui est polish, pour orienter le prochain cycle"
pitfalls_avoided:
  - "Ne pas se contenter d'un score global sans décomposition par dimension"
  - "Ne pas mélanger severity (un nit présenté comme major fait perdre du temps ; un blocker noyé dans des minors passe inaperçu)"
  - "Ne pas proposer de suggestions vagues ('améliorer la clarté') — toujours un fix concret"
  - "Ne pas approuver une synthèse tronquée ou incomplète sur les success_criteria, même si la partie livrée est excellente"
  - "Ne pas être dur sans reconnaître les forces : strengths sourcées montrent que la review est calibrée, pas hostile"
example_template: |
  verdict: APPROVED | NEEDS_CHANGES
  quality_score: 0.XX
  summary: |
    <2-4 phrases : qualité globale, ce qui marche, ce qui bloque ou pas>
  strengths:
    - "<Force 1 sourcée vers section précise + finding source>"
    - "<Force 2 ...>"
  issues:
    - severity: blocker | major | minor | nit
      category: pertinence | exactitude | sourcing | epistemic_honesty | structure | concision
      location: "Section X — citation/ligne exacte"
      message: |
        <Constat + mécanisme causal du problème>
      suggestion: |
        <Fix concret et actionnable>
  required_actions:
    - "[BLOCKER/MAJOR] <action prioritaire>"
    - "<ou : Aucune action bloquante. Polish en passe légère.>"
sources_count: 3
```

</details>
