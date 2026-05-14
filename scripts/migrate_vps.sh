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
    log "Génération du manifest…"
    cd "$SNAPSHOT"
    GIT_COMMIT=$(cd "$INSTALL_DIR" && git rev-parse HEAD 2>/dev/null || echo "unknown")
    HOSTNAME_SRC=$(hostname)
    NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # Checksums sha256 de tous les fichiers
    find . -type f -not -name 'manifest.json' -print0 | \
        xargs -0 sha256sum > checksums.sha256

    cat > manifest.json <<EOF
{
  "schema_version": "1",
  "created_at": "$NOW",
  "source_hostname": "$HOSTNAME_SRC",
  "source_install_dir": "$INSTALL_DIR",
  "source_git_commit": "$GIT_COMMIT",
  "n_files": $(wc -l < checksums.sha256),
  "total_bytes": $(du -sb . | awk '{print $1}'),
  "checksums_file": "checksums.sha256",
  "paths_included": [$(printf '"%s",' "${PATHS_TO_BACKUP[@]}" | sed 's/,$//')]
}
EOF
    ok "Manifest généré ($(jq -r '.n_files' manifest.json) fichiers, $(numfmt --to=iec --suffix=B "$(jq -r '.total_bytes' manifest.json)"))"

    # Tar avec compression
    log "Compression…"
    cd "$TMPDIR"
    tar -czf "$ARCHIVE" -C "$SNAPSHOT" .

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
    tar -xzf "$ARCHIVE" -C "$TMPDIR"

    if [[ ! -f "$TMPDIR/manifest.json" ]]; then
        err "Manifest manquant — archive corrompue ou pas générée par migrate_vps.sh"
        rm -rf "$TMPDIR"; exit 2
    fi
    if [[ ! -f "$TMPDIR/checksums.sha256" ]]; then
        err "checksums.sha256 manquant"
        rm -rf "$TMPDIR"; exit 2
    fi

    log "Métadonnées :"
    jq . "$TMPDIR/manifest.json"

    log "Vérification des checksums…"
    cd "$TMPDIR"
    if sha256sum -c checksums.sha256 --quiet; then
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
    tar -tzf "$ARCHIVE" | head -50
    n=$(tar -tzf "$ARCHIVE" | wc -l)
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
    tar -xzf "$ARCHIVE" -C "$TMPDIR"

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
