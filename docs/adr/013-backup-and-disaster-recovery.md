# ADR-013 — Backup atomique + Disaster Recovery

**Statut :** Accepted
**Date :** 2026-05-14
**Commits associés :** Sprint BBB

## Contexte

Audit de maturité (réponse user 2026-05-14, post-Sprint AAA) a identifié l'absence de **politique de backup/DR** comme axe critique manquant pour atteindre un niveau « pro et propre » niveau entreprise. Risques concrets :

- **Corruption Chroma** : déjà documentée dans le runbook (section 7) — recalculable via reindex, mais la procédure suppose que les épisodes markdown source sont intacts.
- **Suppression accidentelle** `rm -rf skills/` ou `data/memory/episodes/` : **PERTE TOTALE de l'apprentissage** accumulé (16 skills auto-générées, ~120 épisodes au moment de v0.2.0).
- **Disque mort / OS crash** : aucune mécanique de récupération hors restauration manuelle depuis Git (qui ne contient PAS `skills/` ni `data/memory/` — cf. `.gitignore`).

Avant Sprint BBB, le seul backup implicite était l'historique Git sur les fichiers tracés (code, prompts, ADRs). Mais :
- `data/memory/` est **gitignored** (épisodes auto-générés ne polluent pas l'histoire Git).
- `skills/` également (volume potentiel + bruit dans le diff).
- Aucun mécanisme automatique ni testé.

## Décision

Module `src/core/backup.py` + 2 scripts CLI (`backup.py` / `restore.py`) qui implémentent :

### Sources backupées (par défaut)

```
skills/                   ← apprentissage continu (CRITIQUE)
data/memory/              ← épisodes + missions + meta_missions (CRITIQUE)
prompts/                  ← system prompts agents
docs/                     ← ADRs + architecture + runbook
pyproject.toml            ← deps + version + ruff/mypy config
uv.lock                   ← reproductibilité exacte
justfile                  ← raccourcis ops
.pre-commit-config.yaml   ← politique de qualité code
README.md / CHANGELOG.md / CONTRIBUTING.md / LICENSE
```

### Sources EXCLUSES (intentionnel)

| Source | Raison de l'exclusion |
|---|---|
| `.env` | Secrets — l'utilisateur backup ailleurs (password manager / vault) |
| `data/chroma/` | INDEX recalculable via `scripts/reindex_episodes.py` à partir des épisodes (source de vérité) |
| `data/budget_state.json` | Volatile (rotation quotidienne) — la perte = budget repart à 0 |
| `data/autonomous_runs/` | Rapports horodatés, garde-fou non critique |
| `.venv/`, `__pycache__/`, `*.pyc` | Recréés par `uv sync` |

### Atomicité

- Écriture dans `<archive>.zip.tmp` puis `os.replace()` atomique vers `<archive>.zip`.
- Si crash en cours de backup → le `.tmp` reste, le `.zip` ne contient JAMAIS de données partielles.

### Manifest embarqué

Chaque backup contient un `manifest.json` à la racine du ZIP :

```json
{
  "created_at": "2026-05-14T15:30:00+00:00",
  "git_commit": "abc1234",
  "iaa_version": "0.2.0",
  "files_included": [...],
  "total_size_bytes": 1234567,
  "excluded_paths": [".env (secrets)", ...]
}
```

Le manifest permet de retrouver le bon backup (date + commit + version) sans avoir à le dézipper.

### Rotation LRU

Politique par défaut : **garde les 7 plus récents**, suppression LRU (Least Recently Used) basée sur mtime. Configurable via `--keep N`.

### Sécurité restore

- **Refuse l'overwrite par défaut** : si un fichier existe déjà à destination, il est SKIPPED. L'utilisateur doit explicitement `--overwrite` pour écraser.
- **Protection path traversal** : un ZIP malicieux contenant `../../etc/evil.txt` est rejeté (compte comme `failed`, pas restauré).
- **Confirmation interactive** : `restore.py` demande confirmation explicite avant tout overwrite, sauf `--yes`.

### Procédure d'urgence (cf. runbook section 10)

```powershell
just killswitch engage              # 1. STOP
just backup                         # 2. Snapshot l'état corrompu
just restore-latest                 # 3. Restore (interactive)
# Si conflits :
uv run python scripts/restore.py --latest --overwrite
uv run python scripts/reindex_episodes.py  # 4. Rebuild Chroma
just health                         # 5. Sanity
just killswitch release             # 6. Reprendre
```

## Conséquences

**Positives :**
- Risque de perte catastrophique de l'apprentissage **éliminé** (sous condition que `just backup` tourne régulièrement).
- Procédure de restauration **testée à l'unité** (18 tests pytest) — pas un "espérons que ça marche".
- L'archive est **portable** (un seul ZIP, ouvrable avec n'importe quel outil).
- Le manifest permet le **debugging post-mortem** : "depuis quelle version de IAA ce backup a-t-il été pris ?"

**Négatives / à surveiller :**
- **Le backup doit être lancé** — sans cron / Task Scheduler, l'utilisateur peut oublier. Recommandation forte d'ajouter une entrée cron quotidienne ou une étape dans `autonomous_run.py`.
- **Le `.env` n'est PAS backupé** — l'utilisateur doit gérer ses secrets séparément. C'est une décision sécurité (pas de credentials dans un ZIP qui pourrait se balader), mais c'est aussi un risque si la machine meurt avec le `.env` non-sauvegardé ailleurs.
- **Le test de restauration n'est PAS automatisé** : un backup peut être corrompu silencieusement (ZIP valide mais contenu incomplet). À tester manuellement 1× par trimestre via `just restore-from <backup> --target /tmp/test`.
- **Pas de chiffrement at-rest** : les `.zip` sont en clair. Si l'archive contient des skills qui exposent des patterns de prompt sensibles, c'est exploitable. v2 possible : `--encrypt` avec passphrase.

## Alternatives considérées

- **Tout pousser dans Git** (un-gitignorer `data/memory/`) : rejeté. Volume potentiel énorme (~120 épisodes × ~5KB = 600KB aujourd'hui, mais croît). Bruit insupportable dans `git log`. Mieux : Git pour le code, backup ZIP pour les données.
- **DVC (Data Version Control)** : reporté. Plus puissant que ZIP (deduplication, remote storage S3/MinIO), mais overhead d'installation/config disproportionné pour une équipe d'un. À reconsidérer si on passe multi-utilisateur.
- **Snapshot filesystem (ZFS, btrfs)** : rejeté (cross-platform — l'utilisateur est sur Windows + WSL ambigu).
- **Backup différentiel (rsync-like)** : rejeté pour v1. Le full-ZIP est suffisant à cette échelle (< 5MB par backup actuel). Différentiel ajouterait de la complexité (chaîne de backups, restauration en cascade).
- **Inclure `.env` dans le backup avec redaction des secrets** : rejeté. Redaction = fragile (regex peut louper un secret). Mieux : exclusion totale + l'utilisateur gère séparément.

## Pour la suite

- **Cron quotidien** : ajouter `just backup` dans une tâche planifiée Windows Task Scheduler / Linux cron. Quick win mais nécessite que l'utilisateur configure son OS.
- **Backup hook dans `autonomous_run.py`** : à la fin de chaque run autonome long (> 5 missions), trigger `create_backup()` automatique. Garantit qu'on a un backup post-run.
- **Test de restauration trimestriel** : ajouter un script `scripts/verify_backup.py` qui restore le dernier backup dans `/tmp/recovery_test/`, fait un `diff -r` avec project root, et alerte si différences > seuil.
- **Cloud storage** : option `--upload-to s3://...` ou intégration avec un bucket externe pour résilience matérielle (disque mort).
- **Chiffrement at-rest** : `--encrypt PASSPHRASE` qui passe l'archive dans `cryptography.fernet` avant écriture. Procédure de récupération si passphrase perdue : pas de récupération possible (c'est le but).
