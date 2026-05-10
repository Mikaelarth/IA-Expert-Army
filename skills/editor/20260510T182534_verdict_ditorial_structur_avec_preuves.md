---
summary: 'L''editor produit un verdict YAML structuré (APPROVED + score 0.85-0.92)
  qui combine

  un résumé honnête du contrat tenu, des strengths cités avec preuves textuelles,
  et

  des issues triées par sévérité (major/minor/nit) avec location précise et suggestion

  réécrite. La force vient de la granularité : chaque issue pointe un fragment exact,

  pas une critique générale.'
tags:
- editorial-review
- quality-gate
- yaml-verdict
- copywriting
- severity-triage
sources:
- 20260510T181251_904151fb_editor
- 20260510T181929_109e7ce2_editor
- 20260510T182129_0447068e_editor
sources_avg_score: 0.887
extracted_from: 3
skill_id: 20260510T182534_verdict_ditorial_structur_avec_preuves
agent: editor
title: Verdict éditorial structuré avec preuves
created_at: '2026-05-10T18:25:34.052899+00:00'
---

## Résumé

L'editor produit un verdict YAML structuré (APPROVED + score 0.85-0.92) qui combine
un résumé honnête du contrat tenu, des strengths cités avec preuves textuelles, et
des issues triées par sévérité (major/minor/nit) avec location précise et suggestion
réécrite. La force vient de la granularité : chaque issue pointe un fragment exact,
pas une critique générale.

## Patterns clés
- Score 0.87-0.91 quand le brief est respecté mais qu'il reste des frictions de publication ou des micro-ajustements
- Summary en 3-4 phrases qui pose le verdict global avant de détailler, en distinguant défaut éditorial vs risque de publication
- Strengths formulés comme assertions citées (entre guillemets, avec exemples du texte) — jamais d'éloge abstrait
- Issues triées en major (blocker publication) / minor (format, clarity) / nit (économie de mots, polish)
- {'Chaque issue contient toujours': 'severity + category + location précise + message argumenté + suggestion réécrite prête à coller'}

## Techniques
- {'Catégoriser les issues avec un vocabulaire fixe': 'proofs, format, clarity, audience, anti_patterns, cta'}
- Localiser chaque issue par section + fragment cité (ex. "Section 'Démarrer' — phrase d'invitation avant le CTA")
- Distinguer explicitement "défaut éditorial" (compte dans le score) de "risque de publication" (signalé dans required_actions sans pénaliser)
- {'Fournir une suggestion réécrite littérale, pas une instruction vague ("remplacer par': '...")'}
- Confronter chaque pattern observé aux contraintes du brief (ton, structure, longueur, anti-patterns listés)
- Lister required_actions séparément pour les vrais blockers, vide si APPROVED net

## Pièges évités
- Pas de critique vague type "manque de punch" sans citation du fragment problématique
- {'Pas de sur-correction': 'les nits sont marqués comme tels et déclarés optionnels'}
- Pas de confusion entre défaut du texte et défaut hors-scope (URLs fictives, commandes illustratives) — ces derniers vont en required_actions
- {'Pas de score gonflé': 'un texte conforme au brief mais perfectible plafonne à 0.88-0.91, pas 0.95+'}
- Pas de suggestions qui contredisent le brief ou le ton voulu

## Template d'exemple

```
verdict: APPROVED
quality_score: 0.XX
summary: |
  <2-3 phrases : contrat tenu ou non, point principal, distinction défaut/risque>
strengths:
  - >
    <Pattern observé + citation textuelle + référence au brief>
  - >
    <Autre force avec preuve concrète>
issues:
  - severity: major|minor|nit
    category: proofs|format|clarity|audience|cta|anti_patterns
    location: "<section + fragment précis>"
    message: |
      <Argumentation : pourquoi c'est un problème, pour qui>
    suggestion: |
      <Réécriture littérale prête à coller>
required_actions:
  - <Action bloquante avant publication, ou liste vide>
```

## Sources
- 20260510T181251_904151fb_editor (score 0.91)
- 20260510T181929_109e7ce2_editor (score 0.88)
- 20260510T182129_0447068e_editor (score 0.87)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
title: Verdict éditorial structuré avec preuves
agent: editor
tags:
  - editorial-review
  - quality-gate
  - yaml-verdict
  - copywriting
  - severity-triage
summary: |
  L'editor produit un verdict YAML structuré (APPROVED + score 0.85-0.92) qui combine
  un résumé honnête du contrat tenu, des strengths cités avec preuves textuelles, et
  des issues triées par sévérité (major/minor/nit) avec location précise et suggestion
  réécrite. La force vient de la granularité : chaque issue pointe un fragment exact,
  pas une critique générale.
key_patterns:
  - Score 0.87-0.91 quand le brief est respecté mais qu'il reste des frictions de publication ou des micro-ajustements
  - Summary en 3-4 phrases qui pose le verdict global avant de détailler, en distinguant défaut éditorial vs risque de publication
  - Strengths formulés comme assertions citées (entre guillemets, avec exemples du texte) — jamais d'éloge abstrait
  - Issues triées en major (blocker publication) / minor (format, clarity) / nit (économie de mots, polish)
  - Chaque issue contient toujours : severity + category + location précise + message argumenté + suggestion réécrite prête à coller
techniques:
  - Catégoriser les issues avec un vocabulaire fixe : proofs, format, clarity, audience, anti_patterns, cta
  - Localiser chaque issue par section + fragment cité (ex. "Section 'Démarrer' — phrase d'invitation avant le CTA")
  - Distinguer explicitement "défaut éditorial" (compte dans le score) de "risque de publication" (signalé dans required_actions sans pénaliser)
  - Fournir une suggestion réécrite littérale, pas une instruction vague ("remplacer par : ...")
  - Confronter chaque pattern observé aux contraintes du brief (ton, structure, longueur, anti-patterns listés)
  - Lister required_actions séparément pour les vrais blockers, vide si APPROVED net
pitfalls_avoided:
  - Pas de critique vague type "manque de punch" sans citation du fragment problématique
  - Pas de sur-correction : les nits sont marqués comme tels et déclarés optionnels
  - Pas de confusion entre défaut du texte et défaut hors-scope (URLs fictives, commandes illustratives) — ces derniers vont en required_actions
  - Pas de score gonflé : un texte conforme au brief mais perfectible plafonne à 0.88-0.91, pas 0.95+
  - Pas de suggestions qui contredisent le brief ou le ton voulu
example_template: |
  verdict: APPROVED
  quality_score: 0.XX
  summary: |
    <2-3 phrases : contrat tenu ou non, point principal, distinction défaut/risque>
  strengths:
    - >
      <Pattern observé + citation textuelle + référence au brief>
    - >
      <Autre force avec preuve concrète>
  issues:
    - severity: major|minor|nit
      category: proofs|format|clarity|audience|cta|anti_patterns
      location: "<section + fragment précis>"
      message: |
        <Argumentation : pourquoi c'est un problème, pour qui>
      suggestion: |
        <Réécriture littérale prête à coller>
  required_actions:
    - <Action bloquante avant publication, ou liste vide>
sources_count: 3
```

</details>
