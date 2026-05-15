# Example queues — Galerie de cas d'usage

> Templates de queues YAML prêts à l'emploi pour `scripts/autonomous_run.py`.
> Chaque fichier est un cas d'usage canon documenté avec coût attendu, durée
> et verdict cible.

---

## Vue d'ensemble

| # | Template | Cas d'usage | Coût attendu | Durée | Garde-fous testés |
|---|---|---|---|---|---|
| 01 | [`01-engineering-simple.yml`](01-engineering-simple.yml) | 3 fonctions Python courtes | ~$1.50 | ~5 min | — |
| 02 | [`02-research-veille.yml`](02-research-veille.yml) | 3 synthèses / comparatifs | ~$1.00 | ~6 min | — |
| 03 | [`03-creative-content.yml`](03-creative-content.yml) | 3 contenus marketing (landing, email, blog) | ~$0.80 | ~5 min | — |
| 04 | [`04-business-roadmap.yml`](04-business-roadmap.yml) | 3 outputs business (roadmap, viabilité, RGPD) | ~$1.50 | ~6 min | — |
| 05 | [`05-cross-guildes-mvp.yml`](05-cross-guildes-mvp.yml) | 1 méta-mission cross-guildes | ~$4-5 | ~12 min | — |
| 06 | [`06-engineering-api-complete.yml`](06-engineering-api-complete.yml) | Mission étalon FastAPI JWT/CRUD (Sprint DDD) | ~$1.74 | ~12 min | QG + Security |
| 07 | [`07-stress-test-budget.yml`](07-stress-test-budget.yml) | 10 missions courtes pour stress-tester garde-fous | ~$3-5 | ~25-40 min | **Les 5 garde-fous** |

**Coût total si tu lances tout** : ~$14-17. Pas conseillé en une fois sans
discipline budget (voir `DAILY_BUDGET_USD` dans `.env`).

---

## Pour démarrer

Commence par **`01-engineering-simple.yml`** : c'est le moins cher (~$1.50),
le plus rapide (~5 min), et c'est de l'Engineering qui produit du code
vérifiable que tu peux relire.

```bash
# Build l'image sandbox une fois (3 min, optionnel mais recommandé)
uv run python scripts/check_sandbox.py --build

# Lance la queue
uv run python scripts/autonomous_run.py \
  --queue data/example_queues/01-engineering-simple.yml \
  --notify
```

À la fin tu auras :
- Un rapport markdown dans `data/autonomous_runs/<timestamp>.md`
- 3 missions archivées dans `data/memory/missions/`
- 12 épisodes archivés dans `data/memory/episodes/`
- (si notifier configuré) Un message Discord/Slack/Telegram avec le résumé

---

## Choisir le bon template selon ton objectif

### Je veux voir ce que ça fait sans dépenser cher
→ `01-engineering-simple.yml` (~$1.50) ou `03-creative-content.yml` (~$0.80)

### Je veux valider que tout marche en condition réelle
→ `06-engineering-api-complete.yml` (mission étalon documentée, $1.74)
   avec `ENABLE_QUALITY_GUARDIAN=true` + `ENABLE_SECURITY_AUDITOR=true`

### Je veux tester le mode autonome 24/7
→ `07-stress-test-budget.yml` lancé en arrière-plan avec `--notify`
   et `--budget-floor` strict

### Je veux voir le cross-guildes (Engineering + Creative + Business)
→ `05-cross-guildes-mvp.yml` (méta-mission, ~$4-5, démontre `MetaWorkflow`)

### Je veux explorer les 4 guildes en une session
→ `01` + `02` + `03` + `04` lancés successivement (~$5 total)

---

## Format du fichier YAML

Schema validé par `parse_queue()` dans `scripts/autonomous_run.py` :

```yaml
missions:
  - title: "Titre court de la mission"
    description: |
      Description multi-ligne avec détails techniques,
      contraintes, critères d'acceptation.
    guild: engineering   # OU research | creative | business — optionnel
                          # (sinon auto-routé par mots-clés)

  - title: "Mission 2"
    description: "Une-ligne OK aussi"
    # pas de guild → MissionRouter décide via _ENGINEERING_KEYWORDS et co
```

Le `guild:` force le routage. Sans `guild:`, le `MissionRouter` analyse
le title + description et route vers Engineering / Research / Creative /
Business selon les mots-clés.

---

## Pour customiser

1. **Copie le template** qui se rapproche le plus de ton cas :
   ```bash
   cp data/example_queues/01-engineering-simple.yml data/my-queue.yml
   ```
2. **Édite les missions** : remplace title + description par les tiennes.
3. **Lance** :
   ```bash
   uv run python scripts/autonomous_run.py --queue data/my-queue.yml
   ```

`data/` est gitignoré (sauf ces templates) donc tes queues persos restent locales.

---

## Astuces budget

- **Toujours commencer par `--max-missions 1`** sur un nouveau template pour
  valider que la queue parse + 1 mission converge :
  ```bash
  uv run python scripts/autonomous_run.py --queue data/example_queues/01-... --max-missions 1
  ```
- **`--budget-floor` strict** pour les stress tests : 
  `--budget-floor 5.0` stoppe gracieusement si reste < $5 dans le cap journalier.
- **`--dry-run`** : parse la queue, n'exécute aucune mission. Utile pour
  valider un YAML avant de payer.

---

## Aller plus loin

- Vue complète du mode autonome : [docs/operations.md](../../docs/operations.md)
- Garde-fous détaillés : [ADR-003](../../docs/adr/003-autonomy-with-guardrails.md) et [ADR-010](../../docs/adr/010-phase-6-autonomous-validation.md)
- MetaWorkflow cross-guildes : [ADR-009](../../docs/adr/009-meta-workflow-cross-guilds.md)
- Mission étalon (template 06) : [ADR-015](../../docs/adr/015-etalon-mission-findings.md)
