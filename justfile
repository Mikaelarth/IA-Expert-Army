# IA-Expert-Army — raccourcis cross-platform via just (https://just.systems)
# Installation : `cargo install just`  ou  `winget install Casey.Just`
# Usage : `just`, `just test`, `just health`, etc.

# Liste les recettes disponibles (recette par défaut)
default:
    @just --list

# === Setup ===

# Installe / met à jour les dépendances Python (Phase 0 + dev)
sync:
    uv sync

# Vérifie l'environnement (Python, deps, .env, dossiers data/)
check:
    uv run python scripts/check_setup.py

# Health check global (toutes les couches : Python → Sandbox → Langfuse)
health:
    uv run python scripts/health_check.py

# Health check rapide (skip les checks Docker)
health-quick:
    uv run python scripts/health_check.py --quick

# === Tests ===

# Lance la suite complète
test:
    uv run pytest tests/unit/

# Lance la suite avec couverture
test-cov:
    uv run pytest tests/unit/ --cov=src --cov-report=term-missing

# Lance UN test précis (usage: just test-one tests/unit/test_x.py::test_y)
test-one PATTERN:
    uv run pytest {{PATTERN}} -v

# Smoke test : premier appel Claude (~$0.03)
hello:
    uv run python scripts/hello_agent.py

# === Missions ===

# Lance une mission interactive (prompt pour titre + description)
mission:
    uv run python scripts/run_mission.py --interactive

# Mining nightly : extrait les skills depuis les épisodes APPROVED
mine:
    uv run python scripts/nightly_learning.py

# Mining dry-run : montre ce qui serait miné sans appeler Claude
mine-dry:
    uv run python scripts/nightly_learning.py --dry-run

# Re-applique une mission archivée + valide en sandbox
apply MISSION_ID:
    uv run python scripts/apply_mission.py {{MISSION_ID}} --validate-only

# === Garde-fous ===

# Statut budget journalier
budget:
    uv run python scripts/budget.py status

# Reset budget journalier à 0
budget-reset:
    uv run python scripts/budget.py reset

# Daily digest (rapport markdown du jour)
digest:
    uv run python scripts/daily_digest.py

# Killswitch : engage / status / release
killswitch ACTION="status":
    uv run python scripts/killswitch.py {{ACTION}}

# === Sandbox ===

# Vérifie le sandbox Docker + smoke test
sandbox:
    uv run python scripts/check_sandbox.py

# Build l'image sandbox (~3 min première fois)
sandbox-build:
    uv run python scripts/check_sandbox.py --build

# === Observabilité ===

# Démarre la stack Langfuse self-hosted (postgres + clickhouse + minio + redis + worker + web)
langfuse-up:
    docker compose --profile observability up -d

# Stop la stack Langfuse
langfuse-down:
    docker compose --profile observability down

# Logs du web Langfuse
langfuse-logs:
    docker logs iaa-langfuse-web --tail 30

# === Lint / Format ===

# Lint avec ruff
lint:
    uv run ruff check src/ scripts/ tests/

# Auto-fix les erreurs ruff
lint-fix:
    uv run ruff check --fix src/ scripts/ tests/

# Format avec ruff
fmt:
    uv run ruff format src/ scripts/ tests/

# Typecheck (mypy non-strict, dette tracée dans CHANGELOG)
typecheck:
    uv run mypy src/

# === Git ===

# Statut + dernier commit
status:
    git status --short
    @echo "---"
    git log --oneline -1

# Compte les commits depuis le début
commits:
    git log --oneline | wc -l
