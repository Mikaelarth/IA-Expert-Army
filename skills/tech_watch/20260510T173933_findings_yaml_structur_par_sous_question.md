---
summary: 'Pour chaque sous-question du plan, produire 4-8 findings atomiques en YAML,
  chacun avec

  confidence (high/medium/low) + sources nommées. Compléter par emerging_themes, divergences

  et knowledge_gaps transversaux. Privilégier chiffres concrets, mécanismes causaux
  et

  trade-offs nommés plutôt que généralités.'
tags:
- research
- findings
- yaml
- confidence-calibration
- sub-questions
sources:
- 20260510T151433_35a84f56_tech_watch
- 20260510T134850_30a357da_tech_watch
- 20260510T152145_e3b5ffdd_tech_watch
sources_avg_score: 0.89
extracted_from: 3
skill_id: 20260510T173933_findings_yaml_structur_par_sous_question
agent: tech_watch
title: Findings YAML structuré par sous-question
created_at: '2026-05-10T17:39:33.407574+00:00'
---

## Résumé

Pour chaque sous-question du plan, produire 4-8 findings atomiques en YAML, chacun avec
confidence (high/medium/low) + sources nommées. Compléter par emerging_themes, divergences
et knowledge_gaps transversaux. Privilégier chiffres concrets, mécanismes causaux et
trade-offs nommés plutôt que généralités.

## Patterns clés
- Structure rigide : findings_by_subquestion → SQ1, SQ2... → liste de findings atomiques avec finding/confidence/sources
- Chaque finding contient un fait vérifiable + chiffres concrets (coûts $, latences ms, %, seuils) plutôt que des affirmations qualitatives
- Confidence calibrée explicitement : high pour docs officielles + papers peer-reviewed, medium pour pratique stabilisée mais peu d'évidence empirique, low pour tendances émergentes
- Sections transversales obligatoires en fin : emerging_themes (synthèse), divergences (tensions vendor vs réalité), knowledge_gaps (zones d'incertitude pour le synthesizer)
- Notes de processus hors-YAML qui exposent calibration de confiance, biais atténués, et recommandations pour le Document Synthesizer en aval
- Couverture systématique des success_criteria du plan : si le plan exige 4 types de tâche couverts, chaque type apparaît dans au moins un finding

## Techniques
- Citer 2-3 sources nommées par finding : doc officielle + paper + retour communauté (triangulation)
- Nommer les biais/pièges avec leur mécanisme causal : 'position bias = LLM préfère sorties longues, mitigation = normaliser longueur dans prompt'
- Quantifier les trade-offs : '$0.003-0.05/eval × 1M/mois = $3-50K' plutôt que 'coûteux à grande échelle'
- Distinguer explicitement les axes (reference-based vs reference-free, online vs offline, RAG vs free-form vs code vs agents)
- Inclure section 'divergences' qui confronte claims vendors aux retours terrain (ex: docs minimisent coûts, prod révèle 10x)
- Tagger les sources par type : docs officielles, papers arXiv avec auteurs+année, blogs praticiens nommés (Willison, Husain, Yan, Huyen)

## Pièges évités
- Pas de findings vagues type 'attention aux biais' sans mécanisme ni mitigation concrète
- Pas de sur-représentation vendors VC-backed : équilibrage explicite OSS (Langfuse, RAGAS) vs propriétaires (Braintrust)
- Pas de 'confidence: high' par défaut : graduation honnête, certains findings restent en medium/low avec raison
- Pas d'omission des knowledge_gaps : signaler activement ce qui manque (case studies, données long-terme, intégrations non-Python)
- Pas de réponse binaire aux fausses dichotomies (RAG vs FT, auto vs human) : exposer les patterns hybrides observés en prod
- Pas de citations bidons : si la connaissance vient du pre-training sans source vérifiable, descendre la confidence

## Template d'exemple

```
```yaml
findings_by_subquestion:
  SQ1:
    - finding: |
        <Affirmation factuelle 2-5 lignes avec chiffres concrets, noms d'outils/papers,
        mécanisme causal explicite. Ex: "RAGAS = framework OSS spécialisé RAG. Métriques :
        faithfulness (LLM-judge), answer_relevancy (embedding sim). Hypothèse : output =
        texte + chunks source. Pas applicable hors RAG.">
      confidence: high|medium|low
      sources:
        - "<Doc officielle / Paper Auteur et al. année / Blog praticien nommé>"
        - "<Source 2 pour triangulation>"
      reason_if_unknown: ""
    - finding: |
        <Finding 2 sur même SQ, angle différent>
      confidence: medium
      sources: [...]
  SQ2:
    - finding: |...

emerging_themes:
  - "<Thème transversal 1 : tension structurante observée à travers plusieurs SQ>"
  - "<Thème 2>"

divergences:
  - "<Claim vendor X vs réalité terrain Y, avec mécanisme>"

knowledge_gaps:
  - "<Zone d'incertitude 1 : ce qui manque pour trancher>"
```
```

## Sources
- 20260510T151433_35a84f56_tech_watch (score 0.91)
- 20260510T134850_30a357da_tech_watch (score 0.88)
- 20260510T152145_e3b5ffdd_tech_watch (score 0.88)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
title: Findings YAML structuré par sous-question
agent: tech_watch
tags:
  - research
  - findings
  - yaml
  - confidence-calibration
  - sub-questions
summary: |
  Pour chaque sous-question du plan, produire 4-8 findings atomiques en YAML, chacun avec
  confidence (high/medium/low) + sources nommées. Compléter par emerging_themes, divergences
  et knowledge_gaps transversaux. Privilégier chiffres concrets, mécanismes causaux et
  trade-offs nommés plutôt que généralités.
key_patterns:
  - "Structure rigide : findings_by_subquestion → SQ1, SQ2... → liste de findings atomiques avec finding/confidence/sources"
  - "Chaque finding contient un fait vérifiable + chiffres concrets (coûts $, latences ms, %, seuils) plutôt que des affirmations qualitatives"
  - "Confidence calibrée explicitement : high pour docs officielles + papers peer-reviewed, medium pour pratique stabilisée mais peu d'évidence empirique, low pour tendances émergentes"
  - "Sections transversales obligatoires en fin : emerging_themes (synthèse), divergences (tensions vendor vs réalité), knowledge_gaps (zones d'incertitude pour le synthesizer)"
  - "Notes de processus hors-YAML qui exposent calibration de confiance, biais atténués, et recommandations pour le Document Synthesizer en aval"
  - "Couverture systématique des success_criteria du plan : si le plan exige 4 types de tâche couverts, chaque type apparaît dans au moins un finding"
techniques:
  - "Citer 2-3 sources nommées par finding : doc officielle + paper + retour communauté (triangulation)"
  - "Nommer les biais/pièges avec leur mécanisme causal : 'position bias = LLM préfère sorties longues, mitigation = normaliser longueur dans prompt'"
  - "Quantifier les trade-offs : '$0.003-0.05/eval × 1M/mois = $3-50K' plutôt que 'coûteux à grande échelle'"
  - "Distinguer explicitement les axes (reference-based vs reference-free, online vs offline, RAG vs free-form vs code vs agents)"
  - "Inclure section 'divergences' qui confronte claims vendors aux retours terrain (ex: docs minimisent coûts, prod révèle 10x)"
  - "Tagger les sources par type : docs officielles, papers arXiv avec auteurs+année, blogs praticiens nommés (Willison, Husain, Yan, Huyen)"
pitfalls_avoided:
  - "Pas de findings vagues type 'attention aux biais' sans mécanisme ni mitigation concrète"
  - "Pas de sur-représentation vendors VC-backed : équilibrage explicite OSS (Langfuse, RAGAS) vs propriétaires (Braintrust)"
  - "Pas de 'confidence: high' par défaut : graduation honnête, certains findings restent en medium/low avec raison"
  - "Pas d'omission des knowledge_gaps : signaler activement ce qui manque (case studies, données long-terme, intégrations non-Python)"
  - "Pas de réponse binaire aux fausses dichotomies (RAG vs FT, auto vs human) : exposer les patterns hybrides observés en prod"
  - "Pas de citations bidons : si la connaissance vient du pre-training sans source vérifiable, descendre la confidence"
example_template: |
  ```yaml
  findings_by_subquestion:
    SQ1:
      - finding: |
          <Affirmation factuelle 2-5 lignes avec chiffres concrets, noms d'outils/papers,
          mécanisme causal explicite. Ex: "RAGAS = framework OSS spécialisé RAG. Métriques :
          faithfulness (LLM-judge), answer_relevancy (embedding sim). Hypothèse : output =
          texte + chunks source. Pas applicable hors RAG.">
        confidence: high|medium|low
        sources:
          - "<Doc officielle / Paper Auteur et al. année / Blog praticien nommé>"
          - "<Source 2 pour triangulation>"
        reason_if_unknown: ""
      - finding: |
          <Finding 2 sur même SQ, angle différent>
        confidence: medium
        sources: [...]
    SQ2:
      - finding: |...

  emerging_themes:
    - "<Thème transversal 1 : tension structurante observée à travers plusieurs SQ>"
    - "<Thème 2>"

  divergences:
    - "<Claim vendor X vs réalité terrain Y, avec mécanisme>"

  knowledge_gaps:
    - "<Zone d'incertitude 1 : ce qui manque pour trancher>"
  ```
sources_count: 3
```

</details>
