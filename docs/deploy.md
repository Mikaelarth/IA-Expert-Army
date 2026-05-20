# Déploiement sur VPS — Guide complet

> Sprint GGG (2026-05-14) — Cible : OVH VPS-1 → VPS-2 → VPS-3, ou tout équivalent (Hetzner, Scaleway, DigitalOcean, AWS Lightsail, etc.) avec Ubuntu 22.04+ ou Debian 12+.

## TL;DR — déploiement initial en 5 minutes

```bash
# Sur le VPS (root ou sudo)
sudo bash <(curl -sSL https://raw.githubusercontent.com/MikaelArth/IA-Expert-Army/main/scripts/deploy_vps.sh)
sudo -u iaa-army nano /opt/ia-expert-army/.env  # ajoute ANTHROPIC_API_KEY
sudo -u iaa-army bash -lc "cd /opt/ia-expert-army && uv run python scripts/check_setup.py"
```

3 étapes. Tout le reste est documenté ci-dessous pour les cas non-trivials.

---

## 1. Choix du VPS

### Tableau comparatif (OVH, prix HT 2026-05)

| Profile | vCores | RAM | NVMe | Prix/mois | Use case |
|---|---|---|---|---|---|
| **VPS-1** | 4 | 8 Go | 75 Go | 5,52 € | Solo, missions séquentielles, sandbox léger |
| **VPS-2** | 6 | 12 Go | 100 Go | 8,49 € | Solo + Langfuse local + missions parallèles |
| **VPS-3** | 8 | 24 Go | 200 Go | 16,99 € | Multi-utilisateurs, autonomie 24/7, multi-Langfuse |

### Critères de choix par usage

**Démarrage (recommandé) : VPS-1**
- ✅ Suffisant pour : missions séquentielles, sandbox Docker, mémoire vector Chroma
- ❌ Limite : Langfuse self-hosted serré (~3 Go RAM pour PG+ClickHouse+Redis)
- 💡 Fallback Langfuse : utiliser Langfuse Cloud (free tier 1k traces/mois) ou désactiver

**Croissance : VPS-2**
- ✅ Confortable pour : Langfuse self-hosted + 2-3 missions concurrentes
- ✅ ~50% d'overhead disponible pour pics de charge

**Production / autonomie 24/7 : VPS-3**
- ✅ Multi-missions parallèles via meta_workflow asyncio.gather
- ✅ Marge pour : extensions futures (génération images, fine-tuning local Llama, etc.)

### Auto-détection du profil

Le script `deploy_vps.sh` détecte automatiquement le profil depuis la RAM disponible :
- ≤ 9 Go → `vps1`
- ≤ 14 Go → `vps2`
- > 14 Go → `vps3`

Le profil est stocké dans `.env` comme `VPS_PROFILE=vps1` (champ informatif pour les digests et le runbook).

---

## 2. Provisioning initial

### Prérequis sur le VPS

- **OS** : Ubuntu 22.04 LTS, 24.04 LTS, ou Debian 12
- **Accès** : root ou sudo
- **Réseau** : ports 22 (SSH) et 80/443 si reverse-proxy. Aucun port entrant requis pour le système lui-même (tout sortant).
- **Disque libre** : ≥ 5 Go (image sandbox + dépendances Python ≈ 1.5 Go, mémoire/skills minimes au démarrage)

### Lancement du script

**Méthode 1 — One-liner depuis GitHub** :

```bash
sudo bash <(curl -sSL https://raw.githubusercontent.com/MikaelArth/IA-Expert-Army/main/scripts/deploy_vps.sh)
```

**Méthode 2 — Repo cloné localement** :

```bash
sudo bash scripts/deploy_vps.sh
```

**Méthode 3 — Avec options** :

```bash
sudo bash scripts/deploy_vps.sh \
    --vps-profile vps2 \
    --install-dir /home/me/ia-expert-army \
    --skip-sandbox  # si VPS sans Docker, ENABLE_SANDBOX=false dans .env
```

### Ce que fait le script

1. **apt update + paquets système** : git, curl, build-essential, jq, htop, tmux
2. **Docker + compose** : install officiel depuis le PPA Docker
3. **User dédié `iaa-army`** : non-root, ajouté au groupe `docker`
4. **uv (Astral)** : package manager Python ultra-rapide
5. **Clone repo** dans `/opt/ia-expert-army`
6. **`.env` minimal** copié depuis `.env.example`, avec `VPS_PROFILE` patché
7. **`uv sync`** : installe toutes les dépendances Python
8. **Build sandbox** : image Docker `iaa-sandbox:latest` (~3 min)

### Idempotence

Le script peut être ré-exécuté sans casser une install existante. Chaque étape vérifie l'état actuel avant action :
- Docker déjà installé → skip
- User existe → skip
- Repo cloné → `git pull --ff-only`
- `.env` présent → non modifié

---

## 3. Configuration du `.env`

Après `deploy_vps.sh`, édite `/opt/ia-expert-army/.env` :

```bash
sudo -u iaa-army nano /opt/ia-expert-army/.env
```

### Champs OBLIGATOIRES — Ollama doit tourner sur le VPS

```bash
# Installer Ollama sur le VPS (https://ollama.com/install.sh)
curl -fsSL https://ollama.com/install.sh | sh

# Pull les 3 modèles par défaut (~50 Go disque + RAM)
# ATTENTION : qwen2.5:32b nécessite ~24 Go RAM. Sur vps1 (8 Go), basculer
# sur qwen2.5:14b (strategic) + qwen2.5-coder:7b (operational) + llama3.2:3b (bulk).
ollama pull qwen2.5:32b
ollama pull qwen2.5-coder:32b
ollama pull qwen2.5:14b

# Vérifier
ollama list
```

Puis dans `.env` (les défauts conviennent si tu as pullé les 3 modèles ci-dessus) :

```bash
OLLAMA_BASE_URL=http://localhost:11434/v1
MODEL_STRATEGIC=qwen2.5:32b
MODEL_OPERATIONAL=qwen2.5-coder:32b
MODEL_BULK=qwen2.5:14b
```

**Sécurité** : par défaut Ollama bind `127.0.0.1:11434` (pas exposé hors localhost). NE PAS publier ce port sur l'extérieur sans reverse proxy + auth, sinon n'importe qui sur Internet utilise ton GPU.

### Champs RECOMMANDÉS pour autonomie sûre

```bash
# Plafond budget journalier (USD) — défaut 50, à ajuster
DAILY_BUDGET_USD=20.0

# Active Quality Guardian (peer review méta) — coût ~$0.10-0.20/mission
ENABLE_QUALITY_GUARDIAN=true

# Active Security Auditor (OWASP/secrets) — coût ~$0.05-0.10/mission Eng
ENABLE_SECURITY_AUDITOR=true

# Profile VPS (informatif pour les digests)
VPS_PROFILE=vps1
```

### Champs OPTIONNELS

```bash
# Sandbox : laisser à true par défaut. False = pas de validation pytest.
ENABLE_SANDBOX=true

# Langfuse self-hosted (si installé séparément, voir docker-compose.yml)
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...

# Langfuse Cloud (alternative gratuite jusqu'à 1k traces/mois)
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-cloud-...
LANGFUSE_SECRET_KEY=sk-lf-cloud-...
```

---

## 4. Vérifications post-installation

### Health check complet

```bash
sudo -u iaa-army bash -lc "cd /opt/ia-expert-army && uv run python scripts/health_check.py"
```

Attendu : 6/6 verts (config, modèles, Docker daemon, image sandbox, mémoire, dépendances Python).

### Smoke test (~$0.03)

```bash
sudo -u iaa-army bash -lc "cd /opt/ia-expert-army && uv run python scripts/hello_agent.py"
```

Le Chief Orchestrator se présente. Coût ~$0.03.

### Mission live boucle fermée (~$0.50)

```bash
sudo -u iaa-army bash -lc "cd /opt/ia-expert-army && uv run python scripts/run_mission.py \
    --title 'Endpoint /uptime' \
    --description 'Crée un endpoint FastAPI GET /uptime qui retourne {seconds: float} via time.monotonic. Inclus tests pytest.' \
    --apply --validate"
```

Attendu : `APPROVED`, score ≥ 0.85, `pytest passed` dans le sandbox.

---

## 5. Migration VPS → VPS

Le système accumule de la valeur (mémoire, skills, épisodes). Quand tu changes de VPS, **ne perds rien** via `migrate_vps.sh`.

### Export depuis le VPS source

```bash
sudo -u iaa-army bash /opt/ia-expert-army/scripts/migrate_vps.sh export /tmp/iaa-snapshot.tar.gz
```

Ce qui est inclus :
- `data/memory/` (épisodes, missions, meta-missions)
- `data/chroma/` (vector DB pour RAG)
- `data/budget.json` + `data/error_log.json`
- `data/approvals/` (HITL pending/decided)
- `skills/` (skills auto-extraites)
- `prompts/` (au cas où tu aurais customisé)
- `.env` (credentials + tunings)

Manifest JSON inclus : checksums sha256 + git commit + timestamp source.

### Transfert

```bash
# Depuis ta machine locale (la plus simple)
scp source-vps:/tmp/iaa-snapshot.tar.gz dest-vps:/tmp/

# Ou via rsync (resume sur connexion fragile)
rsync -avz --progress source-vps:/tmp/iaa-snapshot.tar.gz dest-vps:/tmp/
```

### Import sur le VPS destination

```bash
# Le VPS dest doit déjà avoir tourné deploy_vps.sh
sudo -u iaa-army bash /opt/ia-expert-army/scripts/migrate_vps.sh import /tmp/iaa-snapshot.tar.gz
```

Garanties :
1. **Verify automatique** : checksums sha256 vérifiés. Refus si altéré.
2. **Backup pré-migration** : l'état actuel du VPS dest est sauvegardé dans `data/.pre-migrate-backup-YYYYMMDD-HHMMSS/`. Rollback trivial.
3. **Killswitch pendant import** : pas d'écriture concurrente.
4. **Permissions** : `chown iaa-army:iaa-army` + `.env` à 600.

### Vérification post-import

```bash
# Le digest journalier doit montrer les missions importées
sudo -u iaa-army bash -lc "cd /opt/ia-expert-army && uv run python scripts/daily_digest.py"

# Health check toujours vert
sudo -u iaa-army bash -lc "cd /opt/ia-expert-army && uv run python scripts/health_check.py"
```

### Rollback en cas de problème

```bash
# Stop tout traitement en cours
sudo -u iaa-army touch /opt/ia-expert-army/data/.killswitch_engaged

# Restore l'ancien état
BACKUP_DIR=$(ls -1d /opt/ia-expert-army/data/.pre-migrate-backup-* | tail -1)
for p in data/memory data/chroma data/budget.json data/error_log.json data/approvals skills prompts; do
    rm -rf "/opt/ia-expert-army/$p"
    cp -a "$BACKUP_DIR/$p" "/opt/ia-expert-army/$p" 2>/dev/null
done

# Lève le killswitch
sudo -u iaa-army rm -f /opt/ia-expert-army/data/.killswitch_engaged
```

---

## 6. Mode service (systemd, optionnel)

Pour lancer le mode autonome au boot ou via `systemctl`, créer `/etc/systemd/system/iaa-army.service` :

```ini
[Unit]
Description=IA-Expert-Army autonomous worker
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=iaa-army
WorkingDirectory=/opt/ia-expert-army
ExecStart=/home/iaa-army/.local/bin/uv run python scripts/autonomous_run.py
Restart=on-failure
RestartSec=30
# Stop = engage le killswitch (graceful)
ExecStop=/usr/bin/touch /opt/ia-expert-army/data/.killswitch_engaged
# Limites de ressources (selon profil VPS)
MemoryHigh=4G          # vps1=4G, vps2=8G, vps3=16G
MemoryMax=6G

[Install]
WantedBy=multi-user.target
```

Activation :

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now iaa-army
sudo systemctl status iaa-army
sudo journalctl -u iaa-army -f
```

---

## 7. Sécurité (production)

### Pare-feu

```bash
sudo ufw allow 22/tcp
sudo ufw enable
```

Le système n'expose **aucun port entrant** par défaut. Tout est sortant (Anthropic API, GitHub si auto-update). Pas besoin d'ouvrir 80/443 sauf si reverse-proxy.

### SSH

- Désactiver login root direct (`PermitRootLogin no` dans `/etc/ssh/sshd_config`)
- Forcer auth par clé (`PasswordAuthentication no`)
- fail2ban actif

### Backups réguliers

Cron quotidien (en plus du backup atomique avant chaque mission) :

```bash
# crontab -e (en tant que root)
0 3 * * * /usr/bin/sudo -u iaa-army /opt/ia-expert-army/scripts/migrate_vps.sh export /home/iaa-army/backups/iaa-$(date +\%Y\%m\%d).tar.gz
0 4 * * * /usr/bin/find /home/iaa-army/backups/ -name "iaa-*.tar.gz" -mtime +14 -delete
```

### Secrets

- `.env` toujours en mode 600 (rwx user only)
- Ne jamais committer `.env` (gitignored par défaut)
- Rotation périodique de la clé Anthropic (console > API keys)

---

## 8. Monitoring & observabilité

### Daily digest (gratuit, intégré)

```bash
sudo -u iaa-army bash -lc "cd /opt/ia-expert-army && uv run python scripts/daily_digest.py"
```

Affiche : missions du jour, coût, verdicts, QG concerns, approvals pending.

### Langfuse self-hosted (VPS-2+)

```bash
# Démarrage stack Langfuse + Postgres + ClickHouse + Redis
cd /opt/ia-expert-army
docker compose --profile langfuse up -d

# Accès : http://VOTRE-VPS:3000
# Récupère les keys Public + Secret dans .env
```

Mémoire requise : ~3 Go (PG + ClickHouse + Redis + Langfuse worker).

### Langfuse Cloud (alternative gratuite)

1. Crée un compte sur [cloud.langfuse.com](https://cloud.langfuse.com)
2. Crée un projet
3. Récupère les keys (Public + Secret)
4. Édite `.env` :

```bash
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-cloud-...
LANGFUSE_SECRET_KEY=sk-lf-cloud-...
```

Limite gratuite : 1000 traces/mois (~30 missions APPROVED/jour).

---

## 9. Troubleshooting

| Problème | Cause probable | Fix |
|---|---|---|
| `uv: command not found` après deploy | Path pas chargé pour iaa-army | `sudo -u iaa-army bash -lc 'source ~/.bashrc'` |
| Sandbox build hang à 3 min | RAM insuffisante (VPS < 4 Go) | `--skip-sandbox` + `ENABLE_SANDBOX=false` |
| `health_check.py` → Docker daemon down | Service docker pas démarré | `sudo systemctl start docker` |
| Mission `--validate` skip silencieux | `ENABLE_SANDBOX=false` ou Docker absent | Vérifier `.env` + `systemctl status docker` |
| Budget atteint refus mission | Plafond `DAILY_BUDGET_USD` atteint | Augmenter dans `.env` ou attendre reset minuit UTC |
| Killswitch engagé après crash | Process tué pendant un import/export | `rm /opt/ia-expert-army/data/.killswitch_engaged` |

Voir [`docs/runbook.md`](runbook.md) pour les incidents complexes (corruption mémoire, désynchro chroma, etc.).

---

## 10. ADRs liés

- [ADR-003 — Mode autonome avec garde-fous](adr/003-autonomy-with-guardrails.md) — les 10 garde-fous obligatoires
- [ADR-013 — Backup et disaster recovery](adr/013-backup-and-disaster-recovery.md) — stratégie backup atomique
- [ADR-016 — Tier mixing (Opus/Sonnet/Haiku)](adr/016-tier-mixing-strategy.md) — économie via choix de modèle
- [ADR-017 — Déploiement VPS (multi-profile)](adr/017-vps-deployment.md) — décisions de packaging
