# ADR-029 — A/B testing des prompts (MVP, suggest-only)

**Statut :** Accepted
**Date :** 2026-05-22
**Sprint :** v0.9.0 A2
**Évolution de :** [ADR-007](007-prompt-ab-testing-strategy.md) (Proposed)

## Contexte

ADR-007 (mai 2026) proposait une architecture A/B testing en 4 couches avec
auto-génération de variantes et auto-promotion. Resté en `Proposed` car trop
ambitieux pour le contexte usage perso. Avec >50 missions accumulées
post-v0.7.0, le besoin pragmatique émerge : **comparer rigoureusement 2
versions d'un prompt sur du vrai trafic, sans risquer une régression
silencieuse.**

Le MVP v0.9.0 réduit l'ambition initiale à un cycle humain-in-the-loop :
- L'humain rédige une variante manuellement (pas d'auto-génération LLM).
- Le système répartit le trafic et mesure objectivement.
- L'humain décide de promouvoir (pas d'auto-promote).

L'auto-génération + auto-promote restent possibles en v2 si le MVP démontre
sa valeur.

## Décision

### Convention de nommage

Les variantes d'un prompt vivent dans le même dossier que le prompt canonique,
avec un suffixe `_vN.md` ou `_<label>.md` :

```
prompts/
  orchestrator/
    code_reviewer.md           ← variante canonique (toujours présente)
    code_reviewer_v2.md        ← variante A/B (nom libre, label arbitraire)
    code_reviewer_concise.md   ← autre variante (label descriptif autorisé)
```

Les variantes sont découvertes automatiquement par `PromptAB.discover_variants`
(pattern glob `<role>*.md` dans le dossier du prompt canonique).

### Sélection

Par défaut, le prompt canonique est utilisé (rétrocompat 100%). L'A/B est
**opt-in** par agent via `Settings.ab_testing_agents` (liste d'agent names).

Pour un agent en A/B :
- Sélection **déterministe** par `hash(mission_id) % n_variants` (mêmes
  variantes choisies si on rejoue une mission, important pour resume).
- **Cohérence intra-mission** : un même agent utilise la même variante à
  tous ses appels d'une mission (orchestrator → architect → developer →
  reviewer ; si le reviewer est en A/B, ses 2 appels — initial + repair —
  utilisent la même variante).
- Distribution : équiprobable sur N variantes. Si on veut un split 80/20,
  on duplique 4× la variante dominante (compromis acceptable au MVP).

### Tracking

Chaque mission qui utilise un agent en A/B écrit dans :
- `data/ab_tests/<role>/<variant>/<mission_id>.json` avec `mission_id`,
  `verdict`, `quality_score`, `cost`, `duration`.

Le store est local (pas de base de données), permet `git diff` sur les
décisions.

### Stats (suggest-only)

Service `PromptAB.compute_stats(role)` agrège par variante :
- `n_missions`, `n_approved`, `approval_rate`
- `avg_quality_score`, `avg_cost_usd`, `avg_duration_seconds`
- Test statistique simple : si `n >= 10` ET `Δ approval_rate >= 10pp`, on
  marque `is_significant=True`.

Service `PromptAB.recommend_winner(role)` retourne la variante qui domine
sur `approval_rate × avg_quality_score`, ou `None` si insuffisamment de
données.

**Pas d'auto-promote.** Le système propose, l'humain décide via :
- Page GUI `7_⚗️_A_B_Testing` qui affiche le tableau de stats.
- Bouton "✅ Promouvoir comme canonique" qui renomme la variante en
  `<role>.md` (et archive l'ancien sous `<role>_archived_YYYYMMDD.md`).

### Alternatives évaluées

| Option | Pourquoi rejetée |
|---|---|
| **Auto-promotion stricte** (selon ADR-007 initial) | Risque de régression silencieuse si métrique de sélection imparfaite. Humain-in-the-loop = filet de sécurité. |
| **A/B sur sub-prompts dans le même fichier** (`{{#if variant}}...{{/if}}`) | Couplage Jinja2 dans système prompts ; perte de lisibilité ; pas de git diff propre entre variantes. |
| **Split par utilisateur** (ex. 50/50 par session) | Pas de session multi-user en usage perso solo. Split par mission_id est plus naturel et reproductible. |
| **Outil tiers (LangSmith, Statsig)** | Dépendance externe SaaS. Le projet est local-first et solo. Service interne minimaliste suffit. |

## Conséquences

### Positives

- **Mesure objective** : un changement de prompt est validé sur 10+ missions
  avant promotion, pas sur 1 mission ressentie comme "meilleure".
- **Rollback trivial** : l'archive `<role>_archived_YYYYMMDD.md` permet de
  restaurer en `cp` + relancer.
- **Cohérence resume** : un re-run avec même mission_id utilise la même
  variante (sélection déterministe par hash).
- **Suggest-only = pas de risque autonome** : humain garde le contrôle.

### Négatives / à surveiller

- **Sample size** : sur usage perso (1-3 missions/jour), atteindre n=10
  par variante prend ~1 semaine. Acceptable pour itérations lentes ; à
  surveiller que l'humain ne promote pas trop tôt.
- **Pas de stratification** : si on A/B teste sur 10 missions toutes
  Engineering, conclusion non applicable à Research. À mitigé en
  documentant les variantes (à quel type de mission elles s'adressent).
- **Variantes non auto-générées** : reste manuel. Si on veut "le système
  m'a proposé 3 variantes basées sur les missions failed", c'est v2.

### Conditions de promotion vers auto-promote (v2)

L'auto-promote sera réactivé si **toutes** ces conditions :
1. >5 promotions humaines ont été faites en MVP, sans regret.
2. Les critères d'auto-promotion sont écrits formellement (seuils de
   significance statistique non discutables a posteriori).
3. Un mode "dry-run preview" permet à l'humain de revoir les promotions
   automatiques avant chaque batch.

## Métriques de suivi

À 1 mois post-livraison :
- ≥1 paire de variantes A/B en place et trafic mesuré.
- 0 régression silencieuse (rétrocompat = pas opt-in = comportement inchangé).
- L'auteur a tranché ≥1 promotion (validation que l'UX décisionnelle marche).

Si métriques OK, on évalue auto-generation des variantes via LLM en v1.x.
