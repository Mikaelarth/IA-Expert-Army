# ADR-011 — Quality Guardian (peer review méta cross-guilde)

**Statut :** Accepted
**Date :** 2026-05-14
**Commits associés :** Sprint YY

## Contexte

Le master plan (cf. plan stratégique approuvé) prévoit en Couche 1 un agent **Quality Guardian** dont le rôle est *« validation finale, peer review global, refus si qualité insuffisante »*. Promesse non livrée jusqu'à v0.2.0.

Jusque-là, chaque guilde a son **reviewer interne** (CodeReviewer, ResearchReviewer, Editor, LegalReviewer) qui juge la qualité TECHNIQUE de l'output dans son domaine. Mais aucun agent ne vérifie 4 axes critiques en mode autonome :

1. **Alignement promesse ↔ livraison** : la guilde a-t-elle réellement répondu à la demande utilisateur ?
2. **Dérive de scope** : over-engineering (5 features livrées pour 1 demandée) ou under-delivery déguisée en APPROVED ?
3. **Cohérence inter-guilde** (meta-missions) : les livrables des sous-missions s'assemblent-ils en un produit cohérent ?
4. **Calibration du verdict guilde** : un score 0.95 sur un livrable trivial ou 0.65 sur un livrable solide-mais-pinaillé sont suspects.

En mode autonome, où l'utilisateur ne peut pas valider chaque mission individuellement, l'absence de ce filet méta = risque d'accumuler des skills polluées (over-engineered patterns) ou de livrer des outputs alignés à 80% qui passent comme APPROVED.

## Décision

Introduire le **`QualityGuardian`** comme agent stratégique (Opus, 2048 tokens, max 2 min de raisonnement). Sa sortie YAML compact (verdict + scores + concerns + rationale) est ajoutée au `UnifiedMissionResult` retourné par `MissionRouter.run()` sous des champs préfixés `qg_*`.

### Sémantique du verdict QG

| Verdict | Quand l'émettre | Effet downstream |
|---|---|---|
| **ACCEPT** | Alignement OK, scope cadré, verdict guilde défendable | Mission validée, eligible au mining si la guilde a APPROVED |
| **NEEDS_REWORK** | Désalignement significatif, dérive importante, ou score guilde non défendable | Le caller (PatternMiner, run_mission) doit ne PAS miner cette mission et notifier l'utilisateur |
| **ESCALATE** | Situation ambiguë : QG ne peut pas statuer (brief flou, domaine hors expertise QG) | Approbation humaine requise |

### Politique : pas d'override automatique du verdict guilde

C'est le point le plus important du design. Le QG :
- **N'override JAMAIS** `final_verdict` retourné par la guilde.
- **N'override JAMAIS** `quality_score` produit par le reviewer guilde.
- Ajoute uniquement les champs informatifs `qg_verdict`, `qg_final_score`, `qg_concerns`, `qg_rationale`.

Rationale : les guildes ont une légitimité de domaine que le QG n'a pas. Si le QG dit NEEDS_REWORK alors que la guilde APPROVED, c'est au **caller** (run_mission CLI affichant l'avertissement, PatternMiner filtrant le mining, daily_digest reportant) de décider quoi faire.

Cette séparation permet de :
- A/B tester les verdicts QG vs guilde sur N missions avant d'engager un override automatique.
- Déboguer plus facilement : on voit l'écart QG↔guilde sans qu'il n'affecte le résultat.
- Donner le pouvoir final à l'humain en mode hybride.

### Opt-in via Settings

`enable_quality_guardian: bool = False` (défaut). Activable via `.env` :

```
ENABLE_QUALITY_GUARDIAN=true
```

Rationale du défaut OFF :
- **Coût** : +1 appel Opus / mission = +$0.10-0.20. Pour les sessions de dev où l'humain valide, c'est gaspillé.
- **Latence** : +5-10s par mission. Non négligeable pour des missions courtes.
- **Recommandation forte d'activer en mode `autonomous_run.py`** ou tout mode prod sans validation humaine.

### Skip explicite sur verdict REJECTED

Si la guilde retourne `REJECTED`, le QG **valide sans appel API** (économie + cohérence). Pas de raison d'overrider un REJECTED — le filet est déjà serré.

## Conséquences

**Positives :**
- Filet méta cross-guilde livré, conforme à la promesse master plan.
- Coût additionnel maîtrisé (opt-in, skip REJECTED, max 2048 tokens out).
- Pas de régression possible des mécanismes existants (le QG est additif, pas substitutif).
- Le `PatternMiner` peut désormais filtrer sur `qg_verdict == ACCEPT` pour ne miner que les missions doublement validées.

**Négatives / à surveiller :**
- **Double cost overhead** : sur les meta-missions cross-guildes, le QG s'appliquerait à chaque sub-mission. Pour v0.2.0, le QG est sur le `MissionRouter` (= une fois par sub-mission). Coût : 3 sub-missions × $0.15 QG = $0.45 ajouté à une meta-mission. À considérer.
- **Risque de "rubber-stamp"** : si Opus QG est trop conservateur, il dira toujours ACCEPT et n'aura aucune valeur. Surveiller la distribution des verdicts QG sur les premières missions et raffiner le prompt si > 95% ACCEPT.
- **Pas de retry automatique sur NEEDS_REWORK** : la mission qui obtient NEEDS_REWORK QG n'est pas relancée. C'est une politique conservatrice mais qui peut frustrer (utilisateur paye et n'a pas de remédiation auto). v2 possible : auto-relance une fois avec les concerns en contexte.

## Alternatives considérées

- **Override automatique du verdict guilde** : rejeté. Le QG n'a pas la légitimité technique (cf. politique de séparation ci-dessus). Pourrait être réactivé en v2 quand on aura mesuré la distribution des QG verdicts.
- **QG sur les workflows internes des guildes** (avant le verdict guilde) : rejeté. Le rôle du reviewer interne est précisément la qualité technique ; ajouter un QG en amont créerait de la confusion et dupliquerait le travail.
- **QG en mode synchrone bloquant** : adopté. L'alternative async-fire-and-forget (logguer le QG sans bloquer le return) ferait perdre l'enrichissement du `UnifiedMissionResult` pour le caller — trop fragile.
- **Sonnet au lieu d'Opus pour le QG** : testé mentalement, rejeté. Le QG doit avoir du discernement subtil (calibration de score, détection over-engineering) — Opus produit des verdicts plus défendables. Coût marginal +$0.10/mission acceptable pour la valeur.

## Validation expérimentale

Smoke run Sprint YY (à compléter post-commit) : 1 mission engineering simple avec `enable_quality_guardian=true`. Critères de succès :
1. Le QG est appelé et retourne un verdict YAML parsable.
2. Les champs `qg_*` sont peuplés dans le `UnifiedMissionResult` final.
3. Le verdict guilde n'est pas modifié.
4. Coût additionnel mesuré : doit être dans la fourchette $0.10-0.20.

## Pour la suite

- **Métriques QG dans `daily_digest`** : ajouter un compteur "missions où qg_verdict ≠ guild_verdict" — c'est la métrique-clé pour savoir si le QG apporte de la valeur ou rubber-stamp.
- **PatternMiner filter** : ajouter `qg_verdict == ACCEPT` dans les critères d'éligibilité mining (cf. ADR-006).
- **CLI `--qg` flag** : permettre l'activation du QG par mission individuelle dans `run_mission.py`, indépendamment de Settings.
- **MetaWorkflow QG** : décider si le QG s'applique à chaque sub-mission (overhead linéaire), à la meta-mission globale (single check), ou les deux (overhead + cohérence).
- **Override automatique conditionnel** : v2 possible — si QG produit NEEDS_REWORK avec une `final_score` < seuil et un guild_verdict APPROVED, déclencher automatiquement un repair loop avec les `meta_concerns` injectés. À mesurer avant d'activer.
