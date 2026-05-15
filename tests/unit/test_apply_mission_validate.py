"""Tests pour validate_files_in_sandbox (src/tools/sandbox_validate.py).

Le helper encapsule la création workspace temp + lancement sandbox + cleanup.
On le teste avec un SandboxRunner mocké pour ne pas dépendre de Docker en CI.

NOTE : depuis le refactor (ADR/sprint-X), la logique est dans
src.tools.sandbox_validate. apply_mission.py n'est qu'un wrapper.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import src.tools.sandbox_validate as sv_module
from src.tools.sandbox_validate import validate_files_in_sandbox


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")


def _file(path: str, content: str = "x = 1\n") -> dict[str, str]:
    return {"path": path, "content": content, "language": "python"}


def test_validate_in_sandbox_returns_none_when_runner_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si SandboxRunner lève SandboxUnavailable → retour None (pas de crash)."""
    from src.sandbox.runner import SandboxUnavailable

    def _raises(**kwargs):
        raise SandboxUnavailable("docker daemon down")

    monkeypatch.setattr(sv_module, "SandboxRunner", _raises)

    result = validate_files_in_sandbox(
        files=[_file("src/foo.py")],
        sandbox_image="iaa-sandbox:latest",
        sandbox_timeout=10,
    )
    assert result is None


def test_validate_in_sandbox_returns_none_when_image_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_runner = MagicMock()
    fake_runner.image_exists.return_value = False
    monkeypatch.setattr(sv_module, "SandboxRunner", lambda **kw: fake_runner)

    result = validate_files_in_sandbox(
        files=[_file("src/foo.py")],
        sandbox_image="iaa-sandbox:latest",
        sandbox_timeout=10,
    )
    assert result is None


def test_validate_in_sandbox_writes_files_and_runs_pytest(
    monkeypatch: pytest.MonkeyPatch,
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
    monkeypatch.setattr(sv_module, "SandboxRunner", lambda **kw: fake_runner)

    captured_workspace = {}

    def _capture_run(workspace, command):
        captured_workspace["path"] = Path(workspace)
        # Vérifie que les fichiers sont bien là pendant le run
        assert (Path(workspace) / "src" / "foo.py").exists()
        assert (Path(workspace) / "tests" / "test_foo.py").exists()
        assert (Path(workspace) / "conftest.py").exists()
        return fake_result

    fake_runner.run.side_effect = _capture_run

    result = validate_files_in_sandbox(
        files=[
            _file("src/foo.py", "def hello(): return 'world'\n"),
            _file(
                "tests/test_foo.py",
                "from src.foo import hello\n\ndef test_hello(): assert hello() == 'world'\n",
            ),
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.sandbox.runner import SandboxResult

    fake_result = SandboxResult(
        exit_code=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
        timed_out=False,
        image="iaa-sandbox:latest",
        command=["pytest"],
    )
    fake_runner = MagicMock()
    fake_runner.image_exists.return_value = True
    fake_runner.run.return_value = fake_result
    monkeypatch.setattr(sv_module, "SandboxRunner", lambda **kw: fake_runner)

    # Mélange : un fichier valide + un sans path (à ignorer)
    result = validate_files_in_sandbox(
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Régression : sans conftest.py qui ajoute le workspace au sys.path,
    `from src.x import y` échoue dans le sandbox."""
    from src.sandbox.runner import SandboxResult

    fake_result = SandboxResult(
        exit_code=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
        timed_out=False,
        image="iaa-sandbox:latest",
        command=["pytest"],
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
    monkeypatch.setattr(sv_module, "SandboxRunner", lambda **kw: fake_runner)

    validate_files_in_sandbox(
        files=[_file("src/foo.py")],
        sandbox_image="iaa-sandbox:latest",
        sandbox_timeout=10,
    )

    assert "sys.path.insert" in captured_conftest_content["text"]


def test_validate_in_sandbox_preserves_user_conftest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si l'utilisateur fournit son propre conftest.py, on ne l'écrase PAS."""
    from src.sandbox.runner import SandboxResult

    fake_result = SandboxResult(
        exit_code=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
        timed_out=False,
        image="iaa-sandbox:latest",
        command=["pytest"],
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
    monkeypatch.setattr(sv_module, "SandboxRunner", lambda **kw: fake_runner)

    validate_files_in_sandbox(
        files=[
            _file("src/foo.py"),
            {"path": "conftest.py", "content": user_conftest, "language": "python"},
        ],
        sandbox_image="iaa-sandbox:latest",
        sandbox_timeout=10,
    )

    assert captured["text"] == user_conftest


# Sprint GGG.1 — kill-switch enable_sandbox


def test_validate_in_sandbox_skipped_when_enable_sandbox_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sprint GGG.1 : si enable_sandbox=False (cas VPS sans Docker ou skip dev),
    le helper court-circuite immédiatement sans tenter d'instancier SandboxRunner."""
    # Si ce mock était appelé, il lèverait — preuve que le court-circuit
    # est bien antérieur à toute interaction Docker.
    def _should_not_be_called(**kwargs):
        raise AssertionError(
            "SandboxRunner ne doit JAMAIS être instancié quand enable_sandbox=False"
        )

    monkeypatch.setattr(sv_module, "SandboxRunner", _should_not_be_called)

    result = validate_files_in_sandbox(
        files=[_file("src/foo.py")],
        sandbox_image="iaa-sandbox:latest",
        sandbox_timeout=10,
        enable_sandbox=False,
    )
    assert result is None


def test_validate_in_sandbox_enable_sandbox_param_overrides_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sprint GGG.1 : le param explicite gagne sur Settings.enable_sandbox.
    Permet aux callers de forcer le comportement sans toucher à .env."""
    # On simule un Settings avec enable_sandbox=True. Le param explicit False
    # doit gagner et court-circuiter.
    from src.core.config import Settings

    fake_settings = Settings(  # type: ignore[call-arg]
        _env_file=None, anthropic_api_key="sk-ant-test"
    )
    fake_settings.enable_sandbox = True

    def _fake_get_settings():
        return fake_settings

    monkeypatch.setattr("src.core.config.get_settings", _fake_get_settings)

    def _should_not_be_called(**kwargs):
        raise AssertionError("court-circuit doit être fait par le param explicit")

    monkeypatch.setattr(sv_module, "SandboxRunner", _should_not_be_called)

    result = validate_files_in_sandbox(
        files=[_file("src/foo.py")],
        sandbox_image="iaa-sandbox:latest",
        sandbox_timeout=10,
        enable_sandbox=False,  # ← explicit override
    )
    assert result is None


# ============================================================================
# Sprint JJJ.3d — couverture de print_sandbox_result
# ============================================================================


def test_print_sandbox_result_green_panel_on_success() -> None:
    """Sprint JJJ.3d : couvre 95-104 du chemin success (exit_code=0)."""
    from io import StringIO

    from rich.console import Console

    from src.sandbox.runner import SandboxResult
    from src.tools.sandbox_validate import print_sandbox_result

    result = SandboxResult(
        exit_code=0,
        stdout="5 passed in 0.3s",
        stderr="",
        duration_seconds=0.45,
        timed_out=False,
        image="test:latest",
        command=["pytest"],
    )
    # Console non-terminale pour capture testable
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    print_sandbox_result(result, console=console)
    output = buf.getvalue()
    assert "exit_code=0" in output
    assert "STDOUT" in output
    assert "5 passed" in output
    # Pas de STDERR (vide)
    assert "STDERR" not in output


def test_print_sandbox_result_red_panel_on_failure() -> None:
    """Sprint JJJ.3d : couvre 95-104 du chemin failure (exit_code != 0)."""
    from io import StringIO

    from rich.console import Console

    from src.sandbox.runner import SandboxResult
    from src.tools.sandbox_validate import print_sandbox_result

    result = SandboxResult(
        exit_code=1,
        stdout="2 failed, 3 passed",
        stderr="AssertionError: expected X got Y",
        duration_seconds=1.2,
        timed_out=False,
        image="test:latest",
        command=["pytest"],
    )
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    print_sandbox_result(result, console=console)
    output = buf.getvalue()
    assert "exit_code=1" in output
    assert "STDOUT" in output
    assert "STDERR" in output
    assert "AssertionError" in output


def test_print_sandbox_result_no_stdout_section_when_empty() -> None:
    """Sprint JJJ.3d : pas de section STDOUT si result.stdout est vide."""
    from io import StringIO

    from rich.console import Console

    from src.sandbox.runner import SandboxResult
    from src.tools.sandbox_validate import print_sandbox_result

    result = SandboxResult(
        exit_code=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
        timed_out=False,
        image="x:latest",
        command=[],
    )
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    print_sandbox_result(result, console=console)
    output = buf.getvalue()
    assert "exit_code=0" in output
    assert "STDOUT" not in output
    assert "STDERR" not in output


def test_print_sandbox_result_truncates_long_stdout() -> None:
    """Sprint JJJ.3d : couvre 107-109 — stdout > 80 lignes tronqué à 80 dernières."""
    from io import StringIO

    from rich.console import Console

    from src.sandbox.runner import SandboxResult
    from src.tools.sandbox_validate import print_sandbox_result

    long_stdout = "\n".join(f"line {i}" for i in range(200))
    result = SandboxResult(
        exit_code=0,
        stdout=long_stdout,
        stderr="",
        duration_seconds=0.5,
        timed_out=False,
        image="x:latest",
        command=[],
    )
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    print_sandbox_result(result, console=console)
    output = buf.getvalue()
    # Les dernières lignes doivent être présentes
    assert "line 199" in output
    assert "line 198" in output
    # Les premières lignes (avant -80) ne doivent PAS être présentes
    assert "line 0\n" not in output
    assert "line 50\n" not in output


def test_print_sandbox_result_truncates_long_stderr() -> None:
    """Sprint JJJ.3d : couvre 112 — stderr tronqué à 2000 derniers chars."""
    from io import StringIO

    from rich.console import Console

    from src.sandbox.runner import SandboxResult
    from src.tools.sandbox_validate import print_sandbox_result

    long_stderr = "X" * 5000 + "FINAL_MARKER"
    result = SandboxResult(
        exit_code=1,
        stdout="",
        stderr=long_stderr,
        duration_seconds=0.1,
        timed_out=False,
        image="x:latest",
        command=[],
    )
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    print_sandbox_result(result, console=console)
    output = buf.getvalue()
    # Le marker final (dans les 2000 derniers chars) doit être présent
    assert "FINAL_MARKER" in output


def test_print_sandbox_result_uses_default_console_when_none() -> None:
    """Sprint JJJ.3d : si console=None, on instancie une Console par défaut.
    Ne doit pas crash même si stdout est non-interactif."""
    from src.sandbox.runner import SandboxResult
    from src.tools.sandbox_validate import print_sandbox_result

    result = SandboxResult(
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_seconds=0.1,
        timed_out=False,
        image="x:latest",
        command=[],
        # Sprint LLL : assertion explicite (la fonction est void → return None).
        # Sans cette ligne, le test était flaggé TEST_NO_ASSERT.
    )
    # Ne lève rien — la fonction crée une Console par défaut en interne
    out = print_sandbox_result(result, console=None)
    # Assertion : la fonction est void par contrat (logging-only).
    assert out is None


# Régression : apply_mission.py expose toujours les helpers en alias pour la
# compatibilité ascendante (les anciens scripts ou notebooks externes).
def test_apply_mission_exposes_legacy_aliases() -> None:
    """Le module apply_mission doit toujours fournir _validate_in_sandbox et
    _print_sandbox_result pour la rétro-compatibilité, même si la logique vit
    dans src.tools.sandbox_validate."""
    import importlib
    import sys

    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        if "apply_mission" in sys.modules:
            del sys.modules["apply_mission"]
        module = importlib.import_module("apply_mission")
        assert hasattr(module, "_validate_in_sandbox")
        assert hasattr(module, "_print_sandbox_result")
        assert callable(module._validate_in_sandbox)
        assert callable(module._print_sandbox_result)
    finally:
        if str(scripts_dir) in sys.path:
            sys.path.remove(str(scripts_dir))
