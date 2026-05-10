---
summary: 'Le legal_reviewer produit un verdict YAML structuré (APPROVED / NEEDS_CHANGES)

  avec score, summary, strengths, issues triées par severity (blocker/major/minor/nit)

  et categories (data/suppliers/ip/ai_transparency/terms), chaque issue citant une

  location précise dans les artefacts amont, une suggestion actionnable et une

  legal_basis (article RGPD/AI Act/ToS). Les majors deviennent des required_actions

  datées (avant M1/M2) et le reviewer signale systématiquement que sa pré-revue ne

  remplace pas un avis juridique homologué.'
tags:
- rgpd
- ai-act
- conformite
- verdict-yaml
- severity-triage
sources:
- 20260510T184525_3f0fcbc1_legal_reviewer
- 20260510T190545_ec8de23f_legal_reviewer
- 20260510T190739_ec8de23f_legal_reviewer
sources_avg_score: 0.89
extracted_from: 3
skill_id: 20260510T191018_verdict_yaml_structur_pour_conformit_rgp
agent: legal_reviewer
title: Verdict YAML structuré pour conformité RGPD/AI Act
created_at: '2026-05-10T19:10:18.613063+00:00'
---

## Résumé

Le legal_reviewer produit un verdict YAML structuré (APPROVED / NEEDS_CHANGES)
avec score, summary, strengths, issues triées par severity (blocker/major/minor/nit)
et categories (data/suppliers/ip/ai_transparency/terms), chaque issue citant une
location précise dans les artefacts amont, une suggestion actionnable et une
legal_basis (article RGPD/AI Act/ToS). Les majors deviennent des required_actions
datées (avant M1/M2) et le reviewer signale systématiquement que sa pré-revue ne
remplace pas un avis juridique homologué.

## Patterns clés
- Calibrage du verdict sur la surface réglementaire réelle : projet doc statique sans PII → APPROVED rapide ; projet manipulant données + LLM tiers → NEEDS_CHANGES avec majors RGPD/ToS.
- Chaque issue cite une location précise (chemin YAML dans plan PM ou BA) plutôt qu'une critique générale, ce qui rend la remédiation traçable.
- Distinction systématique cas A (données non-PII, sortie propre par documentation) vs cas B (PII, base légale + DPA + DPO requis) pour forcer la qualification des données avant tout test LLM.
- Les required_actions sont datées par milestone (AVANT M1, AVANT M2) et reformulables en DoD/KPI par le PM.
- Mention récurrente du fallback 'données mock/synthétiques' comme sortie opérationnelle si la conformité n'est pas validée à temps.

## Techniques
- Grille severity 4 niveaux (blocker/major/minor/nit) + 5 categories (data, suppliers, ip, ai_transparency, terms) appliquée uniformément.
- Citer l'article précis : RGPD art. 6 (base légale), art. 28 (sous-traitant), art. 44-46 (transferts hors UE), art. 32 (sécurité), art. 83 (sanctions) ; AI Act art. 50 (transparence) ; directive 2016/943 (secret des affaires).
- Vérifier le DPA Anthropic et le tier de compte (Free/Pro/Team/Enterprise) pour qualifier les garanties contractuelles applicables.
- Pour les serveurs locaux sans auth : recommander une guard de code refusant le bind non-loopback sans variable d'environnement explicite.
- Chiffrer le coût d'une consultation avocat (€300-600) face au risque d'amende (4% CA / €20M) pour rendre la recommandation actionnable côté décideur.
- Audit licences via pip-licenses/liccheck ; détection PII via Presidio OSS sur échantillon.

## Pièges évités
- Ne pas confondre 'documentation publiée d'une architecture IA' (hors AI Act art. 50) avec 'IA exposée à des utilisateurs finaux' (dans le champ).
- Ne pas accepter qu'un 'responsable projet' signe seul une checklist RGPD à la place du DPO quand des PII sont en jeu.
- Ne pas reporter la lecture des ToS du fournisseur LLM en fin de projet (M3) — la déplacer Jour 1 pour éviter un blocage tardif.
- Ne pas se contenter d'un grep sur noms de champs pour détecter des PII : le contenu libre (champ 'content') peut contenir des données personnelles indépendamment du nom du champ.
- Ne pas affirmer un verdict sans rappeler que la pré-revue ne remplace pas un conseil juridique homologué.

## Template d'exemple

```
verdict: APPROVED | NEEDS_CHANGES
quality_score: 0.XX
summary: |
  <2-4 phrases : posture globale, blockers/majors résiduels, condition d'approbation>
strengths:
  - "<point fort observable cité avec sa location>"
issues:
  - severity: major
    category: data
    location: "<chemin YAML précis dans plan PM ou BA>"
    message: |
      <constat factuel + référence légale implicite>
    suggestion: |
      <action concrète, datée par milestone, avec coût estimé si pertinent>
    legal_basis: |
      <RGPD art. X / AI Act art. Y / ToS fournisseur + lien>
required_actions:
  - "[AVANT M1 — BLOQUANT] <action>"
  - "[NOTE] Cette pré-revue ne se substitue pas à un avis juridique homologué."
```

## Sources
- 20260510T184525_3f0fcbc1_legal_reviewer (score 0.91)
- 20260510T190545_ec8de23f_legal_reviewer (score 0.88)
- 20260510T190739_ec8de23f_legal_reviewer (score 0.88)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
title: Verdict YAML structuré pour conformité RGPD/AI Act
agent: legal_reviewer
tags:
  - rgpd
  - ai-act
  - conformite
  - verdict-yaml
  - severity-triage
summary: |
  Le legal_reviewer produit un verdict YAML structuré (APPROVED / NEEDS_CHANGES)
  avec score, summary, strengths, issues triées par severity (blocker/major/minor/nit)
  et categories (data/suppliers/ip/ai_transparency/terms), chaque issue citant une
  location précise dans les artefacts amont, une suggestion actionnable et une
  legal_basis (article RGPD/AI Act/ToS). Les majors deviennent des required_actions
  datées (avant M1/M2) et le reviewer signale systématiquement que sa pré-revue ne
  remplace pas un avis juridique homologué.
key_patterns:
  - "Calibrage du verdict sur la surface réglementaire réelle : projet doc statique sans PII → APPROVED rapide ; projet manipulant données + LLM tiers → NEEDS_CHANGES avec majors RGPD/ToS."
  - "Chaque issue cite une location précise (chemin YAML dans plan PM ou BA) plutôt qu'une critique générale, ce qui rend la remédiation traçable."
  - "Distinction systématique cas A (données non-PII, sortie propre par documentation) vs cas B (PII, base légale + DPA + DPO requis) pour forcer la qualification des données avant tout test LLM."
  - "Les required_actions sont datées par milestone (AVANT M1, AVANT M2) et reformulables en DoD/KPI par le PM."
  - "Mention récurrente du fallback 'données mock/synthétiques' comme sortie opérationnelle si la conformité n'est pas validée à temps."
techniques:
  - "Grille severity 4 niveaux (blocker/major/minor/nit) + 5 categories (data, suppliers, ip, ai_transparency, terms) appliquée uniformément."
  - "Citer l'article précis : RGPD art. 6 (base légale), art. 28 (sous-traitant), art. 44-46 (transferts hors UE), art. 32 (sécurité), art. 83 (sanctions) ; AI Act art. 50 (transparence) ; directive 2016/943 (secret des affaires)."
  - "Vérifier le DPA Anthropic et le tier de compte (Free/Pro/Team/Enterprise) pour qualifier les garanties contractuelles applicables."
  - "Pour les serveurs locaux sans auth : recommander une guard de code refusant le bind non-loopback sans variable d'environnement explicite."
  - "Chiffrer le coût d'une consultation avocat (€300-600) face au risque d'amende (4% CA / €20M) pour rendre la recommandation actionnable côté décideur."
  - "Audit licences via pip-licenses/liccheck ; détection PII via Presidio OSS sur échantillon."
pitfalls_avoided:
  - "Ne pas confondre 'documentation publiée d'une architecture IA' (hors AI Act art. 50) avec 'IA exposée à des utilisateurs finaux' (dans le champ)."
  - "Ne pas accepter qu'un 'responsable projet' signe seul une checklist RGPD à la place du DPO quand des PII sont en jeu."
  - "Ne pas reporter la lecture des ToS du fournisseur LLM en fin de projet (M3) — la déplacer Jour 1 pour éviter un blocage tardif."
  - "Ne pas se contenter d'un grep sur noms de champs pour détecter des PII : le contenu libre (champ 'content') peut contenir des données personnelles indépendamment du nom du champ."
  - "Ne pas affirmer un verdict sans rappeler que la pré-revue ne remplace pas un conseil juridique homologué."
example_template: |
  verdict: APPROVED | NEEDS_CHANGES
  quality_score: 0.XX
  summary: |
    <2-4 phrases : posture globale, blockers/majors résiduels, condition d'approbation>
  strengths:
    - "<point fort observable cité avec sa location>"
  issues:
    - severity: major
      category: data
      location: "<chemin YAML précis dans plan PM ou BA>"
      message: |
        <constat factuel + référence légale implicite>
      suggestion: |
        <action concrète, datée par milestone, avec coût estimé si pertinent>
      legal_basis: |
        <RGPD art. X / AI Act art. Y / ToS fournisseur + lien>
  required_actions:
    - "[AVANT M1 — BLOQUANT] <action>"
    - "[NOTE] Cette pré-revue ne se substitue pas à un avis juridique homologué."
sources_count: 3
```

</details>
