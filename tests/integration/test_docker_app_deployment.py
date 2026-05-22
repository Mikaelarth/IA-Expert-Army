"""Tests d'invariants statiques sur le Dockerfile app + docker-compose.

Ne lance PAS de vrai build (lourd, nécessite Docker). Valide juste que :
- Les fichiers existent et sont parsables (Dockerfile syntaxe basique, YAML).
- Les ports / volumes / env vars critiques sont configurés correctement.
- Les chemins référencés dans Dockerfile existent dans le repo.

Pour un vrai test de build, lancer manuellement :
    docker compose --profile app build
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DOCKERFILE = REPO_ROOT / "infra" / "docker" / "app.Dockerfile"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"


# ---------------------------------------------------------------------------
# Dockerfile app
# ---------------------------------------------------------------------------


def test_app_dockerfile_exists() -> None:
    assert APP_DOCKERFILE.exists(), f"Dockerfile app manquant : {APP_DOCKERFILE}"


def test_app_dockerfile_has_python_base() -> None:
    content = APP_DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM python:" in content, "Pas de base Python détectée"


def test_app_dockerfile_exposes_streamlit_port() -> None:
    content = APP_DOCKERFILE.read_text(encoding="utf-8")
    assert "EXPOSE 8501" in content, "Le port Streamlit 8501 n'est pas exposé"


def test_app_dockerfile_binds_0_0_0_0_by_default() -> None:
    """Le CMD doit explicitement bind sur 0.0.0.0 (sinon Streamlit fait 127.0.0.1
    et le port mapping Docker ne fonctionne pas correctement)."""
    content = APP_DOCKERFILE.read_text(encoding="utf-8")
    assert "--server.address" in content, "Pas de --server.address dans CMD"
    assert "0.0.0.0" in content, "Le binding 0.0.0.0 manque dans CMD"  # noqa: S104


def test_app_dockerfile_uses_non_root_user() -> None:
    """Défense en profondeur : le container ne doit PAS tourner en root."""
    content = APP_DOCKERFILE.read_text(encoding="utf-8")
    assert "USER iaa" in content, "Le container devrait passer en user non-root 'iaa'"


def test_app_dockerfile_has_healthcheck() -> None:
    content = APP_DOCKERFILE.read_text(encoding="utf-8")
    assert "HEALTHCHECK" in content, "Pas de HEALTHCHECK déclaré"
    assert "_stcore/health" in content, "Healthcheck doit interroger l'endpoint Streamlit"


def test_app_dockerfile_copies_required_directories() -> None:
    """Les répertoires critiques (src/, prompts/, templates/, skills/) doivent
    être COPY dans l'image runtime."""
    content = APP_DOCKERFILE.read_text(encoding="utf-8")
    for required in ["COPY src", "COPY scripts", "COPY prompts", "COPY templates"]:
        assert required in content, f"COPY manquant : {required}"


# ---------------------------------------------------------------------------
# docker-compose.yml — service app
# ---------------------------------------------------------------------------


@pytest.fixture
def compose_config() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def test_compose_has_app_service(compose_config: dict) -> None:
    services = compose_config.get("services", {})
    assert "app" in services, "Service 'app' manquant dans docker-compose.yml"


def test_compose_app_uses_app_dockerfile(compose_config: dict) -> None:
    app = compose_config["services"]["app"]
    build = app.get("build", {})
    assert build.get("dockerfile") == "infra/docker/app.Dockerfile"


def test_compose_app_in_app_profile(compose_config: dict) -> None:
    """Le service app doit être dans le profile 'app' pour ne pas démarrer
    par défaut quand on fait `docker compose up` sans flag."""
    app = compose_config["services"]["app"]
    assert "app" in app.get("profiles", []), "Service app devrait être dans profile 'app'"


def test_compose_app_exposes_streamlit_port(compose_config: dict) -> None:
    app = compose_config["services"]["app"]
    ports = app.get("ports", [])
    assert any("8501" in str(p) for p in ports), "Port 8501 non exposé"


def test_compose_app_has_ollama_env_for_host_resolution(compose_config: dict) -> None:
    """L'app doit pouvoir résoudre Ollama sur le host via OLLAMA_BASE_URL
    par défaut pointant sur host.docker.internal."""
    app = compose_config["services"]["app"]
    env = app.get("environment", {})
    # Soit dict, soit liste de "KEY=VALUE"
    if isinstance(env, dict):
        ollama_url = env.get("OLLAMA_BASE_URL", "")
    else:
        ollama_url = next((e.split("=", 1)[1] for e in env if e.startswith("OLLAMA_BASE_URL=")), "")
    assert "host.docker.internal" in ollama_url or "${OLLAMA_BASE_URL" in ollama_url


def test_compose_app_has_extra_hosts_for_linux(compose_config: dict) -> None:
    """`host.docker.internal` doit être résolu via add_hosts sur Linux."""
    app = compose_config["services"]["app"]
    extra = app.get("extra_hosts", [])
    assert any("host.docker.internal" in str(h) for h in extra), (
        "extra_hosts: doit contenir host.docker.internal:host-gateway pour Linux"
    )


def test_compose_app_mounts_data_volume(compose_config: dict) -> None:
    """data/ doit être monté en volume pour persister entre restarts."""
    app = compose_config["services"]["app"]
    volumes = app.get("volumes", [])
    assert any(":/app/data" in str(v) for v in volumes), "Volume data/ manquant"


def test_compose_app_disables_sandbox_by_default(compose_config: dict) -> None:
    """Sécurité : pas d'accès Docker socket par défaut → sandbox désactivé."""
    app = compose_config["services"]["app"]
    env = app.get("environment", {})
    if isinstance(env, dict):
        enable_sandbox = env.get("ENABLE_SANDBOX", "")
    else:
        enable_sandbox = next(
            (e.split("=", 1)[1] for e in env if e.startswith("ENABLE_SANDBOX=")), ""
        )
    # Soit littéralement "false", soit interpolation ${ENABLE_SANDBOX:-false}
    assert "false" in str(enable_sandbox).lower()


def test_compose_app_has_healthcheck(compose_config: dict) -> None:
    app = compose_config["services"]["app"]
    assert "healthcheck" in app, "Service app devrait avoir un healthcheck"
    test_cmd = app["healthcheck"].get("test", [])
    assert any("_stcore/health" in str(t) for t in test_cmd)


# ---------------------------------------------------------------------------
# run_gui.py — binding host configurable
# ---------------------------------------------------------------------------


def test_run_gui_respects_streamlit_bind_host_env() -> None:
    """run_gui.py doit lire STREAMLIT_BIND_HOST et l'utiliser comme
    --server.address. Validation par lecture du source (pas d'execution)."""
    script = REPO_ROOT / "scripts" / "run_gui.py"
    content = script.read_text(encoding="utf-8")
    assert "STREAMLIT_BIND_HOST" in content, "Variable d'env STREAMLIT_BIND_HOST absente"
    assert "DEFAULT_HOST" in content, "Doit définir un DEFAULT_HOST (127.0.0.1)"
    assert '"127.0.0.1"' in content, "Le défaut doit être 127.0.0.1 pour rétrocompat"


# ---------------------------------------------------------------------------
# Documentation
# ---------------------------------------------------------------------------


def test_deploy_lan_doc_exists() -> None:
    """docs/deploy-lan.md doit exister et documenter le protocole LAN."""
    doc = REPO_ROOT / "docs" / "deploy-lan.md"
    assert doc.exists()
    content = doc.read_text(encoding="utf-8")
    # Sections critiques attendues
    for section in [
        "Mode LAN",
        "Migration vers VPS",
        "host.docker.internal",
        "Troubleshooting",
    ]:
        assert section in content, f"Section critique manquante dans deploy-lan.md : {section}"
