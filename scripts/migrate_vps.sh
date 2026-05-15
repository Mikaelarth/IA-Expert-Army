#!/usr/bin/env bash
# ============================================================================
# migrate_vps.sh — Export/import de l'état IA-Expert-Army entre VPS
# ============================================================================
# Sprint GGG.3 — migration VPS-1 → VPS-2 → VPS-3 sans perte de mémoire/skills.
#
# L'état "mémoire vivante" du système comprend :
#   - data/memory/             — épisodes, missions, meta-missions, skills
#   - data/chroma/             — vector DB (RAG sémantique)
#   - data/budget.json         — état budget journalier
#   - data/error_log.json      — historique erreurs
#   - data/approvals/          — HITL approvals pending/decided
#   - skills/                  — skills auto-extraites par le PatternMiner
#   - prompts/                 — prompts versionnés (utile si modifs locales)
#   - .env                     — credentials Anthropic + Langfuse + tunings
#
# Usage typique :
#
#   # Sur VPS source :
#   sudo -u iaa-army bash scripts/migrate_vps.sh export /tmp/iaa-snapshot.tar.gz
#
#   # Transfert (depuis ta machine ou un VPS vers l'autre) :
#   scp source-vps:/tmp/iaa-snapshot.tar.gz dest-vps:/tmp/
#
#   # Sur VPS destination (après deploy_vps.sh) :
#   sudo -u iaa-army bash scripts/migrate_vps.sh import /tmp/iaa-snapshot.tar.gz
#
# Le script garantit :
#   - Snapshot atomique (kill-switch déclenché pendant l'export, levé après)
#   - Manifest JSON inclus avec checksums + git commit + version
#   - Validation à l'import : refuse si checksums divergent
#   - Backup de l'état destination avant overwrite (rollback possible)
#
# ============================================================================

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/ia-expert-army}"
ACTION="${1:-help}"
ARCHIVE="${2:-}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[migrate]${NC} $*"; }
ok()   { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*" >&2; }
err()  { echo -e "${RED}[err]${NC} $*" >&2; }

# Lecture d'un champ scalaire dans un JSON. Préfère jq, fallback python3.
# Refactor Sprint HHH.1 : jq est absent de certains VPS minimaux et de Git Bash
# (Windows dev). Python3 est garanti présent (installé par deploy_vps.sh).
json_get() {
    local file="$1" key="$2"
    if command -v jq &>/dev/null; then
        jq -r ".${key}" "$file"
    else
        python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$file" "$key"
    fi
}

json_pretty() {
    local file="$1"
    if command -v jq &>/dev/null; then
        jq . "$file"
    else
        python3 -c "import json,sys; print(json.dumps(json.load(open(sys.argv[1])), indent=2))" "$file"
    fi
}

# Conversion bytes → human-readable (KiB/MiB/GiB). Fallback si numfmt absent.
human_size() {
    local bytes="$1"
    if command -v numfmt &>/dev/null; then
        numfmt --to=iec --suffix=B "$bytes"
    else
        # Fallback python3 — toujours dispo
        python3 -c "
b = $bytes
for unit in ('B','KiB','MiB','GiB','TiB'):
    if b < 1024:
        print(f'{b:.1f}{unit}'); break
    b /= 1024
"
    fi
}

usage() {
    cat <<EOF
Usage : $0 <action> [archive]

Actions :
  export <archive.tar.gz>   Crée un snapshot atomique de l'état système
  import <archive.tar.gz>   Restore un snapshot (avec backup de l'existant)
  verify <archive.tar.gz>   Vérifie l'intégrité d'un snapshot (checksums)
  list-content <archive>    Liste le contenu d'un snapshot sans le restaurer

Variables :
  INSTALL_DIR=$INSTALL_DIR  Racine de l'install (par défaut /opt/ia-expert-army)

Exemples :
  $0 export /tmp/iaa-snapshot.tar.gz
  $0 import /tmp/iaa-snapshot.tar.gz
  $0 verify /tmp/iaa-snapshot.tar.gz
EOF
}

check_install_dir() {
    if [[ ! -d "$INSTALL_DIR" ]]; then
        err "INSTALL_DIR introuvable : $INSTALL_DIR"
        err "Lance d'abord scripts/deploy_vps.sh sur le VPS destination."
        exit 1
    fi
}

# ============================================================================
# EXPORT
# ============================================================================
do_export() {
    if [[ -z "$ARCHIVE" ]]; then err "Manque le chemin de l'archive."; usage; exit 1; fi
    check_install_dir

    log "Export depuis $INSTALL_DIR vers $ARCHIVE…"

    # Kill-switch pendant l'export pour cohérence (aucune écriture concurrente)
    KS_FILE="$INSTALL_DIR/data/.killswitch_engaged"
    KS_WAS_ENGAGED=false
    if [[ -f "$KS_FILE" ]]; then
        KS_WAS_ENGAGED=true
        log "Killswitch déjà engagé (laissé en place)"
    else
        log "Engagement du killswitch (cohérence snapshot)…"
        touch "$KS_FILE"
    fi

    # Petit sleep pour laisser une mission en cours finir son tour
    sleep 2

    TMPDIR=$(mktemp -d)
    SNAPSHOT="$TMPDIR/snapshot"
    mkdir -p "$SNAPSHOT"

    # Liste des chemins à inclure (relatifs à $INSTALL_DIR)
    PATHS_TO_BACKUP=(
        "data/memory"
        "data/chroma"
        "data/budget.json"
        "data/error_log.json"
        "data/approvals"
        "skills"
        "prompts"
        ".env"
    )

    log "Copie des artefacts…"
    for p in "${PATHS_TO_BACKUP[@]}"; do
        SRC="$INSTALL_DIR/$p"
        if [[ -e "$SRC" ]]; then
            mkdir -p "$SNAPSHOT/$(dirname "$p")"
            cp -a "$SRC" "$SNAPSHOT/$p"
            ok "  $p"
        else
            warn "  $p absent (skip)"
        fi
    done

    # Manifest JSON avec checksums + métadonnées
    # Sprint HHH.1 — Bugfix : génération via python3 pour escape correct des
    # paths Windows (`C:\Users\...`) qui cassaient le JSON parsing en bash.
    log "Génération du manifest…"
    cd "$SNAPSHOT"
    GIT_COMMIT=$(cd "$INSTALL_DIR" && git rev-parse HEAD 2>/dev/null || echo "unknown")
    HOSTNAME_SRC=$(hostname)
    NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # Checksums sha256 — Sprint HHH.1 : génération via python3 pour
    # déterminisme cross-OS. `sha256sum` sur Git Bash Windows hashe
    # différemment selon mode texte/binaire et convertit CRLF→LF, ce qui
    # cassait le verify après tar+extract. Python3 hashe toujours en binaire
    # exact byte-for-byte.
    python3 -c "
import hashlib, os, sys
out = []
for root, _, files in os.walk('.'):
    for fname in sorted(files):
        if fname == 'manifest.json':
            continue
        path = os.path.join(root, fname)
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        # Format compatible sha256sum -c : '<hash>  <path>' (2 espaces, mode binaire)
        rel = os.path.relpath(path, '.').replace(os.sep, '/')
        out.append(f'{h.hexdigest()}  ./{rel}')
with open('checksums.sha256', 'w', newline='\n') as f:
    f.write('\n'.join(out) + '\n')
"

    N_FILES=$(wc -l < checksums.sha256 | tr -d ' ')
    TOTAL_BYTES=$(du -sb . 2>/dev/null | awk '{print $1}')
    if [[ -z "$TOTAL_BYTES" ]]; then
        # Fallback portable (BSD du n'a pas -b ; on somme via python)
        TOTAL_BYTES=$(python3 -c "
import os, sys
total = 0
for root, _, files in os.walk('.'):
    for f in files:
        try: total += os.path.getsize(os.path.join(root, f))
        except OSError: pass
print(total)
")
    fi

    # Génération JSON via python3 (escape natif des paths Windows)
    PATHS_JSON=$(python3 -c "
import json, sys
paths = sys.argv[1:]
print(json.dumps(paths))
" "${PATHS_TO_BACKUP[@]}")

    python3 -c "
import json, sys
manifest = {
    'schema_version': '1',
    'created_at': sys.argv[1],
    'source_hostname': sys.argv[2],
    'source_install_dir': sys.argv[3],
    'source_git_commit': sys.argv[4],
    'n_files': int(sys.argv[5]),
    'total_bytes': int(sys.argv[6]),
    'checksums_file': 'checksums.sha256',
    'paths_included': json.loads(sys.argv[7]),
}
with open('manifest.json', 'w') as f:
    json.dump(manifest, f, indent=2)
" "$NOW" "$HOSTNAME_SRC" "$INSTALL_DIR" "$GIT_COMMIT" "$N_FILES" "$TOTAL_BYTES" "$PATHS_JSON"

    ok "Manifest généré ($N_FILES fichiers, $(human_size "$TOTAL_BYTES"))"

    # Tar avec compression
    # Sprint HHH.1 — Bugfix : --force-local empêche tar d'interpréter les
    # paths Windows comme `host:path` rcp-style (ex: C:\Users\... → essaie SSH
    # vers host "C", erreur "Cannot connect to C: resolve failed").
    log "Compression…"
    cd "$TMPDIR"
    tar --force-local -czf "$ARCHIVE" -C "$SNAPSHOT" .

    ARCHIVE_SIZE=$(du -h "$ARCHIVE" | cut -f1)
    ok "Archive créée : $ARCHIVE ($ARCHIVE_SIZE)"

    # Lève le killswitch si on l'a posé nous-mêmes
    if [[ "$KS_WAS_ENGAGED" == "false" ]]; then
        rm -f "$KS_FILE"
        log "Killswitch levé"
    fi

    rm -rf "$TMPDIR"

    cat <<EOF

${GREEN}✅  Export complet${NC}

Transfert vers le VPS destination :
   ${BLUE}scp $ARCHIVE user@dest-vps:/tmp/${NC}
   # OU via rsync :
   ${BLUE}rsync -avz $ARCHIVE user@dest-vps:/tmp/${NC}

Sur le VPS destination :
   ${BLUE}sudo -u iaa-army bash scripts/migrate_vps.sh import $ARCHIVE${NC}

EOF
}

# ============================================================================
# VERIFY
# ============================================================================
do_verify() {
    if [[ -z "$ARCHIVE" ]]; then err "Manque le chemin de l'archive."; usage; exit 1; fi
    if [[ ! -f "$ARCHIVE" ]]; then err "Archive introuvable : $ARCHIVE"; exit 1; fi

    log "Vérification de $ARCHIVE…"
    TMPDIR=$(mktemp -d)
    tar --force-local -xzf "$ARCHIVE" -C "$TMPDIR"

    if [[ ! -f "$TMPDIR/manifest.json" ]]; then
        err "Manifest manquant — archive corrompue ou pas générée par migrate_vps.sh"
        rm -rf "$TMPDIR"; exit 2
    fi
    if [[ ! -f "$TMPDIR/checksums.sha256" ]]; then
        err "checksums.sha256 manquant"
        rm -rf "$TMPDIR"; exit 2
    fi

    log "Métadonnées :"
    json_pretty "$TMPDIR/manifest.json"

    log "Vérification des checksums…"
    cd "$TMPDIR"
    # Sprint HHH.1 — Vérification via python3 pour symétrie avec la génération
    # (cf. comment dans do_export). sha256sum -c divergeait sur Windows à cause
    # du mode texte/binaire.
    if python3 -c "
import hashlib, os, sys
ok = True
with open('checksums.sha256') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            expected, path = line.split('  ', 1)
        except ValueError:
            print(f'BAD LINE: {line}', file=sys.stderr); ok = False; continue
        if not os.path.exists(path):
            print(f'MISSING: {path}', file=sys.stderr); ok = False; continue
        h = hashlib.sha256()
        with open(path, 'rb') as fp:
            for chunk in iter(lambda: fp.read(8192), b''):
                h.update(chunk)
        if h.hexdigest() != expected:
            print(f'MISMATCH: {path}', file=sys.stderr)
            print(f'  expected={expected}', file=sys.stderr)
            print(f'  got     ={h.hexdigest()}', file=sys.stderr)
            ok = False
sys.exit(0 if ok else 1)
"; then
        ok "Checksums valides"
    else
        err "❌ Checksums divergent — archive altérée"
        rm -rf "$TMPDIR"; exit 3
    fi
    rm -rf "$TMPDIR"
    ok "Archive valide ✅"
}

# ============================================================================
# LIST CONTENT
# ============================================================================
do_list() {
    if [[ -z "$ARCHIVE" ]]; then err "Manque le chemin de l'archive."; usage; exit 1; fi
    if [[ ! -f "$ARCHIVE" ]]; then err "Archive introuvable : $ARCHIVE"; exit 1; fi
    log "Contenu de $ARCHIVE :"
    tar --force-local -tzf "$ARCHIVE" | head -50
    n=$(tar --force-local -tzf "$ARCHIVE" | wc -l)
    log "Total : $n entrées"
}

# ============================================================================
# IMPORT
# ============================================================================
do_import() {
    if [[ -z "$ARCHIVE" ]]; then err "Manque le chemin de l'archive."; usage; exit 1; fi
    if [[ ! -f "$ARCHIVE" ]]; then err "Archive introuvable : $ARCHIVE"; exit 1; fi
    check_install_dir

    log "Vérification du snapshot avant import…"
    do_verify  # exit non-0 si invalide

    # Backup de l'état actuel avant overwrite (rollback possible)
    BACKUP_DIR="$INSTALL_DIR/data/.pre-migrate-backup-$(date +%Y%m%d-%H%M%S)"
    log "Backup de l'état actuel → $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    for p in data/memory data/chroma data/budget.json data/error_log.json \
             data/approvals skills prompts; do
        if [[ -e "$INSTALL_DIR/$p" ]]; then
            mkdir -p "$BACKUP_DIR/$(dirname "$p")"
            cp -a "$INSTALL_DIR/$p" "$BACKUP_DIR/$p"
        fi
    done
    ok "Backup créé ($(du -sh "$BACKUP_DIR" | cut -f1))"

    # Engagement du killswitch pendant l'import
    KS_FILE="$INSTALL_DIR/data/.killswitch_engaged"
    KS_WAS_ENGAGED=false
    if [[ -f "$KS_FILE" ]]; then
        KS_WAS_ENGAGED=true
    else
        touch "$KS_FILE"
    fi

    log "Extraction…"
    TMPDIR=$(mktemp -d)
    tar --force-local -xzf "$ARCHIVE" -C "$TMPDIR"

    log "Restauration des artefacts dans $INSTALL_DIR…"
    for p in data/memory data/chroma data/budget.json data/error_log.json \
             data/approvals skills prompts .env; do
        SRC="$TMPDIR/$p"
        DST="$INSTALL_DIR/$p"
        if [[ -e "$SRC" ]]; then
            # Pour les répertoires : remove + replace (cohérence)
            if [[ -d "$SRC" ]]; then
                rm -rf "$DST"
                mkdir -p "$(dirname "$DST")"
                cp -a "$SRC" "$DST"
            else
                cp -a "$SRC" "$DST"
            fi
            ok "  $p restauré"
        else
            warn "  $p absent du snapshot (skip)"
        fi
    done

    # Permissions cohérentes pour l'user iaa-army
    if id iaa-army &>/dev/null; then
        chown -R iaa-army:iaa-army "$INSTALL_DIR/data" "$INSTALL_DIR/skills" \
            "$INSTALL_DIR/prompts" "$INSTALL_DIR/.env" 2>/dev/null || true
    fi

    # Permissions strictes pour .env
    chmod 600 "$INSTALL_DIR/.env" 2>/dev/null || true

    rm -rf "$TMPDIR"

    # Lève le killswitch
    if [[ "$KS_WAS_ENGAGED" == "false" ]]; then
        rm -f "$KS_FILE"
        log "Killswitch levé"
    else
        warn "Killswitch laissé engagé (était déjà actif avant migration)"
    fi

    cat <<EOF

${GREEN}✅  Import complet${NC}

État restauré depuis : $ARCHIVE
Backup pré-migration : $BACKUP_DIR

${YELLOW}🔍  Vérifications recommandées :${NC}

  1. Health check :
     ${BLUE}cd $INSTALL_DIR && uv run python scripts/health_check.py${NC}

  2. Daily digest (vérifie que les missions sont visibles) :
     ${BLUE}cd $INSTALL_DIR && uv run python scripts/daily_digest.py${NC}

  3. Smoke test :
     ${BLUE}cd $INSTALL_DIR && uv run python scripts/hello_agent.py${NC}

${YELLOW}🔄  Rollback si besoin :${NC}

  ${BLUE}# Stop tout, puis :
  for p in data/memory data/chroma data/budget.json data/error_log.json data/approvals skills prompts; do
    rm -rf $INSTALL_DIR/\$p
    cp -a $BACKUP_DIR/\$p $INSTALL_DIR/\$p 2>/dev/null
  done${NC}

EOF
}

# ============================================================================
# Dispatch
# ============================================================================
case "$ACTION" in
    export)        do_export ;;
    import)        do_import ;;
    verify)        do_verify ;;
    list-content)  do_list ;;
    help|-h|--help|"") usage ;;
    *) err "Action inconnue : $ACTION"; usage; exit 1 ;;
esac
