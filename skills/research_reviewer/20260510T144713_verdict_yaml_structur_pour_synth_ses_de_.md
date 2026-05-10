---
summary: 'Le research_reviewer produit un verdict YAML structuré (verdict + quality_score
  + summary +

  strengths + issues catégorisées par severity + required_actions) qui évalue la couverture

  des success_criteria, la traçabilité du sourcing vers les findings, et la calibration

  épistémique. Chaque issue est localisée précisément et accompagnée d''une suggestion
  actionnable.'
tags:
- review
- synthese
- sourcing
- honnetete-epistemique
- verdict-yaml
sources:
- 20260510T135047_30a357da_research_reviewer
- 20260510T143904_5e1e3cc7_research_reviewer
- 20260510T144044_5e1e3cc7_research_reviewer
sources_avg_score: 0.873
extracted_from: 3
skill_id: 20260510T144713_verdict_yaml_structur_pour_synth_ses_de_
agent: research_reviewer
title: Verdict YAML structuré pour synthèses de recherche
created_at: '2026-05-10T14:47:13.065798+00:00'
---

## Résumé

Le research_reviewer produit un verdict YAML structuré (verdict + quality_score + summary +
strengths + issues catégorisées par severity + required_actions) qui évalue la couverture
des success_criteria, la traçabilité du sourcing vers les findings, et la calibration
épistémique. Chaque issue est localisée précisément et accompagnée d'une suggestion actionnable.

## Patterns clés
- Verdict binaire clair (APPROVED / NEEDS_CHANGES) couplé à un quality_score numérique entre 0 et 1, le seuil ~0.85 déclenchant l'approbation
- Issues hiérarchisées par severity (blocker / major / minor / nit) et catégorisées (sourcing, pertinence, exactitude, epistemic_honesty, concision, structure)
- Chaque issue contient location précise (section + citation), message explicatif (le pourquoi du problème), suggestion concrète (la correction à apporter)
- Vérification systématique de la couverture des success_criteria explicitement listés dans la mission (livrables tronqués = blocker)
- Traçabilité finding ↔ affirmation : chaque chiffre ou claim doit être sourcé [SQx-finding-y], les chiffres non sourcés sont flaggués
- Calibration épistémique : signaler quand une confiance medium d'un finding n'est pas répercutée dans la synthèse, quand un sourcing vendor est présenté avec autorité indépendante
- Distinction strengths / issues équilibrée : reconnaître ce qui marche avant de pointer les défauts

## Techniques
- Cross-référencer chaque affirmation chiffrée de la synthèse avec le finding source pour détecter chiffres extrapolés ou inventés
- Détecter les sources vendor (docs Anthropic, LangSmith) présentées comme post-mortems indépendants
- Identifier les statistiques à fausse précision (ex. '60-70%') issues d'enquêtes biaisées non signalées
- Vérifier que les TL;DR sont cohérents avec le corps (pas de promesse non tenue)
- Proposer des reformulations exactes en bloc citation, pas seulement décrire le problème
- Distinguer required_actions (à corriger absolument) des issues minor/nit (signalées mais non bloquantes)

## Pièges évités
- Ne pas approuver une synthèse tronquée même si le contenu présent est de qualité (livrables manquants = blocker)
- Ne pas se contenter de pointer un problème sans fournir une suggestion de correction concrète
- Ne pas confondre sévérité technique et sévérité contractuelle (un livrable manquant des success_criteria > une approximation de chiffre)
- Ne pas être complaisant : signaler les nits même quand le verdict est APPROVED, pour l'amélioration continue
- Ne pas accepter un sourcing apparent sans vérifier que le finding cité supporte réellement l'affirmation

## Template d'exemple

```
verdict: APPROVED | NEEDS_CHANGES
quality_score: 0.XX
summary: |
  <2-4 phrases : couverture des livrables, qualité du sourcing, calibration épistémique,
   défauts résiduels>
strengths:
  - "<point fort observable, avec section/élément précis>"
issues:
  - severity: blocker | major | minor | nit
    category: sourcing | pertinence | exactitude | epistemic_honesty | concision | structure
    location: "<section + citation exacte>"
    message: |
      <pourquoi c'est un problème, traçabilité vers finding ou success_criteria>
    suggestion: |
      <reformulation ou action concrète>
required_actions:
  - "<action prioritaire, préfixée par BLOCKER/MAJOR si applicable>"
```

## Sources
- 20260510T135047_30a357da_research_reviewer (score 0.88)
- 20260510T143904_5e1e3cc7_research_reviewer (score 0.87)
- 20260510T144044_5e1e3cc7_research_reviewer (score 0.87)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
title: Verdict YAML structuré pour synthèses de recherche
agent: research_reviewer
tags:
  - review
  - synthese
  - sourcing
  - honnetete-epistemique
  - verdict-yaml
summary: |
  Le research_reviewer produit un verdict YAML structuré (verdict + quality_score + summary +
  strengths + issues catégorisées par severity + required_actions) qui évalue la couverture
  des success_criteria, la traçabilité du sourcing vers les findings, et la calibration
  épistémique. Chaque issue est localisée précisément et accompagnée d'une suggestion actionnable.
key_patterns:
  - "Verdict binaire clair (APPROVED / NEEDS_CHANGES) couplé à un quality_score numérique entre 0 et 1, le seuil ~0.85 déclenchant l'approbation"
  - "Issues hiérarchisées par severity (blocker / major / minor / nit) et catégorisées (sourcing, pertinence, exactitude, epistemic_honesty, concision, structure)"
  - "Chaque issue contient location précise (section + citation), message explicatif (le pourquoi du problème), suggestion concrète (la correction à apporter)"
  - "Vérification systématique de la couverture des success_criteria explicitement listés dans la mission (livrables tronqués = blocker)"
  - "Traçabilité finding ↔ affirmation : chaque chiffre ou claim doit être sourcé [SQx-finding-y], les chiffres non sourcés sont flaggués"
  - "Calibration épistémique : signaler quand une confiance medium d'un finding n'est pas répercutée dans la synthèse, quand un sourcing vendor est présenté avec autorité indépendante"
  - "Distinction strengths / issues équilibrée : reconnaître ce qui marche avant de pointer les défauts"
techniques:
  - "Cross-référencer chaque affirmation chiffrée de la synthèse avec le finding source pour détecter chiffres extrapolés ou inventés"
  - "Détecter les sources vendor (docs Anthropic, LangSmith) présentées comme post-mortems indépendants"
  - "Identifier les statistiques à fausse précision (ex. '60-70%') issues d'enquêtes biaisées non signalées"
  - "Vérifier que les TL;DR sont cohérents avec le corps (pas de promesse non tenue)"
  - "Proposer des reformulations exactes en bloc citation, pas seulement décrire le problème"
  - "Distinguer required_actions (à corriger absolument) des issues minor/nit (signalées mais non bloquantes)"
pitfalls_avoided:
  - "Ne pas approuver une synthèse tronquée même si le contenu présent est de qualité (livrables manquants = blocker)"
  - "Ne pas se contenter de pointer un problème sans fournir une suggestion de correction concrète"
  - "Ne pas confondre sévérité technique et sévérité contractuelle (un livrable manquant des success_criteria > une approximation de chiffre)"
  - "Ne pas être complaisant : signaler les nits même quand le verdict est APPROVED, pour l'amélioration continue"
  - "Ne pas accepter un sourcing apparent sans vérifier que le finding cité supporte réellement l'affirmation"
example_template: |
  verdict: APPROVED | NEEDS_CHANGES
  quality_score: 0.XX
  summary: |
    <2-4 phrases : couverture des livrables, qualité du sourcing, calibration épistémique,
     défauts résiduels>
  strengths:
    - "<point fort observable, avec section/élément précis>"
  issues:
    - severity: blocker | major | minor | nit
      category: sourcing | pertinence | exactitude | epistemic_honesty | concision | structure
      location: "<section + citation exacte>"
      message: |
        <pourquoi c'est un problème, traçabilité vers finding ou success_criteria>
      suggestion: |
        <reformulation ou action concrète>
  required_actions:
    - "<action prioritaire, préfixée par BLOCKER/MAJOR si applicable>"
sources_count: 3
```

</details>
