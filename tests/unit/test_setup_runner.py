"""Tests unitaires pour `src/gui/services/setup_runner.py` (ADR-027).

On ne touche ni au daemon Ollama réel ni à Docker — toutes les détections
"réseau" sont mockées via monkeypatch des helpers internes
(`urllib.request.urlopen`, `shutil.which`, etc.).

Les actions long-running (pull_model, build_sandbox_image, start_ollama_daemon)
ne sont pas exécutées : ce serait fragile (forker un subprocess, télécharger
des modèles…). On valide leur surface API (signatures, valeurs de retour
quand pré-conditions absentes) sans déclencher d'effet de bord réel.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.gui.services import setup_runner
from src.gui.services.setup_runner import (
    ComponentStatus,
    Status,
    create_env_from_example,
    detect_all,
    detect_env_file,
    detect_python,
    detect_uv,
    read_env_content,
    write_env_content,
)

# ---------------------------------------------------------------------------
# Détections triviales (pas de réseau, pas de subprocess)
# ---------------------------------------------------------------------------


def test_detect_python_returns_ok_on_current_runtime() -> None:
    """Python ≥ 3.12 est garanti par requires-python du projet, donc le check
    doit toujours retourner OK quand on lance les tests."""
    result = detect_python()
    assert result.status == Status.OK
    assert "3." in result.detail


def test_detect_uv_optional_returns_status_with_install_url_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si uv absent, on retourne MISSING + URL d'installation (non bloquant)."""
    monkeypatch.setattr(setup_runner.shutil, "which", lambda name: None)
    result = detect_uv()
    assert result.status == Status.MISSING
    assert result.install_url == setup_runner.URL_UV
    assert result.is_required is False


def test_detect_uv_returns_ok_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_runner.shutil, "which", lambda name: "/fake/path/uv")
    result = detect_uv()
    assert result.status == Status.OK
    assert "/fake/path/uv" in result.detail


# ---------------------------------------------------------------------------
# Détection Ollama daemon — mock urlopen
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_detect_ollama_daemon_ok_when_endpoint_responds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"models": [{"name": "qwen2.5:32b"}]}).encode("utf-8")

    def fake_urlopen(req, timeout):
        return _FakeResponse(payload)

    monkeypatch.setattr(setup_runner.urllib.request, "urlopen", fake_urlopen)
    result = setup_runner.detect_ollama_daemon()
    assert result.status == Status.OK
    assert "/api/tags" in result.detail


def test_detect_ollama_daemon_stopped_when_connection_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.error

    def fake_urlopen(req, timeout):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(setup_runner.urllib.request, "urlopen", fake_urlopen)
    result = setup_runner.detect_ollama_daemon()
    assert result.status == Status.STOPPED
    assert result.fix_action == "start_ollama"
    assert "Démarrer" in result.detail or "lance" in result.detail.lower()


# ---------------------------------------------------------------------------
# Détection des 3 modèles — mock `/api/tags` réponse
# ---------------------------------------------------------------------------


def test_detect_model_missing_when_not_in_api_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"models": [{"name": "llama3:8b"}, {"name": "mistral:7b"}]}).encode(
        "utf-8"
    )

    monkeypatch.setattr(
        setup_runner.urllib.request,
        "urlopen",
        lambda req, timeout: _FakeResponse(payload),
    )
    result = setup_runner.detect_model_strategic()
    assert result.status == Status.MISSING
    assert result.fix_action is not None
    assert result.fix_action.startswith("pull_model:")


def test_detect_model_ok_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import get_settings

    s = get_settings()
    payload = json.dumps(
        {"models": [{"name": s.model_strategic}, {"name": s.model_operational}]}
    ).encode("utf-8")

    monkeypatch.setattr(
        setup_runner.urllib.request,
        "urlopen",
        lambda req, timeout: _FakeResponse(payload),
    )
    result = setup_runner.detect_model_strategic()
    assert result.status == Status.OK


def test_detect_model_unknown_when_daemon_down(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    def fake_urlopen(req, timeout):
        raise urllib.error.URLError("nope")

    monkeypatch.setattr(setup_runner.urllib.request, "urlopen", fake_urlopen)
    result = setup_runner.detect_model_bulk()
    assert result.status == Status.UNKNOWN


# ---------------------------------------------------------------------------
# Docker — on vérifie le chemin "binaire absent" sans toucher au daemon
# ---------------------------------------------------------------------------


@pytest.fixture
def settings_with_sandbox():
    """Fixture qui restaure proprement Settings.enable_sandbox après le test.

    Contournement : `monkeypatch.setattr(settings, "enable_sandbox", X,
    raising=False)` se comporte mal avec Pydantic v2 BaseSettings — au teardown,
    le `delattr` peut laisser l'instance singleton sans valeur pour ce field,
    ce qui pollue les autres tests qui partagent `get_settings()` (lru_cache).

    Cette fixture sauvegarde explicitement la valeur originale et la restaure
    via setattr au teardown.
    """
    from src.core.config import get_settings

    settings = get_settings()
    original = settings.enable_sandbox

    def _set(value: bool) -> None:
        object.__setattr__(settings, "enable_sandbox", value)

    yield _set
    object.__setattr__(settings, "enable_sandbox", original)


def test_detect_docker_missing_when_no_binary(
    monkeypatch: pytest.MonkeyPatch, settings_with_sandbox
) -> None:
    # which("docker") = None  → MISSING (avec URL Docker Desktop)
    monkeypatch.setattr(
        setup_runner.shutil,
        "which",
        lambda name: None if name == "docker" else "/x/y",
    )
    # Forcer enable_sandbox=True pour que le check ne short-circuit pas en SKIPPED
    settings_with_sandbox(True)

    result = setup_runner.detect_docker()
    assert result.status == Status.MISSING
    assert result.install_url == setup_runner.URL_DOCKER
    assert result.is_required is False  # docker n'est jamais "bloquant"


def test_detect_docker_skipped_when_sandbox_disabled(settings_with_sandbox) -> None:
    settings_with_sandbox(False)
    result = setup_runner.detect_docker()
    assert result.status == Status.SKIPPED


# ---------------------------------------------------------------------------
# Détection .env + actions sur le fichier
# ---------------------------------------------------------------------------


def test_create_env_from_example_idempotent_when_already_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Redirige .env vers tmp_path (via patch project_root settings)
    from src.core import config

    s = config.get_settings()
    monkeypatch.setattr(type(s), "project_root", property(lambda self: tmp_path))

    (tmp_path / ".env.example").write_text("FOO=bar\n", encoding="utf-8")
    (tmp_path / ".env").write_text("FOO=existing\n", encoding="utf-8")

    result = create_env_from_example()
    assert result.success is True
    # Ne doit PAS écraser
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "FOO=existing\n"


def test_create_env_from_example_copies_when_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core import config

    s = config.get_settings()
    monkeypatch.setattr(type(s), "project_root", property(lambda self: tmp_path))

    (tmp_path / ".env.example").write_text("FOO=bar\n", encoding="utf-8")

    result = create_env_from_example()
    assert result.success is True
    assert (tmp_path / ".env").exists()
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "FOO=bar\n"


def test_read_write_env_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core import config

    s = config.get_settings()
    monkeypatch.setattr(type(s), "project_root", property(lambda self: tmp_path))

    content = "MODEL_STRATEGIC=qwen2.5:14b\nDAILY_BUDGET_USD=0.0\n"
    write_result = write_env_content(content)
    assert write_result.success is True

    # Read back
    assert read_env_content() == content


def test_detect_env_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core import config

    s = config.get_settings()
    monkeypatch.setattr(type(s), "project_root", property(lambda self: tmp_path))

    (tmp_path / ".env.example").write_text("FOO=bar\n", encoding="utf-8")

    result = detect_env_file()
    assert result.status == Status.MISSING
    assert result.fix_action == "create_env"


def test_detect_env_file_ok_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core import config

    s = config.get_settings()
    monkeypatch.setattr(type(s), "project_root", property(lambda self: tmp_path))

    (tmp_path / ".env").write_text("FOO=bar\n", encoding="utf-8")

    result = detect_env_file()
    assert result.status == Status.OK


# ---------------------------------------------------------------------------
# detect_all — smoke test, vérifie que la fonction retourne 10 composants
# sans lever d'exception même si tout est absent.
# ---------------------------------------------------------------------------


def test_detect_all_returns_ten_components_no_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """detect_all() ne doit JAMAIS lever, peu importe l'état de la machine."""
    # On laisse l'environnement réel (peut avoir Ollama up ou down) — le
    # _safe wrapper doit catcher tout ce qui plante.
    results = detect_all()
    assert len(results) == 10
    assert all(isinstance(r, ComponentStatus) for r in results)
    # Au moins le check Python doit être OK
    py = next(r for r in results if r.key == "python")
    assert py.status == Status.OK


# ---------------------------------------------------------------------------
# pull_model — mock urlopen pour vérifier le parsing du stream JSON ligne
# par ligne (sans lancer un vrai pull).
# ---------------------------------------------------------------------------


class _FakeStream:
    """Simule la réponse streaming `/api/pull` d'Ollama."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None


def test_pull_model_parses_streaming_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = [
        json.dumps({"status": "pulling manifest"}).encode("utf-8") + b"\n",
        json.dumps(
            {
                "status": "downloading",
                "digest": "sha256:abc",
                "completed": 500,
                "total": 1000,
            }
        ).encode("utf-8")
        + b"\n",
        json.dumps(
            {
                "status": "downloading",
                "digest": "sha256:abc",
                "completed": 1000,
                "total": 1000,
            }
        ).encode("utf-8")
        + b"\n",
        json.dumps({"status": "success"}).encode("utf-8") + b"\n",
    ]
    monkeypatch.setattr(
        setup_runner.urllib.request, "urlopen", lambda req, timeout: _FakeStream(lines)
    )

    events = list(setup_runner.pull_model("qwen2.5:14b"))
    assert len(events) == 4
    assert events[0].status == "pulling manifest"
    assert events[0].percent is None
    assert events[1].percent == 50.0
    assert events[2].percent == 100.0
    assert events[3].status == "success"


def test_pull_model_raises_when_daemon_down(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    def fake_urlopen(req, timeout):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(setup_runner.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="injoignable"):
        list(setup_runner.pull_model("qwen2.5:7b"))
