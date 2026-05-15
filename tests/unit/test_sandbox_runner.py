"""Tests unitaires pour SandboxRunner — Docker mocké."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.sandbox.runner import SandboxResult, SandboxRunner


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def hello(): return 'world'\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_foo.py").write_text(
        "from src.foo import hello\n\ndef test_hello():\n    assert hello() == 'world'\n"
    )
    return tmp_path


def _fake_container(exit_code: int = 0, stdout: bytes = b"ok\n", stderr: bytes = b"") -> MagicMock:
    container = MagicMock()
    container.wait.return_value = {"StatusCode": exit_code}
    container.logs.side_effect = lambda stdout, stderr: stdout_value(stdout, stderr_value=stderr)
    container.remove.return_value = None
    container.start.return_value = None
    container.put_archive.return_value = True

    def logs_side_effect(stdout: bool, stderr: bool) -> bytes:
        if stdout and not stderr:
            return stdout
        if stderr and not stdout:
            return stderr
        return b""

    def fake_logs(stdout: bool = False, stderr: bool = False) -> bytes:
        if stdout and not stderr:
            return _fake_container._stdout  # type: ignore[attr-defined]
        if stderr and not stdout:
            return _fake_container._stderr  # type: ignore[attr-defined]
        return b""

    _fake_container._stdout = stdout  # type: ignore[attr-defined]
    _fake_container._stderr = stderr  # type: ignore[attr-defined]
    container.logs.side_effect = fake_logs
    return container


def stdout_value(stdout: bool, stderr_value: bool) -> bytes:
    """Helper bidon pour signature mockée."""
    return b""


def _fake_client(container: MagicMock) -> MagicMock:
    client = MagicMock()
    client.ping.return_value = True
    client.containers.create.return_value = container
    client.images.get.return_value = MagicMock()
    return client


def test_runner_executes_command_and_returns_result(workspace: Path) -> None:
    container = _fake_container(exit_code=0, stdout=b"5 passed\n", stderr=b"")
    client = _fake_client(container)

    runner = SandboxRunner(client=client, timeout_seconds=10)
    result = runner.run(workspace=workspace, command=["pytest"])

    assert isinstance(result, SandboxResult)
    assert result.exit_code == 0
    assert "5 passed" in result.stdout
    assert result.timed_out is False
    assert result.command == ["pytest"]
    container.start.assert_called_once()
    container.put_archive.assert_called_once()
    container.remove.assert_called_once()


def test_runner_captures_failure_exit_code(workspace: Path) -> None:
    container = _fake_container(exit_code=1, stdout=b"", stderr=b"AssertionError\n")
    client = _fake_client(container)

    runner = SandboxRunner(client=client)
    result = runner.run(workspace=workspace, command=["pytest"])

    assert result.exit_code == 1
    assert "AssertionError" in result.stderr


def test_runner_marks_timed_out_when_wait_raises(workspace: Path) -> None:
    container = _fake_container(stdout=b"running...\n", stderr=b"")
    container.wait.side_effect = Exception("ReadTimeout")
    client = _fake_client(container)

    runner = SandboxRunner(client=client, timeout_seconds=2)
    result = runner.run(workspace=workspace, command=["sleep", "100"])

    assert result.timed_out is True
    assert result.exit_code == -1
    container.kill.assert_called_once()


def test_runner_passes_security_options(workspace: Path) -> None:
    container = _fake_container(exit_code=0)
    client = _fake_client(container)

    runner = SandboxRunner(
        client=client,
        network="none",
        memory="256m",
        cpu_count=1,
        pids_limit=128,
        user="nobody:nogroup",
    )
    runner.run(workspace=workspace)

    call_kwargs = client.containers.create.call_args.kwargs
    assert call_kwargs["network_mode"] == "none"
    assert call_kwargs["mem_limit"] == "256m"
    assert call_kwargs["nano_cpus"] == 1_000_000_000
    assert call_kwargs["pids_limit"] == 128
    assert call_kwargs["user"] == "nobody:nogroup"
    assert "/tmp" in call_kwargs["tmpfs"]
    # Note: read_only=False (trade-off documenté) — put_archive écrit avant le mount
    # tmpfs, donc impossible de cumuler read_only=True ET extraction tar du workspace.
    # Compensation : tous les autres garde-fous tiennent.
    assert call_kwargs["read_only"] is False


def test_runner_rejects_invalid_workspace(tmp_path: Path) -> None:
    runner = SandboxRunner(client=_fake_client(_fake_container()))
    not_a_dir = tmp_path / "missing"
    with pytest.raises(ValueError, match="workspace"):
        runner.run(workspace=not_a_dir)


def test_runner_cleans_up_container_even_on_error(workspace: Path) -> None:
    container = _fake_container(exit_code=0)
    container.put_archive.side_effect = RuntimeError("disk full")
    client = _fake_client(container)

    runner = SandboxRunner(client=client)
    with pytest.raises(RuntimeError, match="disk full"):
        runner.run(workspace=workspace)

    container.remove.assert_called_once_with(force=True)


def test_make_tar_excludes_unwanted_dirs(workspace: Path) -> None:
    """L'archive tar doit ignorer .git, __pycache__, .venv."""
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text("secret")
    (workspace / "__pycache__").mkdir()
    (workspace / "__pycache__" / "x.pyc").write_text("compiled")

    archive = SandboxRunner._make_tar(workspace)
    import io
    import tarfile

    with tarfile.open(fileobj=io.BytesIO(archive), mode="r") as tar:
        names = tar.getnames()

    assert "src/foo.py" in names
    assert "tests/test_foo.py" in names
    assert not any(".git" in n for n in names)
    assert not any("__pycache__" in n for n in names)


def test_runner_ping_returns_true_on_healthy_daemon() -> None:
    client = _fake_client(_fake_container())
    runner = SandboxRunner(client=client)
    assert runner.ping() is True


def test_runner_ping_returns_false_on_dead_daemon() -> None:
    client = MagicMock()
    client.ping.side_effect = Exception("connection refused")
    client.images.get.return_value = MagicMock()
    runner = SandboxRunner(client=client)
    assert runner.ping() is False


def test_runner_image_exists_true_when_image_found() -> None:
    client = _fake_client(_fake_container())
    runner = SandboxRunner(client=client)
    assert runner.image_exists() is True


def test_runner_image_exists_false_when_not_found() -> None:
    from src.sandbox.runner import ImageNotFound

    client = MagicMock()
    client.ping.return_value = True
    client.images.get.side_effect = ImageNotFound("not here")
    runner = SandboxRunner(client=client)
    assert runner.image_exists() is False


# ============================================================================
# Sprint JJJ.3c — couverture des error paths Docker
# ============================================================================


def test_runner_init_raises_sandbox_unavailable_when_docker_daemon_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sprint JJJ.3c : couvre 85-88. Si docker.from_env() lève DockerException
    (daemon arrêté, socket inaccessible, etc.), on doit lever SandboxUnavailable
    avec un message clair."""
    import src.sandbox.runner as runner_mod
    from src.sandbox.runner import DockerException, SandboxUnavailable

    fake_docker = MagicMock()
    fake_docker.from_env.side_effect = DockerException("docker daemon down")

    monkeypatch.setattr(runner_mod, "docker", fake_docker)
    monkeypatch.setattr(runner_mod, "_DOCKER_AVAILABLE", True)

    with pytest.raises(SandboxUnavailable) as exc_info:
        SandboxRunner()
    assert "Docker non joignable" in str(exc_info.value)


def test_runner_image_exists_false_on_docker_exception() -> None:
    """Sprint JJJ.3c : couvre 108-109. Toute autre DockerException
    (réseau, perm) → False, pas de propagation."""
    from src.sandbox.runner import DockerException

    client = MagicMock()
    client.ping.return_value = True
    client.images.get.side_effect = DockerException("api error")
    runner = SandboxRunner(client=client)
    assert runner.image_exists() is False


def test_runner_image_exists_custom_target(workspace: Path) -> None:
    """Sprint JJJ.3c : image_exists doit accepter un override 'image=' (line 102)."""
    client = MagicMock()
    client.ping.return_value = True
    client.images.get.return_value = MagicMock()
    runner = SandboxRunner(client=client)
    # Override le target par défaut
    assert runner.image_exists(image="autre-image:tag") is True
    client.images.get.assert_called_with("autre-image:tag")


def test_runner_cleanup_handles_notfound_silently(workspace: Path) -> None:
    """Sprint JJJ.3c : couvre 197-198. Si le container a déjà disparu au
    cleanup (race condition), on swallow NotFound."""
    from src.sandbox.runner import NotFound

    container = _fake_container()
    container.remove.side_effect = NotFound("already gone")
    client = _fake_client(container)
    runner = SandboxRunner(client=client)
    # Le run doit compléter normalement malgré le cleanup raté
    result = runner.run(workspace=workspace, command=["pytest"])
    assert isinstance(result, SandboxResult)
    container.remove.assert_called_once()


def test_runner_cleanup_logs_warning_on_docker_exception(
    workspace: Path,
) -> None:
    """Sprint JJJ.3c : couvre 199-200. Si remove() lève autre chose qu'un
    NotFound (e.g. permission denied), on log warning et on continue."""
    from src.sandbox.runner import DockerException

    container = _fake_container()
    container.remove.side_effect = DockerException("perm denied")
    client = _fake_client(container)
    runner = SandboxRunner(client=client)
    # Pas de crash, résultat normal
    result = runner.run(workspace=workspace, command=["pytest"])
    assert isinstance(result, SandboxResult)
