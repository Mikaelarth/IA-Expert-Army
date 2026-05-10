---
summary: 'Recette d''analyse business pour projets internes/OSS où la valeur n''est
  pas un revenu direct

  mais une option stratégique (crédibilité, réutilisabilité, intégrations futures).
  Quantifie

  systématiquement coût v1 vs coût évité futur, identifie le seuil de break-even concret,

  et émet un verdict go/pivot conditionnel à 1-3 actions précises.'
tags:
- business-analysis
- viability
- roi
- option-value
- go-no-go
sources:
- 20260510T184441_3f0fcbc1_business_analyst
- 20260510T190429_ec8de23f_business_analyst
- 20260510T190654_ec8de23f_business_analyst
sources_avg_score: 0.89
extracted_from: 3
skill_id: 20260510T190949_analyse_business_avec_valeur_d_option_et
agent: business_analyst
title: Analyse business avec valeur d'option et break-even
created_at: '2026-05-10T19:09:49.332270+00:00'
---

## Résumé

Recette d'analyse business pour projets internes/OSS où la valeur n'est pas un revenu direct
mais une option stratégique (crédibilité, réutilisabilité, intégrations futures). Quantifie
systématiquement coût v1 vs coût évité futur, identifie le seuil de break-even concret,
et émet un verdict go/pivot conditionnel à 1-3 actions précises.

## Patterns clés
- Reformule explicitement le TAM quand non-applicable ("pas un produit commercial, métrique pertinente = X") plutôt que forcer un chiffre €
- Quantifie le coût v1 en j-h × TJM avec fourchettes basse/haute, et compare au coût évité par réutilisation future
- Identifie un seuil de break-even concret et atteignable (ex. "dès la 1ère intégration tierce économisant > N j-h")
- Verdict toujours conditionnel à 1-3 actions nommées, avec scénario de pivot/no-go explicite
- Sensibilités classées par criticité, avec une variable dominante identifiée comme "plus critique que le sprint technique lui-même"
- Intégration des contraintes externes (Legal, sécurité, RGPD) comme prérequis de milestone, pas comme TODO post-livraison

## Techniques
- {'Schéma YAML stable': 'market_assessment / unique_value_proposition / unit_economics / kpis / business_risks / verdict / rationale'}
- KPIs avec triplet success_threshold + alert_threshold + measurement (mesurable, outil cité)
- Risques avec triplet likelihood/impact/mitigation, mitigation actionnable et chiffrée
- Cas A/Cas B pour scénarios de coût conditionnels (ex. PII vs non-PII)
- Référence aux précédents épisodes ("cf. Précédent 2") pour ancrer les hypothèses de marché
- Hypothèses chiffrées explicites (TJM, taux conversion, CAGR) avec source ou fourchette assumée

## Pièges évités
- Ne pas inventer un TAM en € quand le projet est interne/OSS — reformuler la métrique
- {'Ne pas conclure "go" sans condition': 'toujours nommer 1-3 prérequis non négociables'}
- Ne pas ignorer le coût d'opportunité même quand le coût absolu est faible
- Ne pas confondre valeur d'option (potentielle) et valeur réalisée (matérialisée par cas d'usage concrets)
- Ne pas oublier le risque "ship and forget" / "investissement orphelin" quand pas d'utilisateur identifié

## Template d'exemple

```
market_assessment:
  total_addressable_market: |
    <reformulation si non-commercial : audience, valeur d'option, ...>
  segments:
    - name: <segment>
      pain: <douleur>
      willingness_to_pay: low|medium|high
unit_economics:
  cost_per_unit: |
    <X j-h × Y €/j = Z €, hypothèses explicites>
  revenue_per_unit: |
    <revenu direct OU coût évité par réutilisation>
  break_even: |
    <seuil concret : "dès N intégrations" ou "1 lead consulting">
  sensitivities:
    - variable: <variable critique>
      impact_if_doubles: <chiffré>
kpis:
  - name: <KPI>
    success_threshold: <seuil>
    alert_threshold: <seuil>
    measurement: <outil/méthode>
business_risks:
  - description: <risque>
    likelihood: low|medium|high
    impact: low|medium|high
    mitigation: <action chiffrée>
verdict: go|pivot|no-go
rationale: |
  <synthèse + conditions explicites + scénario de bascule>
```

## Sources
- 20260510T184441_3f0fcbc1_business_analyst (score 0.91)
- 20260510T190429_ec8de23f_business_analyst (score 0.88)
- 20260510T190654_ec8de23f_business_analyst (score 0.88)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
title: Analyse business avec valeur d'option et break-even
agent: business_analyst
tags:
  - business-analysis
  - viability
  - roi
  - option-value
  - go-no-go
summary: |
  Recette d'analyse business pour projets internes/OSS où la valeur n'est pas un revenu direct
  mais une option stratégique (crédibilité, réutilisabilité, intégrations futures). Quantifie
  systématiquement coût v1 vs coût évité futur, identifie le seuil de break-even concret,
  et émet un verdict go/pivot conditionnel à 1-3 actions précises.
key_patterns:
  - Reformule explicitement le TAM quand non-applicable ("pas un produit commercial, métrique pertinente = X") plutôt que forcer un chiffre €
  - Quantifie le coût v1 en j-h × TJM avec fourchettes basse/haute, et compare au coût évité par réutilisation future
  - Identifie un seuil de break-even concret et atteignable (ex. "dès la 1ère intégration tierce économisant > N j-h")
  - Verdict toujours conditionnel à 1-3 actions nommées, avec scénario de pivot/no-go explicite
  - Sensibilités classées par criticité, avec une variable dominante identifiée comme "plus critique que le sprint technique lui-même"
  - Intégration des contraintes externes (Legal, sécurité, RGPD) comme prérequis de milestone, pas comme TODO post-livraison
techniques:
  - Schéma YAML stable : market_assessment / unique_value_proposition / unit_economics / kpis / business_risks / verdict / rationale
  - KPIs avec triplet success_threshold + alert_threshold + measurement (mesurable, outil cité)
  - Risques avec triplet likelihood/impact/mitigation, mitigation actionnable et chiffrée
  - Cas A/Cas B pour scénarios de coût conditionnels (ex. PII vs non-PII)
  - Référence aux précédents épisodes ("cf. Précédent 2") pour ancrer les hypothèses de marché
  - Hypothèses chiffrées explicites (TJM, taux conversion, CAGR) avec source ou fourchette assumée
pitfalls_avoided:
  - Ne pas inventer un TAM en € quand le projet est interne/OSS — reformuler la métrique
  - Ne pas conclure "go" sans condition : toujours nommer 1-3 prérequis non négociables
  - Ne pas ignorer le coût d'opportunité même quand le coût absolu est faible
  - Ne pas confondre valeur d'option (potentielle) et valeur réalisée (matérialisée par cas d'usage concrets)
  - Ne pas oublier le risque "ship and forget" / "investissement orphelin" quand pas d'utilisateur identifié
example_template: |
  market_assessment:
    total_addressable_market: |
      <reformulation si non-commercial : audience, valeur d'option, ...>
    segments:
      - name: <segment>
        pain: <douleur>
        willingness_to_pay: low|medium|high
  unit_economics:
    cost_per_unit: |
      <X j-h × Y €/j = Z €, hypothèses explicites>
    revenue_per_unit: |
      <revenu direct OU coût évité par réutilisation>
    break_even: |
      <seuil concret : "dès N intégrations" ou "1 lead consulting">
    sensitivities:
      - variable: <variable critique>
        impact_if_doubles: <chiffré>
  kpis:
    - name: <KPI>
      success_threshold: <seuil>
      alert_threshold: <seuil>
      measurement: <outil/méthode>
  business_risks:
    - description: <risque>
      likelihood: low|medium|high
      impact: low|medium|high
      mitigation: <action chiffrée>
  verdict: go|pivot|no-go
  rationale: |
    <synthèse + conditions explicites + scénario de bascule>
sources_count: 3
```

</details>
