# ADR-010 — Protocole de validation Phase 6 (autonomie 24h)

**Statut :** Accepted
**Date :** 2026-05-14
**Commits associés :** `scripts/autonomous_run.py` + suite de tests (Sprint C)

## Contexte

Le master plan définit la Phase 6 comme **« Mode pleinement autonome avec garde-fous »** et son critère de succès comme :

> *« Mission longue 24h sans dérive, dans budget »*

Jusqu'ici, les garde-fous étaient **testés unitairement** (BudgetController, Killswitch, saturation detection) mais jamais **exercés ensemble en condition réelle** sur une fenêtre temporelle longue. Une mission individuelle prouve que le système ne crashe pas — une fenêtre 24h prouve que le système ne **dérive** pas (qualité moyenne ne chute pas, coûts ne dérapent pas, taux d'erreur ne grimpe pas).

## Décision

Créer un **harness autonome** (`scripts/autonomous_run.py`) qui exécute une queue YAML de missions séquentiellement, en évaluant **5 garde-fous** entre chaque mission. Un dépassement de l'un d'eux provoque un arrêt propre avec rapport circonstancié.

### Les 5 garde-fous (en code, testés unitairement)

1. **Budget floor** : `budget_remaining_today() ≥ $5` (défaut, paramétrable `--budget-floor`).
   - Limite hard, indépendante du daily cap.
   - Empêche d'épuiser le budget jusqu'au dernier cent — laisse une réserve pour les interventions manuelles du lendemain.

2. **Killswitch clear** : `Killswitch.assert_clear()` ne doit pas lever.
   - L'utilisateur peut engager le killswitch à tout moment (touchant `data/.killswitch`) pour stopper le run sans attendre le rapport.

3. **Error rate** : `errored / N < 30%` sur les `N=5` dernières missions.
   - « errored » = exception levée OU verdict `FAILED:*`.
   - Circuit breaker : un système qui se casse 2 fois sur 5 ne devrait pas continuer à brûler du budget.

4. **Saturation rate** : `saturated / N < 20%` sur les `N=5` dernières.
   - Limite plus sévère que les erreurs : la saturation est un *symptôme silencieux* (le verdict peut être correct mais la sortie est tronquée).
   - Si 1 mission sur 5 sature, c'est qu'un `DEFAULT_MAX_TOKENS` est sous-dimensionné quelque part → on stoppe pour permettre le diagnostic (cf. ADR-005).

5. **Quality moving average** : `avg(quality_score) ≥ 0.70` sur les `N=5` dernières.
   - Détection de **dérive** : si la qualité moyenne chute sous 0.70, le système produit du travail médiocre — pas la peine de continuer.
   - Le seuil 0.70 correspond au plancher empirique observé sur APPROVED missions (les meilleurs sont autour de 0.85-0.95, les NEEDS_CHANGES légers à 0.75-0.85). En dessous de 0.70, on est en zone REJECTED implicite.

### Pourquoi ces 5 et pas d'autres

Les 5 sont **strictement non-redondants** :
- 1 garde le budget (économique)
- 2 garde l'override humain (gouvernance)
- 3 garde la fiabilité (taux de plantage)
- 4 garde la qualité explicite (tronquage)
- 5 garde la qualité implicite (dérive sémantique)

D'autres candidats considérés et **rejetés** pour le MVP :
- **Latence moyenne par mission** : utile mais corrélé à la qualité (si un agent satare il tourne souvent plus longtemps). Pas indispensable v1.
- **Coût moyen par mission** : déjà capté par le budget floor + un compteur dans le rapport. Une « explosion de coût » se manifeste par épuisement plus rapide du floor — couvert.
- **Diversité des guildes** : intéressant pour Phase 7 (assurer qu'on ne reste pas coincé dans une seule guilde) mais hors scope Phase 6.

### Fenêtre glissante (`N=5`)

Calibrée pour équilibrer **sensibilité** (réagir vite à un problème) et **stabilité** (ne pas trigger sur un seul accident isolé). Sur N=3, un test échoué donne 33% error rate → trop sensible. Sur N=10, on tolère 2 erreurs avant alerte → trop lent en début de run.

5 missions = ~25 min en moyenne (5 min/mission). C'est la granularité où un opérateur attentif voudrait être notifié.

## Conséquences

**Positives :**
- Le critère « Phase 6 réussie » devient un fichier YAML + une commande, pas une promesse abstraite.
- La logique des garde-fous (`evaluate_guardrails`) est une **pure function** : 8 tests unit couvrent toutes les conditions de déclenchement.
- Le rapport markdown est self-contained et exploitable a posteriori (timeline, raison d'arrêt, stats).
- L'arrêt est **gracieux** : la mission courante termine, l'épisode est archivé, le rapport est écrit. Pas de corruption.

**Négatives / à surveiller :**
- **Le run est séquentiel** : 24h = ~288 missions à 5min chacune. En pratique, on ne testera jamais 288 missions distinctes (où trouver les sujets ?). La fenêtre 24h ressemblera plutôt à 10-30 missions étalées, avec du repos entre.
- **La queue YAML est statique** : pas de génération automatique de sujets. Pour une vraie Phase 6, soit on charge un backlog produit (réaliste), soit on ajoute un `TopicGenerator` Haiku qui propose des missions. v2.
- **Aucun mode "drain" partiel** : si le run s'arrête au garde-fou #2, les 3 missions restantes ne sont pas mises de côté pour redémarrage ultérieur — l'opérateur doit éditer la queue manuellement. v2 possible avec un état persistant.

## Alternatives considérées

- **Cron + script court** : rejeté. Le cron lance un nouveau process à chaque tick → réinit cold du venv + pas de mémoire glissante facile. La boucle interne avec garde-fous est plus naturelle.
- **Une "watcher" daemon qui surveille les missions lancées par d'autres outils** : reporté. Phase 6 vise *le système qui se gère lui-même*, pas *un outil de monitoring externe*. Ce dernier viendra avec Langfuse en Phase 8+.
- **Garde-fous "soft" (warn-only)** : rejeté. Tout l'enjeu est qu'un opérateur **peut** lâcher le système — donc les seuils doivent **stopper**, pas juste alerter. Un alert sans stop fait perdre la confiance dans l'autonomie.

## Validation expérimentale (Sprint C smoke run)

Un smoke run a été exécuté le **2026-05-14 13:15 UTC** sur la queue
`data/autonomous_queue_smoke.yml` (2 missions engineering + 1 research).

**Résultats observés** :

| Mission | Guilde | Verdict | Score | Coût | Durée |
|---|---|---|---|---|---|
| Hello health endpoint | engineering | APPROVED | 0.97 | $0.34 | 74s |
| Slugify utility | engineering | APPROVED | 0.93 | $0.38 | 92s |
| Comparatif Pydantic v1 vs v2 | research | APPROVED | 0.91 | $0.27 | 130s |
| **Total** | — | **3/3 APPROVED** | **0.94 avg** | **$1.00** | **5.0 min** |

**Garde-fous évalués** : 3 fois (avant chaque mission). **Aucun déclenché** (état toujours sain). Raison d'arrêt : `queue épuisée`. Exit code : 0.

Critères du smoke validés :
1. ✅ Le loop traverse la queue sans crash.
2. ✅ Les 5 garde-fous sont évalués entre chaque mission (vérifié via les logs).
3. ✅ Le rapport markdown est produit (`data/autonomous_runs/20260514T131532.md`) avec timeline + stats.
4. ✅ L'exit code distingue "queue épuisée" (0) de "garde-fou déclenché" (3) — vérifié à l'unit + dans ce smoke (exit 0).

**Note** : ce smoke ne **stresse** pas les garde-fous (tout passe). Pour vraiment exercer le path d'arrêt, on pourrait soit :
- (a) Lancer avec `--budget-floor 100.0` (jamais satisfait → STOP immédiat).
- (b) Mocker une mission qui sature → trigger guardrail #4.

Les 21 tests unit couvrent déjà ces cas. Le smoke vise à valider l'**intégration**, pas les seuils.

## Procédure pour un vrai run 24h

1. **Préparer une queue réaliste** dans `data/autonomous_queue_24h.yml` (15-30 missions hétérogènes, mélange engineering / research / creative / business, avec quelques `--meta` cross-guildes).
2. **Vérifier l'état initial** : `just health`, `just budget` (idéal : restant ≥ $25).
3. **Lancer** : `nohup uv run python scripts/autonomous_run.py --queue data/autonomous_queue_24h.yml > run.log 2>&1 &`
4. **Surveiller passivement** : `tail -f run.log` quand on veut, ou consulter le rapport intermédiaire dans `data/autonomous_runs/` (un fichier est écrit même en cas d'arrêt anticipé).
5. **Killswitch d'urgence** : `just killswitch engage` → la mission courante termine, le run s'arrête au prochain check.

## Pour la suite

- **TopicGenerator (Haiku)** : génère N missions automatiquement à partir d'un thème ou d'un backlog GitHub.
- **State persistant** : si le run s'arrête au milieu, sauvegarder l'index de la queue + les records pour reprendre exactement où on s'est arrêté.
- **Métriques cumulatives dans `daily_digest`** : ajouter un compteur "autonomous runs aujourd'hui" + raison d'arrêt majoritaire.
- **Test d'intégration mocké** : `pytest -m autonomous` qui lance `run_autonomous` avec un MissionRouter mocké pour valider le loop en CI (sans coût API).
