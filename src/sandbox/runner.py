"""SandboxRunner — exécution isolée de code (tests, scripts) dans un container Docker.

Garde-fou Phase 3 — toute exécution de code généré par les agents passe par ici.

Politique par défaut :
- network = "none" (pas d'accès réseau)
- read-only = True (workspace monté en lecture seule)
- mem_limit = configurable (défaut 512 MB)
- cpu_count = 1
- pids_limit = 256 (anti fork-bomb)
- user = "nobody:nogroup" (pas de root)
- timeout strict (défaut 30 s, kill au-delà)

Le runner ne lève pas d'exception sur exit code != 0 — il retourne un SandboxResult
qui contient stdout/stderr/exit_code/timed_out. Au caller de juger.
"""

from __future__ import annotations

import contextlib
import io
import tarfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

# docker SDK est lourd à importer ; on le wrap pour permettre le mock dans les tests
try:
    import docker
    from docker.errors import ContainerError, DockerException, ImageNotFound, NotFound

    _DOCKER_AVAILABLE = True
except ImportError:
    docker = None
    _DOCKER_AVAILABLE = False
    ContainerError = DockerException = ImageNotFound = NotFound = Exception

from src.core.logging import get_logger

log = get_logger("sandbox.runner")


class SandboxResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    image: str = ""
    command: list[str] = []


class SandboxUnavailable(RuntimeError):
    """Levée quand Docker n'est pas disponible (pas installé, ou daemon down)."""


class SandboxRunner:
    """Exécute des commandes dans un container Docker éphémère et isolé."""

    def __init__(
        self,
        image: str = "iaa-sandbox:latest",
        network: str = "none",
        memory: str = "512m",
        cpu_count: int = 1,
        pids_limit: int = 256,
        user: str = "nobody:nogroup",
        timeout_seconds: int = 30,
        client: Any = None,
    ) -> None:
        self.image = image
        self.network = network
        self.memory = memory
        self.cpu_count = cpu_count
        self.pids_limit = pids_limit
        self.user = user
        self.timeout_seconds = timeout_seconds
        if client is not None:
            self._client = client
        elif _DOCKER_AVAILABLE:
            try:
                self._client = docker.from_env()
            except DockerException as exc:
                raise SandboxUnavailable(
                    f"Docker non joignable : {exc}. Vérifie que Docker Desktop est lancé."
                ) from exc
        else:
            raise SandboxUnavailable("Le SDK docker-py n'est pas installé.")

    def ping(self) -> bool:
        """Test de connectivité du daemon Docker."""
        try:
            self._client.ping()
            return True
        except Exception:
            return False

    def image_exists(self, image: str | None = None) -> bool:
        """Vérifie qu'une image est présente localement."""
        target = image or self.image
        try:
            self._client.images.get(target)
            return True
        except ImageNotFound:
            return False
        except DockerException:
            return False

    def run(
        self,
        workspace: Path,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Lance une commande dans un container éphémère et retourne le résultat.

        - `workspace` : dossier copié dans /workspace (read-only) AVANT l'exécution.
          On copie via tar archive plutôt que volume mount, pour fiabilité Windows.
        - `command` : si None, utilise le CMD de l'image (typiquement `pytest`).
        - `env` : variables d'environnement du container (sans secrets).
        """
        if not workspace.is_dir():
            raise ValueError(f"workspace doit être un dossier existant : {workspace}")

        container = None
        started = time.perf_counter()
        timed_out = False
        cmd_used = command or []

        try:
            # Trade-off de sécurité (validé 2026-05-10) : on désactive read_only=True car
            # docker put_archive() écrit AVANT le start du container, donc avant que les
            # tmpfs ne soient montés → conflit "container rootfs is marked read-only".
            # Compensation : tous les autres garde-fous restent en place (no-network,
            # user=nobody, mem/cpu/pids limits, timeout strict, container éphémère
            # détruit après chaque run, fs des libs système non modifiable depuis nobody).
            # Une alternative bind-mount du workspace existe mais est moins portable
            # Windows ↔ Linux que tar+tmpfs.
            container = self._client.containers.create(
                image=self.image,
                command=command,
                environment=env or {},
                network_mode=self.network,
                mem_limit=self.memory,
                nano_cpus=int(self.cpu_count * 1_000_000_000),
                pids_limit=self.pids_limit,
                user=self.user,
                read_only=False,
                # /tmp ici = tmpfs RAM dans un container Docker éphémère + isolé
                # (no-net, user=nobody, mem/cpu/pid limits) — pas un /tmp hôte.
                tmpfs={"/tmp": "size=64m,mode=1777"},  # noqa: S108
                detach=True,
                working_dir="/workspace",
            )

            # Copie du workspace dans /workspace via tar
            archive = self._make_tar(workspace)
            container.put_archive("/workspace", archive)

            container.start()

            try:
                exit_status = container.wait(timeout=self.timeout_seconds)
                exit_code = int(exit_status.get("StatusCode", -1))
            except Exception:  # ReadTimeout & co
                timed_out = True
                exit_code = -1
                with contextlib.suppress(Exception):
                    container.kill()

            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

            duration = time.perf_counter() - started
            log.info(
                "sandbox.run.complete",
                image=self.image,
                exit_code=exit_code,
                timed_out=timed_out,
                duration_s=round(duration, 2),
            )
            return SandboxResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                timed_out=timed_out,
                image=self.image,
                command=cmd_used,
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except NotFound:
                    pass
                except DockerException as exc:
                    log.warning("sandbox.cleanup.failed", error=str(exc))

    @staticmethod
    def _make_tar(source_dir: Path) -> bytes:
        """Crée une archive tar in-memory du dossier (sans le dossier parent)."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for entry in source_dir.rglob("*"):
                if any(
                    part in {".git", "__pycache__", ".venv", ".pytest_cache"}
                    for part in entry.parts
                ):
                    continue
                arcname = entry.relative_to(source_dir).as_posix()
                tar.add(str(entry), arcname=arcname, recursive=False)
        buf.seek(0)
        return buf.read()
