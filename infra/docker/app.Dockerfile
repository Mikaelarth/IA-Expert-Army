# IA-Expert-Army — App image (Streamlit GUI + dépendances complètes)
#
# Cette image héberge l'application principale (GUI + agents + RAG + A/B testing).
# Elle est conçue pour :
#   1. Tester l'app depuis un autre PC du LAN (binding 0.0.0.0)
#   2. Préparer un déploiement VPS futur (image reproductible)
#
# Build :
#   docker build -t iaa-app:latest -f infra/docker/app.Dockerfile .
#
# Run autonome (LAN) :
#   docker run -d --name iaa-app \
#     -p 8501:8501 \
#     -e OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 \
#     --add-host=host.docker.internal:host-gateway \
#     -v "$(pwd)/data:/app/data" \
#     -v "$(pwd)/skills:/app/skills" \
#     -v "$(pwd)/prompts:/app/prompts" \
#     -v "$(pwd)/templates:/app/templates" \
#     iaa-app:latest
#
# Via docker-compose (recommandé) :
#   docker compose --profile app up -d
#
# Cf. docs/deploy-lan.md pour le détail du protocole LAN + chemin VPS.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Dépendances système minimales :
# - curl/ca-certificates : santé + requêtes Ollama
# - tini : init PID 1 propre (handle SIGTERM)
# - git : utile pour `_get_git_commit` dans /version (sinon "unknown" sans crash)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        tini \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installation uv (cohérent avec dev workflow)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

# ----------------------------------------------------------------------------
# Stage deps : install dependencies en cache layer indépendant du code source
# (rebuilds rapides quand seul le code change, pas les deps)
# ----------------------------------------------------------------------------
FROM base AS deps

COPY pyproject.toml uv.lock README.md ./

# Pre-création de src/ pour que `uv sync` réussisse (le project est une lib)
RUN mkdir -p src && touch src/__init__.py

# Sync avec tous les groupes (gui pour streamlit, dev pas inclus en prod image)
RUN uv sync --frozen --all-extras --group gui --no-dev

# ----------------------------------------------------------------------------
# Stage runtime
# ----------------------------------------------------------------------------
FROM base AS runtime

# Copier l'environnement déjà installé
COPY --from=deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app

# Copier le code source (les volumes en runtime peuvent overrider data/, etc.)
COPY pyproject.toml uv.lock README.md .env.example ./
COPY src ./src
COPY scripts ./scripts
COPY prompts ./prompts
COPY templates ./templates
COPY skills ./skills

# Créer les répertoires runtime qui seront montés en volumes
RUN mkdir -p data/memory data/chroma data/checkpoints data/ab_tests data/approvals

# Utilisateur non-root pour la défense en profondeur
RUN useradd --create-home --shell /bin/bash iaa && \
    chown -R iaa:iaa /app
USER iaa

# Streamlit par défaut écoute 8501 ; on l'expose. La GUI est l'entrée principale.
EXPOSE 8501

# Healthcheck léger : Streamlit expose /_stcore/health (statut interne)
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

# Tini comme init pour gérer SIGTERM proprement (kill rapide au docker stop)
ENTRYPOINT ["/usr/bin/tini", "--"]

# CMD lance directement streamlit avec bind 0.0.0.0 pour LAN.
# Le paramètre est overridable depuis docker-compose ou docker run.
CMD ["streamlit", "run", "src/gui/app.py", \
     "--server.address", "0.0.0.0", \
     "--server.port", "8501", \
     "--server.headless", "true", \
     "--browser.gatherUsageStats", "false"]
