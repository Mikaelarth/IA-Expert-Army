"""Tests pour les helpers de validation sandbox dans scripts/apply_mission.py.

Le helper _validate_in_sandbox encapsule la création workspace temp + lancement
sandbox + cleanup. On le teste avec un SandboxRunner mocké pour ne pas
dépendre de Docker en CI."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Le script apply_mission.py vit sous scripts/ et n'est pas un module installé.
# On l'importe via importlib en injectant son répertoire dans sys.path.
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture
def apply_mission_module(monkeypatch: pytest.MonkeyPatch):
    """Charge dynamiquement apply_mission.py comme module."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        # Force reload pour repartir de zéro
        if "apply_mission" in sys.modules:
            del sys.modules["apply_mission"]
        module = importlib.import_module("apply_mission")
        yield module
    finally:
        if str(SCRIPTS_DIR) in sys.path:
            sys.path.remove(str(SCRIPTS_DIR))


def _file(path: str, content: str = "x = 1\n") -> dict[str, str]:
    return {"path": path, "content": content, "language": "python"}


def test_validate_in_sandbox_returns_none_when_runner_unavailable(
    apply_mission_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si SandboxRunner lève SandboxUnavailable → retour None (pas de crash)."""
    from src.sandbox.runner import SandboxUnavailable

    def _raises(**kwargs):
        raise SandboxUnavailable("docker daemon down")

    monkeypatch.setattr(apply_mission_module, "SandboxRunner", _raises)

    result = apply_mission_module._validate_in_sandbox(
        files=[_file("src/foo.py")],
        sandbox_image="iaa-sandbox:latest",
        sandbox_timeout=10,
    )
    assert result is None


def test_validate_in_sandbox_returns_none_when_image_missing(
    apply_mission_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_runner = MagicMock()
    fake_runner.image_exists.return_value = False
    monkeypatch.setattr(apply_mission_module, "SandboxRunner", lambda **kw: fake_runner)

    result = apply_mission_module._validate_in_sandbox(
        files=[_file("src/foo.py")],
        sandbox_image="iaa-sandbox:latest",
        sandbox_timeout=10,
    )
    assert result is None


def test_validate_in_sandbox_writes_files_and_runs_pytest(
    apply_mission_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le helper doit créer les fichiers dans un workspace temp et appeler runner.run()."""
    from src.sandbox.runner import SandboxResult

    fake_result = SandboxResult(
        exit_code=0,
        stdout="9 passed",
        stderr="",
        duration_seconds=0.5,
        timed_out=False,
        image="iaa-sandbox:latest",
        command=["pytest", "-v", "--tb=short"],
    )
    fake_runner = MagicMock()
    fake_runner.image_exists.return_value = True
    fake_runner.run.return_value = fake_result
    monkeypatch.setattr(apply_mission_module, "SandboxRunner", lambda **kw: fake_runner)

    captured_workspace = {}

    def _capture_run(workspace, command):
        captured_workspace["path"] = Path(workspace)
        # Vérifie que les fichiers sont bien là pendant le run
        assert (Path(workspace) / "src" / "foo.py").exists()
        assert (Path(workspace) / "tests" / "test_foo.py").exists()
        assert (Path(workspace) / "conftest.py").exists()
        return fake_result

    fake_runner.run.side_effect = _capture_run

    result = apply_mission_module._validate_in_sandbox(
        files=[
            _file("src/foo.py", "def hello(): return 'world'\n"),
            _file("tests/test_foo.py", "from src.foo import hello\n\ndef test_hello(): assert hello() == 'world'\n"),
        ],
        sandbox_image="iaa-sandbox:latest",
        sandbox_timeout=30,
    )

    assert result is fake_result
    assert result.exit_code == 0
    fake_runner.run.assert_called_once()
    # Le workspace temp doit avoir été nettoyé
    assert not captured_workspace["path"].exists()


def test_validate_in_sandbox_skips_files_without_path(
    apply_mission_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.sandbox.runner import SandboxResult

    fake_result = SandboxResult(
        exit_code=0, stdout="", stderr="", duration_seconds=0.1,
        timed_out=False, image="iaa-sandbox:latest", command=["pytest"],
    )
    fake_runner = MagicMock()
    fake_runner.image_exists.return_value = True
    fake_runner.run.return_value = fake_result
    monkeypatch.setattr(apply_mission_module, "SandboxRunner", lambda **kw: fake_runner)

    # Mélange : un fichier valide + un sans path (à ignorer)
    result = apply_mission_module._validate_in_sandbox(
        files=[
            _file("src/ok.py"),
            {"path": "", "content": "garbage"},
            {"path": "  ", "content": "also garbage"},
        ],
        sandbox_image="iaa-sandbox:latest",
        sandbox_timeout=10,
    )
    # Le run a quand même eu lieu (pas crash)
    assert result is fake_result
    fake_runner.run.assert_called_once()


def test_validate_in_sandbox_creates_conftest_for_imports(
    apply_mission_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Régression : sans conftest.py qui ajoute le workspace au sys.path,
    `from src.x import y` échoue dans le sandbox."""
    from src.sandbox.runner import SandboxResult

    fake_result = SandboxResult(
        exit_code=0, stdout="", stderr="", duration_seconds=0.1,
        timed_out=False, image="iaa-sandbox:latest", command=["pytest"],
    )
    fake_runner = MagicMock()
    fake_runner.image_exists.return_value = True

    captured_conftest_content = {}

    def _check_conftest(workspace, command):
        conftest = Path(workspace) / "conftest.py"
        assert conftest.exists()
        captured_conftest_content["text"] = conftest.read_text(encoding="utf-8")
        return fake_result

    fake_runner.run.side_effect = _check_conftest
    monkeypatch.setattr(apply_mission_module, "SandboxRunner", lambda **kw: fake_runner)

    apply_mission_module._validate_in_sandbox(
        files=[_file("src/foo.py")],
        sandbox_image="iaa-sandbox:latest",
        sandbox_timeout=10,
    )

    assert "sys.path.insert" in captured_conftest_content["text"]


def test_validate_in_sandbox_preserves_user_conftest(
    apply_mission_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si l'utilisateur fournit son propre conftest.py, on ne l'écrase PAS."""
    from src.sandbox.runner import SandboxResult

    fake_result = SandboxResult(
        exit_code=0, stdout="", stderr="", duration_seconds=0.1,
        timed_out=False, image="iaa-sandbox:latest", command=["pytest"],
    )
    fake_runner = MagicMock()
    fake_runner.image_exists.return_value = True

    user_conftest = "# Mon conftest custom\nimport pytest\n"
    captured = {}

    def _check_conftest(workspace, command):
        conftest = Path(workspace) / "conftest.py"
        captured["text"] = conftest.read_text(encoding="utf-8")
        return fake_result

    fake_runner.run.side_effect = _check_conftest
    monkeypatch.setattr(apply_mission_module, "SandboxRunner", lambda **kw: fake_runner)

    apply_mission_module._validate_in_sandbox(
        files=[
            _file("src/foo.py"),
            {"path": "conftest.py", "content": user_conftest, "language": "python"},
        ],
        sandbox_image="iaa-sandbox:latest",
        sandbox_timeout=10,
    )

    assert captured["text"] == user_conftest
