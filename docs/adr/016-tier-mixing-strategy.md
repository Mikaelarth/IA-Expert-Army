# ADR-016 — Stratégie de tier mixing (Opus / Sonnet / Haiku)

**Statut :** Accepted
**Date :** 2026-05-14
**Commits associés :** Sprint EEE

## Contexte

Le projet utilise 3 modèles Anthropic via 3 alias de configuration :

- `model_strategic` (Opus 4.7) — ~$15/Mtok in, $75/Mtok out
- `model_operational` (Sonnet 4.6) — ~$3/Mtok in, $15/Mtok out
- `model_bulk` (Haiku 4.5) — ~$0.80/Mtok in, $4/Mtok out

Le ratio Opus/Sonnet est ~5× sur input et output. Une mission cross-guildes water-tracker à $4-5 contient ~30-40% de coût lié à des appels Opus. La compaction de coût est un objectif explicite (utilisateur a énoncé le 2026-05-14 : *"je ne voudrai pas être limité ou être dépendant comment faire ?"*).

À l'audit Sprint EEE, on constate que **8 agents sur 18** sont en Opus :

| Tier | Count | Agents |
|---|---|---|
| Strategic (Opus) | 8 | ChiefOrchestrator, SoftwareArchitect, QualityGuardian, SkillExtractor, MetaDecomposer, ResearchLead, ContentStrategist, BusinessAnalyst |
| Operational (Sonnet) | 9 | BackendDeveloper, CodeReviewer, SecurityAuditor, DocumentSynthesizer, ResearchReviewer, Copywriter, Editor, ProjectManager, LegalReviewer |
| Bulk (Haiku) | 1 | TechWatch |

## Décision

Distinguer **3 catégories d'agents** selon leur besoin réel de jugement :

### Catégorie A — Jugement critique irrémédiable (Opus obligatoire)

L'erreur de l'agent ne peut pas être rattrapée par un repair loop : son output est le squelette dont dépend tout le travail downstream, ou bien l'arbitrage final sur un verdict.

| Agent | Pourquoi Opus |
|---|---|
| **SoftwareArchitect** | Skeleton technique. Erreur d'arch = 100% du code downstream pourri. |
| **QualityGuardian** | Arbitre méta cross-guilde. Sa raison d'être est le discernement nuancé. |
| **BusinessAnalyst** | Verdict viable/non engage des décisions humaines. Raisonnement économique nuancé. |

### Catégorie B — Décomposition / planning template-guidé (Opus → Sonnet candidat)

L'agent décompose un input riche en suivant un template strict. La structure du template encadre suffisamment Sonnet pour qu'il livre du résultat équivalent.

| Agent | État Sprint EEE | Économie attendue |
|---|---|---|
| **SkillExtractor** | ✅ **VAGUE 1 → Sonnet** | ~5× sur mining nightly (~$0.05-0.15 par mining) |
| **MetaDecomposer** | ✅ **VAGUE 1 → Sonnet** | ~5× sur ce poste (~$0.20 par mission cross-guildes) |
| ChiefOrchestrator | ⏳ Vague 2 (smoke à valider) | ~5× sur ce poste (~$0.05-0.15 par mission) |
| ResearchLead | ⏳ Vague 2 | ~5× sur ce poste (~$0.10-0.30 par mission research) |
| ContentStrategist | ⏳ Vague 2 | ~5× sur ce poste (~$0.10-0.20 par mission creative) |

### Catégorie C — Production / review structurée (Sonnet)

Tous les développeurs / reviewers / copywriters / etc. produisent ou jugent du contenu selon des critères structurés. Sonnet est le tier optimal qualité/coût.

### Catégorie D — Balayage de connaissances (Haiku)

TechWatch fait du sourcing / recall — Haiku adéquat avec max_tokens=8192 à coût négligeable.

## Vague 1 — appliquée Sprint EEE

**Changements** :
- `SkillExtractor.model = model_operational` (était `model_strategic`)
- `MetaDecomposer.model = model_operational` (était `model_strategic`)

**Justification précise** :

1. **SkillExtractor** : input = N épisodes déjà structurés (chaque épisode étant lui-même issu d'un agent spécialisé qui a déjà fait le travail nuancé). Output = template YAML strict (`title + tags + summary + key_patterns + techniques + pitfalls + example_template`). C'est de la **synthèse template-guidée**. Bonus : tourne en NIGHTLY hors path mission live → impact qualité court terme = nul, rollback trivial si dégradation observée.

2. **MetaDecomposer** : input = description + titre. Output = ≤4 sous-missions, chacune routée vers UNE des 4 guildes valides, avec dépendances bornées. Schéma de validation strict (`_parse_decomposition` rejette tout ce qui sort du template). Sonnet **doit** produire dans ce template ou le résultat est rejeté avant exécution. Économie cumulative : appelé sur CHAQUE mission cross-guildes.

**Vérification empirique attendue** : sur la prochaine mission cross-guildes, comparer le coût `meta_decomposer` aux historiques (épisode `chief_orchestrator` du même type). Cible : ratio ~5× moindre.

## Vague 2 — différée

ChiefOrchestrator + ResearchLead + ContentStrategist sont des candidates plus risquées :
- **ChiefOrchestrator** : fait classification + petite réflexion sur scope. Erreur de routage = mission entière exécutée sur le mauvais problème.
- **ResearchLead** : décompose en sous-questions. Le découpage initial conditionne la qualité de toute la recherche downstream.
- **ContentStrategist** : positioning + audience + proofs. Conditionne le brief que Copywriter suit aveuglément.

Ces 3 sont à valider par smoke empirique sur 2-3 missions de chaque type avant déplacement. Plan : bumper temporairement avec un flag d'env, comparer scores avant/après sur N missions équivalentes.

## Garde-fou anti-dérive

Test régression `tests/unit/test_agent_model_tiers.py` :
- 1 test par agent assertant son tier exact
- 1 test méta `test_opus_agent_count_under_threshold` plafonnant à **7 agents Opus**
- Tests EEE renommés `test_*_sprint_eee_moved_to_sonnet` pour rendre visible la décision et bloquer un rollback silencieux

**Effet désiré** : si quelqu'un (humain ou agent) ajoute un nouvel Opus, le test pète immédiatement. Soit il déplace un autre Opus en compensation, soit il documente la décision dans un nouvel ADR.

## Conséquences

**Positives** :
- Économie attendue ~10-20% sur missions cross-guildes (impactées par MetaDecomposer)
- Économie ~5× sur mining nightly (SkillExtractor)
- Critère explicite de tier (catégories A/B/C/D) → décisions futures cadrées

**Négatives** :
- Risque de régression qualité sur SkillExtractor si Sonnet rate certaines synthèses subtiles. **Mitigation** : SkillExtractor est nightly donc 1) pas d'impact mission live, 2) on observe les skills produites, 3) rollback Opus en 1 ligne si nécessaire.
- Risque de régression sur MetaDecomposer si Sonnet rate des décompositions optimales. **Mitigation** : la validation structurelle (`_parse_decomposition`) bloque les sorties hors-template avant exécution. Une mauvaise décomposition se voit (sub-missions absurdes) et déclenche un re-run.

## Suivi

Métrique à observer sur les 5 prochaines missions cross-guildes :
- Coût épisode `meta_decomposer` (cible : ÷5)
- Coût total mission cross-guildes (cible : -10 à 20%)
- Verdict final (cible : pas de dégradation observable)

À la 5ᵉ mission, décider Vague 2 : GO si pas de dégradation, sinon analyser les cas problématiques avant.

## Alternatives considérées

1. **Tout passer en Sonnet** : refusé. Risque trop élevé sur Architect / QG / BA. Économie marginale (3 derniers Opus), risque énorme.
2. **Ajouter un 4ᵉ tier "synthesis" spécifique** : refusé. Sur-design pour 2 agents. Si le besoin émerge sur 5+ agents, on créera ce tier à ce moment.
3. **Auto-router Opus/Sonnet selon la complexité de l'input** : refusé. Implementation coûteuse, surface de bug, et le bénéfice est largement obtenu par le tier mixing manuel par agent.

## Sources

- Pricing Anthropic 2026-05 : Opus 4.7 ($15/$75 per Mtok), Sonnet 4.6 ($3/$15), Haiku 4.5 ($0.80/$4)
- Mission DDD.ter (`f8d1b181-f8a4-4e3e-b5ca-ee54a3346f86`) : 8 épisodes, $1.74 total, dont 3 épisodes Opus pour $1.14 (65% du coût)
- ADR-005 (saturation) : justifie max_tokens élevés sur les agents Sonnet (déjà 16384 sur BackendDeveloper, 8192 sur la plupart)
