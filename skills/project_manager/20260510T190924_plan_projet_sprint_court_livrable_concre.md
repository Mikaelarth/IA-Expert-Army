---
summary: 'Pour un sprint court (1-2 semaines) avec livrable technique défini, structurer
  le plan en

  3 milestones séquentiels (squelette/setup → contenu/intégration → déploiement/tests)
  avec

  Definition of Done mesurable, checkpoints go/pivot/stop datés, et 1-3 décisions
  bloquantes

  à trancher dès J+1 pour débloquer l''exécution.'
tags:
- project-planning
- milestones
- risk-management
- sprint-court
- yaml-deliverable
sources:
- 20260510T184332_3f0fcbc1_project_manager
- 20260510T190319_ec8de23f_project_manager
sources_avg_score: 0.895
extracted_from: 2
skill_id: 20260510T190924_plan_projet_sprint_court_livrable_concre
agent: project_manager
title: Plan projet sprint court livrable concret
created_at: '2026-05-10T19:09:24.326594+00:00'
---

## Résumé

Pour un sprint court (1-2 semaines) avec livrable technique défini, structurer le plan en
3 milestones séquentiels (squelette/setup → contenu/intégration → déploiement/tests) avec
Definition of Done mesurable, checkpoints go/pivot/stop datés, et 1-3 décisions bloquantes
à trancher dès J+1 pour débloquer l'exécution.

## Patterns clés
- Final objective formulé en 2-4 lignes avec critère de succès mesurable et observable (URL HTTP 200, tool fonctionnel bout-en-bout)
- Scope explicite in/out où le 'out' désamorce les dérives prévisibles (versioning, auth, refactoring, traduction)
- 3 milestones suivant l'arc : (M1) squelette/setup minimal qui tourne → (M2) contenu réel + conformité → (M3) déploiement + tests bout-en-bout
- Chaque milestone a un deliverable concret + DoD en checklist vérifiable (commandes, fichiers, URLs)
- Checkpoints alignés sur fin de milestone avec triade continue/pivot/stop et critères opérationnels par branche
- Risques peu nombreux mais qualifiés (probability/impact/mitigation/early_warning), centrés sur les vrais blocants (RGPD, déploiement silencieux)
- Décisions de la semaine = bloquantes pour M1, owner + deadline J+1/J+2

## Techniques
- Estimer en jours-fourchette (1-2j, 2-3j) plutôt qu'en valeur unique, charge totale en heures explicitée
- DoD en bullets actionnables incluant au moins une commande shell vérifiable (`mkdocs serve`, `python -m ...`, `make test`)
- Pivot pré-câblé dans chaque checkpoint : alternative technique nommée (Jekyll vs MkDocs, HTTP vs stdio, Netlify vs GH Pages)
- Early_warning observable et précoce (ex : 'PR mergée en <30min sans trace de relecture')
- Coûts infra chiffrés à 0 € quand applicable, mais lister les sources (GitHub Pages gratuit, tokens API ~$5-10)
- Conformité/sécurité traitée comme milestone-bloquante, pas comme annexe (audit RGPD ou licence MIT intégré au DoD)

## Pièges évités
- Pas de milestone fourre-tout 'développement' : chaque M a un focus unique et un livrable distinct
- Pas de décision floue sans owner ni deadline (toujours owner + J+N)
- Pas de risque générique ('le projet peut prendre du retard') : risques spécifiques au domaine technique
- Pas d'oubli du critère bloquant amont (repo public requis, validateur RGPD identifié) — listé en D1
- Pas de DoD subjectif type 'ça marche' : toujours commande/URL/fichier vérifiable

## Template d'exemple

```
final_objective: |
  <1 phrase outcome + 1 phrase critère de succès mesurable>
scope:
  in: [<5-8 items précis>]
  out: [<4-6 dérives prévisibles désamorcées>]
milestones:
  - id: M1
    title: <Squelette/setup>
    deliverable: |
      <artefact concret>
    definition_of_done: |
      - <commande shell qui tourne>
      - <fichier commité>
    duration_estimate: "1-2 jours"
    depends_on: []
  # M2 = contenu réel + conformité ; M3 = tests bout-en-bout + déploiement
resources:
  roles: [{role: ..., etp: 0.X, charge_estimee: ...}]
  infra_or_budget: [<lignes chiffrées, 0 € si applicable>]
risks:
  - {id: R1, description, probability, impact, mitigation, early_warning}
checkpoints:
  - timing: "Fin M1 (J+N)"
    decision: continue | pivot | stop
    criteria: |
      CONTINUE si ... / PIVOT si ... → <alternative nommée> / STOP si ...
decisions_cette_semaine:
  - {id: D1, decision/question, owner, deadline: "J+1"}
```

## Sources
- 20260510T184332_3f0fcbc1_project_manager (score 0.91)
- 20260510T190319_ec8de23f_project_manager (score 0.88)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
title: Plan projet sprint court livrable concret
agent: project_manager
tags:
  - project-planning
  - milestones
  - risk-management
  - sprint-court
  - yaml-deliverable
summary: |
  Pour un sprint court (1-2 semaines) avec livrable technique défini, structurer le plan en
  3 milestones séquentiels (squelette/setup → contenu/intégration → déploiement/tests) avec
  Definition of Done mesurable, checkpoints go/pivot/stop datés, et 1-3 décisions bloquantes
  à trancher dès J+1 pour débloquer l'exécution.
key_patterns:
  - "Final objective formulé en 2-4 lignes avec critère de succès mesurable et observable (URL HTTP 200, tool fonctionnel bout-en-bout)"
  - "Scope explicite in/out où le 'out' désamorce les dérives prévisibles (versioning, auth, refactoring, traduction)"
  - "3 milestones suivant l'arc : (M1) squelette/setup minimal qui tourne → (M2) contenu réel + conformité → (M3) déploiement + tests bout-en-bout"
  - "Chaque milestone a un deliverable concret + DoD en checklist vérifiable (commandes, fichiers, URLs)"
  - "Checkpoints alignés sur fin de milestone avec triade continue/pivot/stop et critères opérationnels par branche"
  - "Risques peu nombreux mais qualifiés (probability/impact/mitigation/early_warning), centrés sur les vrais blocants (RGPD, déploiement silencieux)"
  - "Décisions de la semaine = bloquantes pour M1, owner + deadline J+1/J+2"
techniques:
  - "Estimer en jours-fourchette (1-2j, 2-3j) plutôt qu'en valeur unique, charge totale en heures explicitée"
  - "DoD en bullets actionnables incluant au moins une commande shell vérifiable (`mkdocs serve`, `python -m ...`, `make test`)"
  - "Pivot pré-câblé dans chaque checkpoint : alternative technique nommée (Jekyll vs MkDocs, HTTP vs stdio, Netlify vs GH Pages)"
  - "Early_warning observable et précoce (ex : 'PR mergée en <30min sans trace de relecture')"
  - "Coûts infra chiffrés à 0 € quand applicable, mais lister les sources (GitHub Pages gratuit, tokens API ~$5-10)"
  - "Conformité/sécurité traitée comme milestone-bloquante, pas comme annexe (audit RGPD ou licence MIT intégré au DoD)"
pitfalls_avoided:
  - "Pas de milestone fourre-tout 'développement' : chaque M a un focus unique et un livrable distinct"
  - "Pas de décision floue sans owner ni deadline (toujours owner + J+N)"
  - "Pas de risque générique ('le projet peut prendre du retard') : risques spécifiques au domaine technique"
  - "Pas d'oubli du critère bloquant amont (repo public requis, validateur RGPD identifié) — listé en D1"
  - "Pas de DoD subjectif type 'ça marche' : toujours commande/URL/fichier vérifiable"
example_template: |
  final_objective: |
    <1 phrase outcome + 1 phrase critère de succès mesurable>
  scope:
    in: [<5-8 items précis>]
    out: [<4-6 dérives prévisibles désamorcées>]
  milestones:
    - id: M1
      title: <Squelette/setup>
      deliverable: |
        <artefact concret>
      definition_of_done: |
        - <commande shell qui tourne>
        - <fichier commité>
      duration_estimate: "1-2 jours"
      depends_on: []
    # M2 = contenu réel + conformité ; M3 = tests bout-en-bout + déploiement
  resources:
    roles: [{role: ..., etp: 0.X, charge_estimee: ...}]
    infra_or_budget: [<lignes chiffrées, 0 € si applicable>]
  risks:
    - {id: R1, description, probability, impact, mitigation, early_warning}
  checkpoints:
    - timing: "Fin M1 (J+N)"
      decision: continue | pivot | stop
      criteria: |
        CONTINUE si ... / PIVOT si ... → <alternative nommée> / STOP si ...
  decisions_cette_semaine:
    - {id: D1, decision/question, owner, deadline: "J+1"}
sources_count: 2
```

</details>
