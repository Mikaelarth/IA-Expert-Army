---
summary: 'Recette pour produire une synthèse Markdown décisionnelle à partir de findings
  de recherche : ouverture par TL;DR opérationnel, sections numérotées alignées sur
  les sous-questions (SQ), tableaux comparatifs multi-axes, citations [SQ-finding-N]
  systématiques, section "Divergences & limites" honnête, et conclusion orientée action
  avec seuils chiffrés et prochaines questions.'
tags:
- synthesis
- markdown
- decision-guide
- technical-comparison
- sourced-findings
sources:
- 20260510T135007_30a357da_document_synthesizer
- 20260510T175622_1b88a119_document_synthesizer
sources_avg_score: 0.88
extracted_from: 2
skill_id: 20260510T175846_synth_se_d_cisionnelle_technique_structu
agent: document_synthesizer
title: Synthèse décisionnelle technique structurée par sections
created_at: '2026-05-10T17:58:46.980813+00:00'
---

## Résumé

Recette pour produire une synthèse Markdown décisionnelle à partir de findings de recherche : ouverture par TL;DR opérationnel, sections numérotées alignées sur les sous-questions (SQ), tableaux comparatifs multi-axes, citations [SQ-finding-N] systématiques, section "Divergences & limites" honnête, et conclusion orientée action avec seuils chiffrés et prochaines questions.

## Patterns clés
- TL;DR en tête qui donne directement la recommandation chiffrée et nuancée (pas un résumé descriptif, une réponse)
- Sections numérotées (Section 1, 2, ...) explicitement mappées sur les sous-questions de recherche (SQ1, SQ2...)
- Tableaux comparatifs multi-axes pour toute comparaison (≥3 options × ≥4 critères) plutôt que prose
- Citations inline systématiques au format [SQ-finding-N] après chaque affirmation factuelle
- Section "Divergences & limites" qui distingue gaps de données, divergences de sources, et ce qui n'a pas été couvert
- Conclusion en deux temps : "Que faire maintenant" (recommandations actionnables) + "Prochaines questions à creuser"
- Seuils quantifiés partout (coûts $, durées, volumes) plutôt que qualificatifs vagues
- Encadrés ⚠️ pour les pièges et signaux contre-intuitifs

## Techniques
- Phase/seuils/critères sous forme de tableaux décisionnels (réponse → recommandation)
- Anti-patterns documentés avec structure : Symptôme observable / Mécanisme / Sources / Correction
- "Test" en une phrase opérationnelle pour chaque critère de décision (ex. "Puis-je spécifier le flux comme une séquence linéaire ?")
- Distinction explicite entre confidence levels (high/medium/low) pour les findings incertains
- Liste finale "Sources consultées" exhaustive et catégorisée (papers, docs, GitHub, communautés)
- Marqueurs de niveau de preuve : "estimation anecdotique", "non vérifiable directement", "low confidence"

## Pièges évités
- Ne pas masquer les limites : les bons épisodes documentent explicitement les gaps et biais commerciaux des sources
- Ne pas se contenter d'un scalaire qualité/coût : décomposer en axes orthogonaux (fraîcheur, cohérence, latence, etc.)
- Ne pas conclure par un avis tranché unique : proposer des phases/paliers avec seuils de bascule
- Éviter la prose continue pour les comparaisons — toujours basculer en tableau dès qu'il y a ≥3 dimensions
- Ne pas inventer de chiffres précis sans citation ; préférer fourchettes (ex. "$50–200/mois") aux valeurs ponctuelles

## Template d'exemple

```
# <Titre> — <angle décisionnel/temporel>
```

## Sources
- 20260510T135007_30a357da_document_synthesizer (score 0.88)
- 20260510T175622_1b88a119_document_synthesizer (score 0.88)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
title: Synthèse décisionnelle technique structurée par sections
agent: document_synthesizer
tags:
  - synthesis
  - markdown
  - decision-guide
  - technical-comparison
  - sourced-findings
summary: |
  Recette pour produire une synthèse Markdown décisionnelle à partir de findings de recherche : ouverture par TL;DR opérationnel, sections numérotées alignées sur les sous-questions (SQ), tableaux comparatifs multi-axes, citations [SQ-finding-N] systématiques, section "Divergences & limites" honnête, et conclusion orientée action avec seuils chiffrés et prochaines questions.
key_patterns:
  - TL;DR en tête qui donne directement la recommandation chiffrée et nuancée (pas un résumé descriptif, une réponse)
  - Sections numérotées (Section 1, 2, ...) explicitement mappées sur les sous-questions de recherche (SQ1, SQ2...)
  - Tableaux comparatifs multi-axes pour toute comparaison (≥3 options × ≥4 critères) plutôt que prose
  - Citations inline systématiques au format [SQ-finding-N] après chaque affirmation factuelle
  - Section "Divergences & limites" qui distingue gaps de données, divergences de sources, et ce qui n'a pas été couvert
  - Conclusion en deux temps : "Que faire maintenant" (recommandations actionnables) + "Prochaines questions à creuser"
  - Seuils quantifiés partout (coûts $, durées, volumes) plutôt que qualificatifs vagues
  - Encadrés ⚠️ pour les pièges et signaux contre-intuitifs
techniques:
  - Phase/seuils/critères sous forme de tableaux décisionnels (réponse → recommandation)
  - Anti-patterns documentés avec structure : Symptôme observable / Mécanisme / Sources / Correction
  - "Test" en une phrase opérationnelle pour chaque critère de décision (ex. "Puis-je spécifier le flux comme une séquence linéaire ?")
  - Distinction explicite entre confidence levels (high/medium/low) pour les findings incertains
  - Liste finale "Sources consultées" exhaustive et catégorisée (papers, docs, GitHub, communautés)
  - Marqueurs de niveau de preuve : "estimation anecdotique", "non vérifiable directement", "low confidence"
pitfalls_avoided:
  - Ne pas masquer les limites : les bons épisodes documentent explicitement les gaps et biais commerciaux des sources
  - Ne pas se contenter d'un scalaire qualité/coût : décomposer en axes orthogonaux (fraîcheur, cohérence, latence, etc.)
  - Ne pas conclure par un avis tranché unique : proposer des phases/paliers avec seuils de bascule
  - Éviter la prose continue pour les comparaisons — toujours basculer en tableau dès qu'il y a ≥3 dimensions
  - Ne pas inventer de chiffres précis sans citation ; préférer fourchettes (ex. "$50–200/mois") aux valeurs ponctuelles
example_template: |
  # <Titre> — <angle décisionnel/temporel>

  ## TL;DR
  <2-4 phrases : recommandation chiffrée + nuance + condition de bascule>

  ---

  ## Section 1 — <thème SQ1>
  ### <sous-thème>
  | Critère | Option A | Option B |
  |---|---|---|
  | ... | ... | ... |
  [SQ1-finding-N]

  > ⚠️ <piège ou signal contre-intuitif>

  ## Section N — <critères/anti-patterns>
  ...

  ## Divergences & limites
  - **Gaps** : ...
  - **Divergences entre sources** : ...
  - **Non couvert** : ...

  ## Conclusion / Pour aller plus loin
  ### Que faire maintenant
  1. <action avec seuil>
  ### Prochaines questions à creuser
  - ...

  ## Sources consultées
  - <catégorie> : ...
sources_count: 2
```

</details>
