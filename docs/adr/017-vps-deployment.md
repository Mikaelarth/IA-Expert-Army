# ADR-017 — Déploiement VPS multi-profile (vps1/vps2/vps3)

**Statut :** Accepted
**Date :** 2026-05-14
**Commits associés :** Sprint GGG

## Contexte

L'utilisateur (MikaelArth, solo) souhaite déployer IA-Expert-Army sur un VPS personnel pour :
1. Fonctionnement 24/7 indépendant de sa machine de dev (Windows)
2. Mode autonome sécurisé (autonomous_run + garde-fous)
3. Évolution progressive : démarre VPS-1 (5,52 €/mois), monte VPS-2 puis VPS-3 selon usage

Trois profiles cibles (OVH 2026-05) :

| Profile | RAM | NVMe | Prix/mois | Limite identifiée |
|---|---|---|---|---|
| VPS-1 | 8 Go | 75 Go | 5,52 € | Langfuse self-hosted serré (~3 Go) |
| VPS-2 | 12 Go | 100 Go | 8,49 € | Tout passe + 2-3 missions concurrentes |
| VPS-3 | 24 Go | 200 Go | 16,99 € | Multi-missions parallèles + extensions |

Problème central : **comment packager le système pour qu'un user solo puisse migrer entre VPS sans perdre la mémoire vivante (épisodes, skills, vector DB) ?**

Sous-problèmes :
1. Bootstrap d'un VPS neuf (idempotent, automatisé)
2. Adaptabilité de la config selon hardware (Langfuse activable ou non)
3. Migration sans perte (export/import atomique avec checksums)
4. Documentation opérationnelle complète (runbook + deploy guide)

## Décision

### 1. Script `deploy_vps.sh` idempotent

Un seul script bash exécutable sur Ubuntu 22.04+ ou Debian 12+ qui :
- Installe deps système, Docker, uv (Astral)
- Crée user dédié `iaa-army` (non-root, dans groupe docker)
- Clone le repo dans `/opt/ia-expert-army`
- Provisionne `.env` minimal depuis `.env.example` avec auto-détection du profil VPS depuis `/proc/meminfo`
- Lance `uv sync` + build image sandbox

**Idempotence garantie** : chaque étape vérifie l'état avant action (Docker installé ? user existe ? repo cloné ? `.env` présent ?). Réexécution = noop si tout est en place.

### 2. Settings adaptables (`Settings.enable_sandbox`, `Settings.vps_profile`)

Deux nouveaux champs :
- `enable_sandbox: bool = True` — kill-switch explicite pour court-circuiter `validate_files_in_sandbox` sans tenter Docker. Utile sur VPS sans Docker ou pour CI rapide.
- `vps_profile: Literal["", "vps1", "vps2", "vps3", "local"]` — informatif (digests/runbook). N'affecte pas la logique métier.

Langfuse reste **opt-in via les credentials vides** (pattern existant) — pas besoin d'un flag `enable_langfuse` séparé. Sur VPS-1, on laisse les credentials vides → Langfuse désactivé automatiquement, économie ~3 Go RAM.

### 3. Script `migrate_vps.sh` (export / import / verify / list-content)

Pattern snapshot/restore atomique :

```
# Source
sudo -u iaa-army bash scripts/migrate_vps.sh export /tmp/iaa-snapshot.tar.gz

# Transfert via scp/rsync

# Destination
sudo -u iaa-army bash scripts/migrate_vps.sh import /tmp/iaa-snapshot.tar.gz
```

**Garanties** :
- **Cohérence** : killswitch engagé pendant l'export (pas d'écriture concurrente)
- **Intégrité** : manifest JSON + checksums sha256 de tous les fichiers, vérifiés à l'import (refus si altéré)
- **Rollback** : backup automatique de l'état destination avant overwrite, dans `data/.pre-migrate-backup-YYYYMMDD-HHMMSS/`
- **Permissions** : `chown iaa-army`, `chmod 600 .env`

**Contenu du snapshot** :
- `data/memory/` (épisodes, missions, meta-missions, skills)
- `data/chroma/` (vector DB)
- `data/budget.json`, `data/error_log.json`, `data/approvals/`
- `skills/` (auto-extraites)
- `prompts/` (au cas où custom)
- `.env` (credentials + tunings)

### 4. Documentation : `docs/deploy.md` + section `docs/runbook.md`

`docs/deploy.md` couvre :
1. Choix VPS (tableau comparatif + critères usage)
2. Provisioning initial (one-liner curl, étapes manuelles)
3. Configuration `.env` (obligatoires, recommandés, optionnels)
4. Vérifications post-install (health check, smoke test, mission live)
5. Migration VPS → VPS
6. Mode service (systemd)
7. Sécurité (UFW, SSH, backups cron, secrets)
8. Monitoring (digest, Langfuse self-hosted vs cloud)
9. Troubleshooting (10 cas courants)

## Conséquences

**Positives** :
- User solo peut déployer en 5 min sur VPS neuf
- Migration VPS-1 → VPS-2 → VPS-3 transparente, sans perte de mémoire vivante
- `enable_sandbox=False` permet d'opérer dégradé sur VPS très contraint (sans Docker)
- Auto-détection du profil → defaults sensés sans config manuelle

**Négatives** :
- Le script `deploy_vps.sh` n'est testé que sur Ubuntu 22.04 (pas de CI multi-OS pour l'instant)
- Pas de support Alpine/CentOS/Fedora (apt-only)
- L'import `migrate_vps.sh` ne valide pas la compatibilité de schéma entre versions du repo (si VPS source en v0.2 et VPS dest en v0.3, peut casser silencieusement) — à adresser dans un Sprint futur via versioning du schéma data/

**À surveiller** :
- Docker buildx + compose plugin : nouvelles deps depuis 2024, vérifier qu'OVH Ubuntu 22.04 a bien le PPA `download.docker.com` accessible
- Build sandbox sur VPS-1 (4 vCores) : ~3 min mesuré localement, à valider en condition réelle
- Taille snapshot après 3-6 mois d'usage : surtout `data/chroma/` qui croît avec les épisodes. Si > 500 Mo, prévoir rsync incrémental (pas tar.gz monolithique)

## Alternatives considérées

1. **Docker compose tout-en-un + image officielle publiée** : refusé pour cette phase. Plus complexe à maintenir, moins flexible pour debug. Reportable à v0.5+ quand le système stabilisé.

2. **Ansible playbook** : refusé. Sur-tooling pour un user solo. Bash idempotent suffit. Si plusieurs users le déploient, on basculera sur Ansible.

3. **Backup quotidien automatique sur S3/B2** : reporté à un Sprint futur. Le crontab local + `migrate_vps.sh` couvre 80% du besoin sans dépendance cloud externe.

4. **Migration "live" sans downtime (master-master ou rsync continu)** : refusé. Le système n'est pas designed pour multi-instance. Le killswitch + snapshot est la bonne primitive.

5. **Provisioning Terraform OVH** : refusé pour la phase solo. Trop d'overhead. Si l'utilisateur passe à du multi-VPS, on reverra.

## Suivi

À surveiller sur les 3 premiers déploiements VPS-1 réels :
- Temps total `deploy_vps.sh` (cible : ≤ 15 min sur VPS-1 4 vCores)
- Taille du snapshot après 1 semaine d'usage (cible : ≤ 50 Mo)
- Temps `migrate_vps.sh export` puis `import` (cible : ≤ 2 min chacun)
- Aucune perte de mémoire post-migration

Si une de ces métriques dérape, ouvrir un Sprint correctif.

## Sources

- OVH VPS pricing 2026-05 (vérifié via WebFetch sur ovh.com)
- ADR-013 (backup atomique) — réutilise le même pattern (manifest + checksums)
- Pattern killswitch existant (`Killswitch` class dans `src/core/killswitch.py`)
- Anthropic SDK retry behavior (laisse 2 retries auto, timeout 300s)
