# Operations Guide — IA Expert Army en autonome 24/7

> Ce guide couvre tout ce qui concerne le **mode opérationnel** : déploiement
> sur VPS, exécution autonome, monitoring, garde-fous, économie de coût API.
> Pour démarrer en local, voir [docs/getting-started.md](getting-started.md).

---

## Table des matières

1. [Vue d'ensemble du mode autonome](#1-vue-densemble-du-mode-autonome)
2. [Déploiement sur VPS](#2-deploiement-sur-vps)
3. [Configuration des garde-fous](#3-configuration-des-garde-fous)
4. [Notifications mobiles](#4-notifications-mobiles-discordslacktelegram)
5. [Monitoring et observabilité](#5-monitoring-et-observabilite)
6. [Réduire le coût Anthropic](#6-reduire-le-cout-anthropic)
7. [Migration VPS → VPS sans perte](#7-migration-vps-vps-sans-perte)
8. [Backup & disaster recovery](#8-backup-disaster-recovery)
9. [Mode service systemd](#9-mode-service-systemd)
10. [Commandes opérationnelles courantes](#10-commandes-operationnelles-courantes)

---

## 1. Vue d'ensemble du mode autonome

Le mode autonome (`scripts/autonomous_run.py`) prend une **queue YAML de missions** et les exécute séquentiellement avec **5 garde-fous non négociables** :

| Garde-fou | Comportement | ADR |
|---|---|---|
| Budget journalier | STOP si `daily_budget_usd` épuisé | [ADR-003](adr/003-autonomy-with-guardrails.md) |
| Killswitch | STOP si fichier `data/.killswitch_engaged` présent | [ADR-003](adr/003-autonomy-with-guardrails.md) |
| Error rate | STOP si > 30% des N dernières missions ont échoué | [ADR-010](adr/010-phase-6-autonomous-validation.md) |
| Saturation rate | STOP si > 20% des N dernières missions ont saturé | [ADR-005](adr/005-saturation-detection-and-prevention.md) |
| Quality drift | STOP si moving avg quality < 0.70 | [ADR-010](adr/010-phase-6-autonomous-validation.md) |

À chaque arrêt, un **rapport markdown** est écrit dans `data/autonomous_runs/<timestamp>.md` avec timeline, stats par mission, raison d'arrêt.

### Lancement basique

```bash
uv run python scripts/autonomous_run.py \
  --queue data/autonomous_queue.yml \
  --max-missions 10 \
  --notify  # Sprint HHH : envoi du rapport via webhook (Discord/Slack/Telegram)
```

### Format de la queue YAML

```yaml
# data/autonomous_queue.yml
missions:
  - title: "Endpoint /uptime"
    description: "Crée un endpoint FastAPI GET /uptime..."
    guild: engineering   # optionnel — sinon auto-routé via mots-clés

  - title: "Comparatif RAG vs Fine-tuning 2026"
    description: "Synthétise les trade-offs entre les 2 approches..."
    guild: research
```

### Templates prêts à l'emploi

Pas besoin de partir de zéro — **7 templates documentés** dans
[`data/example_queues/`](https://github.com/MikaelArth/IA-Expert-Army/tree/main/data/example_queues) couvrent les
cas d'usage canon :

| # | Template | Cas d'usage | Coût | Durée |
|---|---|---|---|---|
| 01 | `01-engineering-simple.yml` | 3 fonctions Python courtes | ~$1.50 | ~5 min |
| 02 | `02-research-veille.yml` | 3 synthèses / comparatifs | ~$1.00 | ~6 min |
| 03 | `03-creative-content.yml` | Landing + email + blog | ~$0.80 | ~5 min |
| 04 | `04-business-roadmap.yml` | Roadmap + viabilité + RGPD | ~$1.50 | ~6 min |
| 05 | `05-cross-guildes-mvp.yml` | Méta-mission cross-guildes | ~$4-5 | ~12 min |
| 06 | `06-engineering-api-complete.yml` | Mission étalon FastAPI JWT/CRUD | ~$1.74 | ~12 min |
| 07 | `07-stress-test-budget.yml` | 10 missions courtes (stress garde-fous) | ~$3-5 | ~25-40 min |

Pour démarrer : `01-engineering-simple.yml` est le plus rapide et le moins
cher. Lance avec `--max-missions 1` la première fois pour valider :

```bash
uv run python scripts/autonomous_run.py \
  --queue data/example_queues/01-engineering-simple.yml \
  --max-missions 1
```

---

## 2. Déploiement sur VPS

### Choix du VPS (OVH 2026)

| Profile | vCores | RAM | NVMe | Prix HT/mois | Use case |
|---|---|---|---|---|---|
| **VPS-1** | 4 | 8 Go | 75 Go | 5,52 € | Solo, missions séquentielles |
| **VPS-2** | 6 | 12 Go | 100 Go | 8,49 € | + Langfuse self-hosted + 2-3 missions concurrentes |
| **VPS-3** | 8 | 24 Go | 200 Go | 16,99 € | Multi-utilisateurs, autonomie 24/7, multi-Langfuse |

> Recommandation pour démarrer : **VPS-1** (suffisant). Migration VPS-1 → VPS-2 → VPS-3 se fait **sans perte** via `migrate_vps.sh` (cf. §7).

### Provisioning automatique

```bash
# Sur le VPS (Ubuntu 22.04+ ou Debian 12)
curl -sSL https://raw.githubusercontent.com/MikaelArth/IA-Expert-Army/main/scripts/deploy_vps.sh | sudo bash
```

Le script (idempotent) installe :
1. Paquets système (build-essential, git, jq, htop, tmux)
2. Docker + docker-compose
3. User dédié `iaa-army` (non-root, dans groupe docker)
4. Python 3.12+ via uv
5. Clone du repo dans `/opt/ia-expert-army`
6. `.env` minimal (à éditer pour ajouter `ANTHROPIC_API_KEY`)
7. Build de l'image sandbox

Auto-détection du profil VPS depuis `/proc/meminfo` :
- ≤ 9 Go → `vps1`
- ≤ 14 Go → `vps2`
- > 14 Go → `vps3`

### Configuration `.env` recommandée pour autonome

```bash
# Backend LLM Ollama local (ADR-025) — pré-requis : Ollama installé + modèles pullés
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_API_KEY=ollama
OLLAMA_TIMEOUT_SECONDS=900
MODEL_STRATEGIC=qwen2.5:32b
MODEL_OPERATIONAL=qwen2.5-coder:32b
MODEL_BULK=qwen2.5:14b

# Budget désactivé par défaut (Ollama gratuit). Réactivable en cap proxy
# tokens/temps si besoin — mettre une valeur > 0.
DAILY_BUDGET_USD=0.0

# Garde-fous qualité opt-in (coûtent du temps de génération, pas de l'USD)
ENABLE_QUALITY_GUARDIAN=true   # peer review méta cross-guilde (+1 appel Opus-équivalent)
ENABLE_SECURITY_AUDITOR=true   # audit OWASP/secrets engineering (+1 appel Sonnet-équivalent)

# Notifications mobiles (cf. §4)
NOTIFY_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Profile pour le diagnostic
VPS_PROFILE=vps1
```

Pour tous les détails d'install : [docs/deploy.md](deploy.md).

---

## 3. Configuration des garde-fous

### Hard cap budget journalier

```bash
# Statut courant
just budget
# ou : uv run python scripts/budget.py status

# Reset manuel (urgence légitime uniquement)
just budget-reset

# Bumper le cap
echo "DAILY_BUDGET_USD=100.0" >> .env
```

Le `BudgetController` archive l'état dans `data/budget_state.json` avec rotation à minuit UTC. **Refus prouvé en condition réelle** sur missions cross-guildes — cf. [ADR-003](adr/003-autonomy-with-guardrails.md).

### Killswitch d'urgence

```bash
# ENGAGE — stoppe tout traitement en cours, refuse tout nouveau
just killswitch engage

# STATUT
just killswitch status

# RELÂCHE
just killswitch release
```

Le killswitch est un **fichier sentinel** (`data/.killswitch_engaged`) :
zéro dépendance, zéro fragilité. Tout `Workflow.run` vérifie sa présence
avant chaque appel LLM.

### Tests régression sur les garde-fous

```bash
just test-cov  # 573 tests + coverage
```

Les garde-fous ont leurs propres tests : `test_workflow_guardrails.py`,
`test_budget.py`, `test_killswitch.py`.

---

## 4. Notifications mobiles (Discord/Slack/Telegram)

Active la notification du daily digest et des alertes critiques sur ton téléphone via un webhook configuré dans `.env`.

### Setup en 30 secondes (Discord)

1. Sur ton serveur Discord : `Paramètres serveur` → `Intégrations` → `Webhooks` → `Nouveau webhook`
2. Copie l'URL (commence par `https://discord.com/api/webhooks/...`)
3. Édite `.env` :

```bash
NOTIFY_WEBHOOK_URL=https://discord.com/api/webhooks/<ID>/<TOKEN>
NOTIFY_BACKEND=auto   # détecte Discord depuis l'URL
```

4. Vérifie :

```bash
uv run python scripts/health_check.py --notify-test
```

Tu reçois un message de test sur ton serveur Discord. Si OK, c'est branché.

### Backends supportés

| Backend | URL pattern | Format envoyé |
|---|---|---|
| Discord | `discord.com/api/webhooks/...` | embeds colorés par level |
| Slack | `hooks.slack.com/services/...` | blocks markdown |
| Telegram | `api.telegram.org/bot.../sendMessage?chat_id=...` | text markdown |
| Generic (n8n, Pipedream, Zapier...) | tout autre URL | JSON brut `{level, title, body, timestamp}` |

### Quoi déclenche une notification ?

- `daily_digest.py --notify` → envoie le digest du jour (level WARNING si REJECTED présent, sinon INFO)
- `autonomous_run.py --notify` → envoie le rapport final (SUCCESS si queue drainée, WARNING si garde-fou déclenché)

Pour déclencher le digest tous les soirs sur le VPS via cron :

```bash
# crontab -e (en tant qu'iaa-army)
0 22 * * * cd /opt/ia-expert-army && uv run python scripts/daily_digest.py --notify
```

Détails techniques + alternatives écartées : [ADR-018](adr/018-mobile-notifications.md).

---

## 5. Monitoring et observabilité

### Daily digest (gratuit, intégré)

```bash
uv run python scripts/daily_digest.py
```

Affiche : missions du jour, coût, verdicts, QG concerns, approvals pending, skills générées.

### Health check global

```bash
just health         # check complet (Docker + Langfuse + tout)
just health-quick   # skip Docker (pour CI)
```

Affiche un tableau de 17 composants : Setup, Couches 2-4, Garde-fous, Notification, Déploiement, Documentation, Sandbox, Observabilité.

### Langfuse self-hosted (⛔ non recommandé en l'état au 2026-05-21)

> **Statut clarifié Session 6** : la stack 6 containers (`docker compose --profile observability up -d`) démarre, mais la config v3 du `docker-compose.yml` est incomplète — les migrations ClickHouse échouent au premier boot (env vars supplémentaires non mappées vs la doc officielle Langfuse v3). **Ne pas activer cette stack** tant qu'un sprint dédié n'a pas remis à jour la config (cf. note dans `docker-compose.yml` + ADR-025).
>
> En attendant, utilise **Langfuse Cloud** (section suivante) — c'est gratuit jusqu'à ~1k traces/mois — ou rien (`structlog` console/JSON suffit pour usage perso).

### Langfuse Cloud (recommandé, free tier)

1. Crée compte sur [cloud.langfuse.com](https://cloud.langfuse.com)
2. Crée un projet, récupère public + secret keys
3. Édite `.env` :

```bash
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-cloud-...
LANGFUSE_SECRET_KEY=sk-lf-cloud-...
```

Limite gratuite : **1000 traces/mois** (~30 missions APPROVED/jour).

---

## 6. Réduire le coût Anthropic

### Tier mixing (politique ADR-016)

Le projet utilise 3 modèles Claude :
- **Opus** (`model_strategic`) — ~$15/$75 per Mtok in/out
- **Sonnet** (`model_operational`) — ~$3/$15 (5× moins cher)
- **Haiku** (`model_bulk`) — ~$0.80/$4 (15× moins cher)

État au Sprint EEE.v1 : **8 agents Opus, 9 agents Sonnet, 1 agent Haiku**.
Économie déjà appliquée sur SkillExtractor (mining nightly) et MetaDecomposer
(décomposition cross-guildes). Total ~10-20% réduction sur missions cross-guildes.

### Garder le contrôle

Ajout d'un agent Opus = engagement explicite. Le test `test_opus_agent_count_under_threshold`
plafonne à **7 agents Opus max**. Et l'audit `OPUS_WITHOUT_JUSTIFICATION` exige
un commentaire `# Opus :` à proximité de chaque usage de `model_strategic`.

### Surveillance proactive

```bash
# Coût de la dernière mission archivée
just digest

# Statut budget
just budget
```

Et bien sûr le notifier (§4) t'envoie une alerte sur ton mobile dès que le budget dérape.

---

## 7. Migration VPS → VPS sans perte

Le système accumule de la valeur (mémoire, skills, vector DB). Quand tu changes de VPS, **ne perds rien** via `migrate_vps.sh` :

### Export depuis VPS source

```bash
sudo -u iaa-army bash /opt/ia-expert-army/scripts/migrate_vps.sh \
  export /tmp/iaa-snapshot.tar.gz
```

Inclut : `data/memory/` (épisodes, missions, meta-missions), `data/chroma/` (vector DB),
`data/budget.json`, `data/error_log.json`, `data/approvals/`, `skills/`, `prompts/`,
`.env` (credentials + tunings).

**Garanties** : killswitch engagé pendant l'export (cohérence) + manifest JSON
avec checksums sha256 (vérifiables à l'import).

### Transfert

```bash
scp source-vps:/tmp/iaa-snapshot.tar.gz dest-vps:/tmp/
# ou rsync pour reprendre sur connexion fragile :
rsync -avz --progress source-vps:/tmp/iaa-snapshot.tar.gz dest-vps:/tmp/
```

### Import sur VPS destination

```bash
sudo -u iaa-army bash /opt/ia-expert-army/scripts/migrate_vps.sh \
  import /tmp/iaa-snapshot.tar.gz
```

**Garanties** :
1. **Verify automatique** des checksums avant import (refus si altéré)
2. **Backup pré-migration** dans `data/.pre-migrate-backup-YYYYMMDD-HHMMSS/` (rollback trivial)
3. **Killswitch engagé** pendant l'import
4. Permissions `chown iaa-army`, `.env` à 600

### Rollback en cas de problème

```bash
sudo -u iaa-army touch /opt/ia-expert-army/data/.killswitch_engaged

BACKUP_DIR=$(ls -1d /opt/ia-expert-army/data/.pre-migrate-backup-* | tail -1)
for p in data/memory data/chroma data/budget.json data/error_log.json data/approvals skills prompts; do
    rm -rf "/opt/ia-expert-army/$p"
    cp -a "$BACKUP_DIR/$p" "/opt/ia-expert-army/$p" 2>/dev/null
done

sudo -u iaa-army rm -f /opt/ia-expert-army/data/.killswitch_engaged
```

Tests round-trip exécutables : `tests/integration/test_migrate_vps.py` (6 tests, garantissent zéro corruption sur Linux ET Windows).

Détails complets : [ADR-017](adr/017-vps-deployment.md).

---

## 8. Backup & disaster recovery

### Backup local atomique

```bash
just backup       # snapshot data/ + skills/ + prompts/ + ADRs + configs
just backup-list  # liste les backups (rotation auto : garde 7 derniers)
```

Le backup est un ZIP avec manifest JSON, créé atomiquement (rename à la fin).
Pas de risque de backup corrompu en cas de crash mid-write.

### Restore

```bash
just restore-latest                              # le plus récent
just restore-from data/backups/iaa-backup-2026-05-15.zip   # ciblé
```

Le restore demande confirmation par défaut. Il valide les checksums sha256
contre le manifest avant écriture, et refuse path traversal.

### Cron quotidien recommandé sur VPS

```bash
# crontab -e (root)
0 3 * * * /usr/bin/sudo -u iaa-army /opt/ia-expert-army/scripts/migrate_vps.sh export /home/iaa-army/backups/iaa-$(date +\%Y\%m\%d).tar.gz
0 4 * * * /usr/bin/find /home/iaa-army/backups/ -name "iaa-*.tar.gz" -mtime +14 -delete
```

Pour stocker les backups hors-VPS (S3, B2, etc.), pipe vers `aws s3 cp` ou
`rclone copy` après l'export.

---

## 9. Mode service systemd

Pour lancer le mode autonome au boot (ou via `systemctl`), créer `/etc/systemd/system/iaa-army.service` :

```ini
[Unit]
Description=IA-Expert-Army autonomous worker
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=iaa-army
WorkingDirectory=/opt/ia-expert-army
ExecStart=/home/iaa-army/.local/bin/uv run python scripts/autonomous_run.py --queue data/autonomous_queue.yml --notify
Restart=on-failure
RestartSec=30
ExecStop=/usr/bin/touch /opt/ia-expert-army/data/.killswitch_engaged
MemoryHigh=4G   # vps1=4G, vps2=8G, vps3=16G
MemoryMax=6G

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now iaa-army
sudo systemctl status iaa-army
sudo journalctl -u iaa-army -f
```

---

## 10. Commandes opérationnelles courantes

| Tâche | Commande | Coût |
|---|---|---|
| Vérifier la santé du système | `just health` | 0 |
| Voir le digest du jour | `just digest` | 0 |
| Voir les backups existants | `just backup-list` | 0 |
| Approuver une demande HITL | `just approve <id> "raison"` | 0 |
| Lancer une mission interactive | `just mission` | ~$0.20-1.00 |
| Mining nightly (cron-able) | `just mine` | ~$0.05-0.50 |
| Démarrer Langfuse | `just langfuse-up` | 0 (~3 Go RAM) |
| Stopper Langfuse | `just langfuse-down` | 0 |

Toutes les recipes : `just` (sans argument liste tout).

---

## 11. Incidents et runbook

Pour les incidents complexes (corruption mémoire, désynchro chroma, budget bloqué, etc.) : [docs/runbook.md](runbook.md). 14 sections couvrant les cas observés en condition réelle.

**Procédure de crise globale** (toujours commencer par ces 3 commandes) :
```bash
# 1. ARRÊT
just killswitch engage

# 2. SNAPSHOT (avant tout changement)
just backup

# 3. DIAGNOSTIC
just health
just budget
ls data/autonomous_runs/ | tail -3
```

---

## ADRs liés

- [ADR-003 — Mode autonome avec garde-fous obligatoires](adr/003-autonomy-with-guardrails.md)
- [ADR-005 — Détection et prévention de la saturation](adr/005-saturation-detection-and-prevention.md)
- [ADR-010 — Phase 6 — validation autonome](adr/010-phase-6-autonomous-validation.md)
- [ADR-013 — Backup et disaster recovery](adr/013-backup-and-disaster-recovery.md)
- [ADR-014 — HITL approvals](adr/014-hitl-approvals.md)
- [ADR-016 — Tier mixing (Opus / Sonnet / Haiku)](adr/016-tier-mixing-strategy.md)
- [ADR-017 — Déploiement VPS multi-profile](adr/017-vps-deployment.md)
- [ADR-018 — Notifications mobiles via webhook](adr/018-mobile-notifications.md)
