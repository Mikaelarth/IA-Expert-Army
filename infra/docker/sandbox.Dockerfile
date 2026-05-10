# IA-Expert-Army Sandbox — image isolée pour exécuter le code généré par les agents.
#
# Build :
#   docker build -t iaa-sandbox:latest -f infra/docker/sandbox.Dockerfile infra/docker
#
# Usage (via SandboxRunner) :
#   - Le workspace est monté en lecture seule sur /workspace
#   - L'utilisateur runtime est `nobody` (pas de root)
#   - Réseau désactivé par défaut (network=none)
#   - Limites CPU/RAM imposées par docker-py au runtime
#
# Stack pré-installée (Phase 3) : pytest + ce qui est commun aux missions actuelles
# (FastAPI, httpx, pydantic). Élargir si une mission produit du code utilisant
# d'autres libs (ajouter dans cette image, rebuild).

FROM python:3.12-slim

# Installer les outils de test + libs courantes des agents
RUN pip install --no-cache-dir \
    pytest==9.0.3 \
    pytest-asyncio==1.3.0 \
    httpx==0.28.1 \
    fastapi==0.136.1 \
    pydantic==2.13.4 \
    && rm -rf /root/.cache/pip

# Workspace en lecture seule (mounté par le runner)
WORKDIR /workspace

# Pas de root au runtime
USER nobody:nogroup

# Par défaut : exécute pytest sur le workspace
CMD ["pytest", "-v", "--tb=short"]
