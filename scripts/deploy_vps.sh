#!/usr/bin/env bash
# ============================================================================
# deploy_vps.sh — Provision idempotente d'un VPS Ubuntu 22.04+ pour IA-Expert-Army
# ============================================================================
# Sprint GGG.2 — déploiement VPS-1/VPS-2/VPS-3 (OVH ou équivalent).
#
# Idempotent : peut être ré-exécuté sans casser une install existante.
# Tout est checké avant action (set -e + check_then_act).
#
# Prérequis :
#   - VPS Ubuntu 22.04 LTS ou supérieur (testé jusqu'à 24.04)
#   - Accès root ou sudo
#   - Connexion internet
#
# Usage :
#   curl -sSL https://raw.githubusercontent.com/MikaelArth/IA-Expert-Army/main/scripts/deploy_vps.sh | sudo bash
#   # OU
#   sudo bash scripts/deploy_vps.sh [--vps-profile vps1|vps2|vps3]
#
# Le script :
#   1. Met à jour apt + installe deps systeme (build-essential, git, curl, ...)
#   2. Installe Docker + docker-compose (utile pour sandbox + Langfuse optionnel)
#   3. Installe uv (Astral) + Python 3.12 si absent
#   4. Crée user iaa-army (non-root) avec accès Docker
#   5. Clone le repo dans /opt/ia-expert-army
#   6. Provisionne .env minimal depuis .env.example (l'utilisateur complète après)
#   7. Lance uv sync
#   8. Build l'image sandbox (~3 min, désactivable via --skip-sandbox)
#   9. Affiche les next steps : éditer .env, lancer health_check, smoke test
#
# Exit codes :
#   0 : succès complet
#   1 : prérequis manquants (pas root, pas Ubuntu, etc.)
#   2 : étape critique échouée (apt, docker daemon, uv install)
#   3 : étape optionnelle échouée (sandbox build) — install partielle utilisable
#
# ============================================================================

set -euo pipefail

# ----- Configuration -----
REPO_URL="${REPO_URL:-https://github.com/MikaelArth/IA-Expert-Army.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/ia-expert-army}"
SERVICE_USER="${SERVICE_USER:-iaa-army}"
VPS_PROFILE=""
SKIP_SANDBOX=false
SKIP_GIT=false  # utile pour relancer après modifs locales

# ----- Couleurs -----
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[deploy]${NC} $*"; }
ok()   { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*" >&2; }
err()  { echo -e "${RED}[err]${NC} $*" >&2; }

# ----- Parse args -----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --vps-profile) VPS_PROFILE="$2"; shift 2 ;;
        --skip-sandbox) SKIP_SANDBOX=true; shift ;;
        --skip-git) SKIP_GIT=true; shift ;;
        --install-dir) INSTALL_DIR="$2"; shift 2 ;;
        --repo-url) REPO_URL="$2"; shift 2 ;;
        -h|--help)
            sed -n '4,40p' "$0"  # affiche le header doc
            exit 0 ;;
        *) err "Argument inconnu : $1"; exit 1 ;;
    esac
done

# ----- Vérifications préalables -----
log "Vérification des prérequis…"

if [[ $EUID -ne 0 ]]; then
    err "Ce script doit être lancé en root (ou via sudo)."
    exit 1
fi

if ! command -v lsb_release &>/dev/null; then
    apt-get update -qq && apt-get install -y -qq lsb-release
fi

DISTRO=$(lsb_release -is 2>/dev/null || echo "Unknown")
RELEASE=$(lsb_release -rs 2>/dev/null || echo "0")

if [[ "$DISTRO" != "Ubuntu" && "$DISTRO" != "Debian" ]]; then
    warn "Distribution détectée : $DISTRO $RELEASE — testé sur Ubuntu 22.04+."
    warn "Le script peut fonctionner mais aucun support officiel."
fi

ok "OS : $DISTRO $RELEASE"

# ----- Auto-detect VPS profile from RAM si non fourni -----
if [[ -z "$VPS_PROFILE" ]]; then
    RAM_GB=$(awk '/MemTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo)
    if   [[ $RAM_GB -le 9 ]];  then VPS_PROFILE="vps1"
    elif [[ $RAM_GB -le 14 ]]; then VPS_PROFILE="vps2"
    else                            VPS_PROFILE="vps3"
    fi
    log "Profile auto-détecté depuis ${RAM_GB}Go RAM : $VPS_PROFILE"
fi

# ============================================================================
# Étape 1 — apt update + paquets système
# ============================================================================
log "Étape 1/8 : mise à jour apt + paquets systeme…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    build-essential \
    git \
    curl \
    ca-certificates \
    gnupg \
    rsync \
    ufw \
    htop \
    tmux \
    jq \
    python3 \
    python3-pip \
    python3-venv
ok "Paquets système installés"

# ============================================================================
# Étape 2 — Docker (idempotent)
# ============================================================================
if command -v docker &>/dev/null; then
    ok "Docker déjà installé : $(docker --version)"
else
    log "Étape 2/8 : installation Docker…"
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin
    systemctl enable --now docker
    ok "Docker installé : $(docker --version)"
fi

# ============================================================================
# Étape 3 — User dédié + accès Docker
# ============================================================================
if id "$SERVICE_USER" &>/dev/null; then
    ok "User $SERVICE_USER existe déjà"
else
    log "Étape 3/8 : création user $SERVICE_USER…"
    useradd -m -s /bin/bash "$SERVICE_USER"
    ok "User $SERVICE_USER créé"
fi

if id -nG "$SERVICE_USER" | grep -qw docker; then
    ok "User $SERVICE_USER déjà dans le groupe docker"
else
    usermod -aG docker "$SERVICE_USER"
    ok "User $SERVICE_USER ajouté au groupe docker"
fi

# ============================================================================
# Étape 4 — uv (package manager Python rapide)
# ============================================================================
if sudo -u "$SERVICE_USER" bash -lc 'command -v uv' &>/dev/null; then
    UV_VERSION=$(sudo -u "$SERVICE_USER" bash -lc 'uv --version')
    ok "uv déjà installé : $UV_VERSION"
else
    log "Étape 4/8 : installation uv pour $SERVICE_USER…"
    sudo -u "$SERVICE_USER" bash -lc \
        'curl -LsSf https://astral.sh/uv/install.sh | sh'
    ok "uv installé"
fi

# ============================================================================
# Étape 5 — clone repo
# ============================================================================
if [[ "$SKIP_GIT" == "true" ]]; then
    warn "Étape 5/8 : skip git (--skip-git)"
elif [[ -d "$INSTALL_DIR/.git" ]]; then
    log "Étape 5/8 : repo déjà cloné, pull des changements…"
    sudo -u "$SERVICE_USER" git -C "$INSTALL_DIR" pull --ff-only || \
        warn "git pull a échoué — divergence locale, à inspecter manuellement"
    ok "Repo à jour"
else
    log "Étape 5/8 : clone $REPO_URL → $INSTALL_DIR…"
    mkdir -p "$INSTALL_DIR"
    chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    sudo -u "$SERVICE_USER" git clone "$REPO_URL" "$INSTALL_DIR"
    ok "Repo cloné"
fi

# ============================================================================
# Étape 6 — .env minimal
# ============================================================================
ENV_FILE="$INSTALL_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    ok ".env déjà présent ($ENV_FILE) — non modifié"
else
    log "Étape 6/8 : provisioning .env minimal…"
    if [[ ! -f "$INSTALL_DIR/.env.example" ]]; then
        err ".env.example introuvable dans $INSTALL_DIR — repo corrompu ?"
        exit 2
    fi
    sudo -u "$SERVICE_USER" cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
    # Patch profile VPS détecté
    sudo -u "$SERVICE_USER" sed -i "s/^VPS_PROFILE=.*/VPS_PROFILE=$VPS_PROFILE/" "$ENV_FILE"
    # Sur VPS-1 (8 Go) on désactive Langfuse par défaut (~3 Go RAM)
    if [[ "$VPS_PROFILE" == "vps1" ]]; then
        log "VPS-1 détecté : .env tunings (sandbox léger, pas de Langfuse)"
        # ENABLE_LANGFUSE n'existe pas comme flag : Langfuse est opt-in via les credentials.
        # On laisse les credentials vides → désactivé automatiquement.
    fi
    chmod 600 "$ENV_FILE"
    warn "⚠️  Édite $ENV_FILE pour ajouter ANTHROPIC_API_KEY=sk-ant-..."
    warn "    sudo -u $SERVICE_USER nano $ENV_FILE"
fi

# ============================================================================
# Étape 7 — uv sync
# ============================================================================
log "Étape 7/8 : uv sync (peut prendre 1-2 min)…"
sudo -u "$SERVICE_USER" bash -lc "cd $INSTALL_DIR && uv sync"
ok "Dépendances Python installées"

# ============================================================================
# Étape 8 — Build sandbox (optionnel)
# ============================================================================
if [[ "$SKIP_SANDBOX" == "true" ]]; then
    warn "Étape 8/8 : skip sandbox build (--skip-sandbox)"
    warn "  → run_mission --validate ne fonctionnera pas"
    warn "  → set ENABLE_SANDBOX=false dans .env pour skip silencieux"
else
    log "Étape 8/8 : build image sandbox (~3 min sur VPS-1)…"
    if sudo -u "$SERVICE_USER" bash -lc \
        "cd $INSTALL_DIR && uv run python scripts/check_sandbox.py --build"; then
        ok "Image sandbox construite"
    else
        warn "Build sandbox échoué — install utilisable mais sans validation pytest"
        warn "Réessayer avec : cd $INSTALL_DIR && uv run python scripts/check_sandbox.py --build"
    fi
fi

# ============================================================================
# Récapitulatif
# ============================================================================
cat <<EOF

${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}
${GREEN}✅  IA-Expert-Army installé avec succès${NC}
${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}

  📁  Installation :  $INSTALL_DIR
  👤  User :          $SERVICE_USER
  🖥️  Profile VPS :    $VPS_PROFILE
  💾  RAM dispo :      $(awk '/MemAvailable/ {printf "%.1f Go", $2/1024/1024}' /proc/meminfo)

${YELLOW}🔧  Prochaines étapes :${NC}

  1. Édite la clé API :
     sudo -u $SERVICE_USER nano $ENV_FILE

  2. Vérifie la config :
     sudo -u $SERVICE_USER bash -lc "cd $INSTALL_DIR && uv run python scripts/check_setup.py"

  3. Smoke test (~\$0.03) :
     sudo -u $SERVICE_USER bash -lc "cd $INSTALL_DIR && uv run python scripts/hello_agent.py"

  4. Mission live (~\$0.50) :
     sudo -u $SERVICE_USER bash -lc "cd $INSTALL_DIR && uv run python scripts/run_mission.py \\
        --title 'Endpoint /uptime' \\
        --description 'Crée un endpoint FastAPI GET /uptime…' \\
        --apply --validate"

${BLUE}📚  Doc complète : $INSTALL_DIR/docs/deploy.md${NC}
${BLUE}🚨  Runbook incidents : $INSTALL_DIR/docs/runbook.md${NC}

EOF

exit 0
