"""setup_runner — détections + actions click-to-install pour la page Setup (ADR-027).

# audit: ignore FILE_TOO_LONG -- 590 lignes acceptées : 10 détections +
# 5 actions + 1 enum + 3 dataclass dans un seul module pour la même surface
# fonctionnelle (Setup Wizard). Split par catégorie (3 sous-modules) ne
# clarifierait rien — toutes les fonctions sont consommées par la même page
# `0_🛠_Setup.py` et partagent le helper `_ollama_api_base()` + Status enum.

Concentre toute la logique non-UI du Setup Wizard. Les pages Streamlit
importent ce module et l'appellent ; aucune dépendance sur `streamlit` ici
pour garder la couche testable hors AppTest.

Composants détectés (cf. ADR-027 §scope) :

1. Python ≥ 3.12          → toujours OK (la GUI tourne)
2. uv installé             → `shutil.which("uv")`
3. Ollama installé         → `shutil.which("ollama")`
4. Ollama daemon démarré   → HTTP GET `/api/tags`
5. Modèle stratégique      → présent dans `/api/tags`
6. Modèle opérationnel     → présent dans `/api/tags`
7. Modèle bulk             → présent dans `/api/tags`
8. Docker installé + daemon→ `docker.from_env().ping()`
9. Image sandbox           → `images.get("iaa-sandbox:latest")`
10. Fichier .env           → fichier présent à la racine

Actions disponibles :

- `start_ollama_daemon()` : lance `ollama serve` détaché
- `pull_model(name)`     : `POST /api/pull` streaming JSON, yield progression
- `build_sandbox_image()` : invoque `docker build` via subprocess + log live
- `create_env_from_example()` : copie `.env.example` → `.env` si absent
- `start_docker_desktop()` : lance `Docker Desktop.exe` (Windows uniquement)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from src.core.config import get_settings


class Status(StrEnum):
    """Statut d'un composant Setup."""

    OK = "OK"
    MISSING = "MISSING"  # composant absent → installer ou créer
    STOPPED = "STOPPED"  # composant présent mais service arrêté → démarrer
    SKIPPED = "SKIPPED"  # composant optionnel volontairement désactivé
    UNKNOWN = "UNKNOWN"  # détection a planté


@dataclass
class ComponentStatus:
    """Résultat d'une détection unitaire."""

    key: str  # identifiant stable (ex: "ollama_daemon")
    label: str  # affichage utilisateur (ex: "Ollama daemon")
    status: Status
    detail: str
    install_url: str | None = None  # URL pour bouton "Télécharger"
    fix_action: str | None = None  # key d'action côté GUI (ex: "start_ollama")
    is_required: bool = True  # False = composant optionnel (Docker en mode no-sandbox)


# ============================================================================
# URLs officielles — ouvertes via st.link_button quand l'install requiert UAC
# ============================================================================

URL_OLLAMA = "https://ollama.com/download"
URL_DOCKER = "https://www.docker.com/products/docker-desktop/"
URL_UV = "https://docs.astral.sh/uv/getting-started/installation/"


# ============================================================================
# Détection du mode d'exécution (host vs conteneurisé) — v0.9.2
# ============================================================================
#
# Quand la GUI tourne dans un container Docker (`iaa-app:latest`), certaines
# détections n'ont pas de sens :
# - Le binaire `ollama` n'est PAS dans le container (volontaire — Ollama
#   tourne sur le host via `host.docker.internal:11434`). MISSING serait
#   trompeur, on retourne SKIPPED.
# - Le binaire `docker` n'est PAS dans le container (volontaire — sandbox
#   désactivé par défaut, cf. docs/deploy-lan.md §4).
# - L'installation `uv` n'est pas nécessaire (les deps sont gelées dans
#   l'image au build).
#
# La détection se fait via la sentinelle `/.dockerenv` (présente dans tous
# les containers Docker depuis 2014) ou via la variable d'env explicite
# `IAA_DEPLOYMENT_MODE=container` qu'on peut forcer.


def is_running_in_container() -> bool:
    """True si la GUI tourne dans un container Docker.

    Détection cumulative :
    1. Variable d'env `IAA_DEPLOYMENT_MODE=container` — override explicite.
    2. Présence du fichier `/.dockerenv` (créé par Docker dans tout container).
    3. Présence de `docker` ou `containerd` dans `/proc/1/cgroup` (Linux).

    Best-effort : si la détection plante (Windows host sans /proc, etc.),
    on retourne False (mode "host").
    """
    if os.environ.get("IAA_DEPLOYMENT_MODE") == "container":
        return True
    try:
        if Path("/.dockerenv").exists():
            return True
    except OSError:
        pass
    try:
        cgroup = Path("/proc/1/cgroup")
        if cgroup.exists():
            content = cgroup.read_text(encoding="utf-8")
            if "docker" in content or "containerd" in content:
                return True
    except OSError:
        pass
    return False


# ============================================================================
# Détections — chaque fonction retourne ComponentStatus, ne lève jamais
# ============================================================================


def _ollama_api_base() -> str:
    """Dérive l'URL native Ollama (`/api/...`) depuis `ollama_base_url`.

    Settings stocke l'endpoint OpenAI-compatible (`http://host:11434/v1`).
    L'API native vit à la racine (`/api/tags`, `/api/pull`).
    """
    s = get_settings()
    return s.ollama_base_url.rstrip("/").removesuffix("/v1")


def _safe(fn, key: str, label: str) -> ComponentStatus:
    """Wrap une détection pour capturer toute exception."""
    try:
        return fn()
    except Exception as exc:
        return ComponentStatus(
            key=key,
            label=label,
            status=Status.UNKNOWN,
            detail=f"{type(exc).__name__}: {exc}",
        )


def detect_python() -> ComponentStatus:
    ver = sys.version_info
    if ver < (3, 12):
        return ComponentStatus(
            key="python",
            label="Python ≥ 3.12",
            status=Status.MISSING,
            detail=f"Version détectée : {ver.major}.{ver.minor}.{ver.micro} — upgrade requis",
        )
    return ComponentStatus(
        key="python",
        label="Python ≥ 3.12",
        status=Status.OK,
        detail=f"{ver.major}.{ver.minor}.{ver.micro}",
    )


def detect_uv() -> ComponentStatus:
    # v0.9.2 — En container, les deps sont gelées dans l'image au build,
    # uv n'est pas requis runtime → SKIPPED plutôt que MISSING (trompeur).
    if is_running_in_container():
        return ComponentStatus(
            key="uv",
            label="uv (package manager)",
            status=Status.SKIPPED,
            detail="Non requis : deps gelées dans l'image Docker au build.",
            is_required=False,
        )
    path = shutil.which("uv")
    if path is None:
        return ComponentStatus(
            key="uv",
            label="uv (package manager)",
            status=Status.MISSING,
            detail="`uv` introuvable dans le PATH",
            install_url=URL_UV,
            is_required=False,  # la GUI tourne déjà donc deps installées
        )
    return ComponentStatus(
        key="uv",
        label="uv (package manager)",
        status=Status.OK,
        detail=path,
        is_required=False,
    )


def detect_ollama_installed() -> ComponentStatus:
    # v0.9.2 — En container, le binaire `ollama` n'est PAS dans l'image
    # (volontaire — Ollama tourne sur le host via host.docker.internal).
    # SKIPPED car ce qui compte c'est que le daemon réponde, vérifié plus loin.
    if is_running_in_container():
        return ComponentStatus(
            key="ollama_installed",
            label="Ollama installé",
            status=Status.SKIPPED,
            detail=(
                "Mode container : le binaire local n'est pas requis. "
                "Le daemon doit tourner sur le host (vérifié ci-dessous)."
            ),
            is_required=False,
        )
    path = shutil.which("ollama")
    if path is None:
        return ComponentStatus(
            key="ollama_installed",
            label="Ollama installé",
            status=Status.MISSING,
            detail="Binaire `ollama` introuvable dans le PATH",
            install_url=URL_OLLAMA,
        )
    return ComponentStatus(
        key="ollama_installed",
        label="Ollama installé",
        status=Status.OK,
        detail=path,
    )


def detect_ollama_daemon() -> ComponentStatus:
    """Ping `/api/tags` pour vérifier que le daemon répond.

    NB: ne dit pas si les modèles sont pullés (cf. detect_model_*).
    """
    url = f"{_ollama_api_base()}/api/tags"
    try:
        req = urllib.request.Request(url)  # noqa: S310 — localhost Ollama
        with urllib.request.urlopen(req, timeout=3) as resp:  # noqa: S310 — localhost Ollama
            json.loads(resp.read().decode("utf-8"))
        return ComponentStatus(
            key="ollama_daemon",
            label="Ollama daemon",
            status=Status.OK,
            detail=f"daemon joignable sur {url}",
        )
    except urllib.error.URLError as exc:
        # v0.9.3 — En container, le bouton "Démarrer le daemon" ne peut pas
        # marcher (binaire ollama absent de l'image). On guide l'opérateur
        # vers le PC host. Pas de fix_action ; install_url=None.
        reason = exc.reason if hasattr(exc, "reason") else exc
        if is_running_in_container():
            return ComponentStatus(
                key="ollama_daemon",
                label="Ollama daemon",
                status=Status.STOPPED,
                detail=(
                    f"Daemon injoignable depuis le container ({reason}). "
                    "Vérifier sur le PC host que `ollama serve` tourne et que "
                    f"l'URL `{url}` est joignable (host.docker.internal "
                    "résout vers le host sur Docker Desktop ; en Linux, le "
                    "compose configure `extra_hosts: host-gateway`)."
                ),
                # Pas de fix_action : le container ne peut PAS démarrer ollama
            )
        return ComponentStatus(
            key="ollama_daemon",
            label="Ollama daemon",
            status=Status.STOPPED,
            detail=(
                f"Daemon injoignable ({reason}) — lance `ollama serve` ou clique sur Démarrer."
            ),
            fix_action="start_ollama",
        )


def _list_installed_models() -> set[str]:
    """Retourne les modèles pullés selon `/api/tags`. Lève si daemon down."""
    url = f"{_ollama_api_base()}/api/tags"
    req = urllib.request.Request(url)  # noqa: S310 — localhost Ollama
    with urllib.request.urlopen(req, timeout=3) as resp:  # noqa: S310 — localhost Ollama
        payload = json.loads(resp.read().decode("utf-8"))
    return {m["name"] for m in payload.get("models", []) if isinstance(m, dict)}


def _detect_model(tier: str, model_name: str) -> ComponentStatus:
    label = f"Modèle {tier} (`{model_name}`)"
    try:
        installed = _list_installed_models()
    except Exception:
        # Daemon down : on remonte un STOPPED neutre (le check daemon le
        # signalera explicitement, pas de doublon de message d'erreur).
        return ComponentStatus(
            key=f"model_{tier}",
            label=label,
            status=Status.UNKNOWN,
            detail="Daemon Ollama injoignable — démarrer d'abord le daemon.",
        )
    if model_name in installed:
        return ComponentStatus(
            key=f"model_{tier}",
            label=label,
            status=Status.OK,
            detail=f"`{model_name}` pullé",
        )
    return ComponentStatus(
        key=f"model_{tier}",
        label=label,
        status=Status.MISSING,
        detail=f"`{model_name}` absent — `ollama pull {model_name}` ou clique sur Pull.",
        fix_action=f"pull_model:{model_name}",
    )


def detect_model_strategic() -> ComponentStatus:
    return _detect_model("strategic", get_settings().model_strategic)


def detect_model_operational() -> ComponentStatus:
    return _detect_model("operational", get_settings().model_operational)


def detect_model_bulk() -> ComponentStatus:
    return _detect_model("bulk", get_settings().model_bulk)


def detect_docker() -> ComponentStatus:
    """Détecte Docker daemon (rapide, 1 seul appel ping)."""
    s = get_settings()
    label = "Docker daemon"
    # v0.9.3 — En container sans socket /var/run/docker.sock monté, le sandbox
    # ne peut PAS fonctionner (le binaire docker n'est pas dans l'image, et
    # même installé il aurait besoin du socket pour piloter le daemon host).
    # SKIPPED systématique pour ne pas afficher un MISSING + "Télécharger
    # Docker Desktop" trompeur depuis un poste distant qui consulte la GUI.
    if is_running_in_container() and not Path("/var/run/docker.sock").exists():
        return ComponentStatus(
            key="docker",
            label=label,
            status=Status.SKIPPED,
            detail=(
                "Mode container sans socket Docker monté — sandbox non disponible. "
                "Pour activer : monter `/var/run/docker.sock` côté compose "
                "(cf. docs/deploy-lan.md §4)."
            ),
            is_required=False,
        )
    if not s.enable_sandbox:
        return ComponentStatus(
            key="docker",
            label=label,
            status=Status.SKIPPED,
            detail="`ENABLE_SANDBOX=false` dans `.env` — sandbox désactivée, Docker non requis.",
            is_required=False,
        )
    if shutil.which("docker") is None:
        return ComponentStatus(
            key="docker",
            label=label,
            status=Status.MISSING,
            detail="Binaire `docker` introuvable — installer Docker Desktop.",
            install_url=URL_DOCKER,
            is_required=False,
        )
    try:
        import docker  # type: ignore[import]
    except ImportError:
        return ComponentStatus(
            key="docker",
            label=label,
            status=Status.MISSING,
            detail="SDK Python `docker` absent — `uv sync --all-groups` à relancer.",
            is_required=False,
        )
    try:
        client = docker.from_env()
        client.ping()
        v = client.version().get("Version", "?")
        return ComponentStatus(
            key="docker",
            label=label,
            status=Status.OK,
            detail=f"Docker {v} joignable",
            is_required=False,
        )
    except Exception as exc:
        # Docker installé mais daemon down (Windows : Docker Desktop pas lancé)
        fix = "start_docker" if sys.platform == "win32" else None
        return ComponentStatus(
            key="docker",
            label=label,
            status=Status.STOPPED,
            detail=f"Daemon Docker injoignable : {type(exc).__name__}. Lancer Docker Desktop.",
            install_url=URL_DOCKER,
            fix_action=fix,
            is_required=False,
        )


def detect_sandbox_image() -> ComponentStatus:
    """Vérifie présence de `iaa-sandbox:latest`."""
    s = get_settings()
    label = "Image sandbox (`iaa-sandbox:latest`)"
    # v0.9.3 — Cohérent avec detect_docker : en container sans socket Docker
    # monté, on ne peut pas inspecter les images du host. SKIPPED.
    if is_running_in_container() and not Path("/var/run/docker.sock").exists():
        return ComponentStatus(
            key="sandbox_image",
            label=label,
            status=Status.SKIPPED,
            detail="Mode container sans socket Docker monté — image non vérifiable.",
            is_required=False,
        )
    if not s.enable_sandbox:
        return ComponentStatus(
            key="sandbox_image",
            label=label,
            status=Status.SKIPPED,
            detail="Sandbox désactivée — image non requise.",
            is_required=False,
        )
    try:
        import docker  # type: ignore[import]
        from docker.errors import ImageNotFound  # type: ignore[import]
    except ImportError:
        return ComponentStatus(
            key="sandbox_image",
            label=label,
            status=Status.UNKNOWN,
            detail="SDK docker absent",
            is_required=False,
        )
    try:
        client = docker.from_env()
        client.ping()
    except Exception:
        return ComponentStatus(
            key="sandbox_image",
            label=label,
            status=Status.UNKNOWN,
            detail="Daemon Docker down — vérifie le check précédent.",
            is_required=False,
        )
    try:
        client.images.get("iaa-sandbox:latest")
        return ComponentStatus(
            key="sandbox_image",
            label=label,
            status=Status.OK,
            detail="Image présente",
            is_required=False,
        )
    except ImageNotFound:
        return ComponentStatus(
            key="sandbox_image",
            label=label,
            status=Status.MISSING,
            detail="Image absente — clique sur Build pour la construire (~2 min).",
            fix_action="build_sandbox",
            is_required=False,
        )


def detect_env_file() -> ComponentStatus:
    s = get_settings()
    env_path = s.project_root / ".env"
    example_path = s.project_root / ".env.example"
    label = "Fichier `.env`"
    if env_path.exists():
        return ComponentStatus(
            key="env_file",
            label=label,
            status=Status.OK,
            detail=str(env_path),
        )
    if example_path.exists():
        return ComponentStatus(
            key="env_file",
            label=label,
            status=Status.MISSING,
            detail="Absent — clique sur Créer pour copier depuis `.env.example`.",
            fix_action="create_env",
        )
    return ComponentStatus(
        key="env_file",
        label=label,
        status=Status.MISSING,
        detail="Absent et `.env.example` manquant aussi — vérifier l'intégrité du repo.",
    )


def detect_all() -> list[ComponentStatus]:
    """Lance toutes les détections séquentiellement (latence cumulée ~3-5 s).

    Pas de parallélisme : la plupart des détections sont rapides et le
    parallélisme cross-thread avec urllib + docker n'apporte pas grand chose
    en pratique (le bottleneck est `client.ping()` Docker, ~500 ms).
    """
    return [
        _safe(detect_python, "python", "Python ≥ 3.12"),
        _safe(detect_uv, "uv", "uv"),
        _safe(detect_ollama_installed, "ollama_installed", "Ollama installé"),
        _safe(detect_ollama_daemon, "ollama_daemon", "Ollama daemon"),
        _safe(detect_model_strategic, "model_strategic", "Modèle strategic"),
        _safe(detect_model_operational, "model_operational", "Modèle operational"),
        _safe(detect_model_bulk, "model_bulk", "Modèle bulk"),
        _safe(detect_docker, "docker", "Docker daemon"),
        _safe(detect_sandbox_image, "sandbox_image", "Image sandbox"),
        _safe(detect_env_file, "env_file", "Fichier .env"),
    ]


# ============================================================================
# Actions — opérations qui peuvent être déclenchées depuis la GUI
# ============================================================================


@dataclass
class ActionResult:
    """Résultat d'une action de fix."""

    success: bool
    message: str


def start_ollama_daemon() -> ActionResult:  # pragma: no cover
    """Lance `ollama serve` en sous-processus détaché.

    Si le daemon répond déjà, no-op succès. Sinon, fork un processus qui
    survit à la fermeture de la GUI (l'utilisateur doit l'arrêter manuellement
    avec `ollama stop` ou en quittant le tray icon Ollama).

    pragma: no cover — fork process détaché + poll 7s ; le mocking de
    `subprocess.Popen` avec creationflags Windows n'apporte pas de
    valeur de test. Validation manuelle au smoke-run de la GUI.
    """
    # Idempotence : déjà up = succès silencieux
    if detect_ollama_daemon().status == Status.OK:
        return ActionResult(success=True, message="Daemon déjà démarré.")

    if shutil.which("ollama") is None:
        return ActionResult(
            success=False,
            message="Binaire `ollama` introuvable — installer d'abord Ollama.",
        )

    # Résolution du chemin absolu pour éviter S607 (partial path) — on a
    # déjà vérifié ci-dessus que shutil.which retourne quelque chose.
    ollama_exe = shutil.which("ollama")
    assert ollama_exe is not None  # noqa: S101 — pré-condition vérifiée 3 lignes plus haut

    try:
        # Détacher proprement selon la plateforme. Sur Windows, on utilise
        # DETACHED_PROCESS pour que le processus survive à la GUI ; sur Unix,
        # start_new_session pour la même raison.
        if sys.platform == "win32":
            detached_process = 0x00000008
            create_new_process_group = 0x00000200
            subprocess.Popen(  # noqa: S603 — args statiques + chemin résolu
                [ollama_exe, "serve"],
                creationflags=detached_process | create_new_process_group,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
        else:
            subprocess.Popen(  # noqa: S603 — args statiques + chemin résolu
                [ollama_exe, "serve"],
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
    except Exception as exc:
        return ActionResult(
            success=False,
            message=f"Échec lancement daemon : {type(exc).__name__}: {exc}",
        )

    # Petit poll pour confirmer que le daemon répond avant de rendre la main.
    import time

    for _ in range(15):  # 15 × 0.5 s = 7.5 s max
        time.sleep(0.5)
        if detect_ollama_daemon().status == Status.OK:
            return ActionResult(success=True, message="Daemon démarré, /api/tags répond.")
    return ActionResult(
        success=False,
        message="Processus lancé mais /api/tags n'a pas répondu en 7 s. Vérifier les logs Ollama.",
    )


@dataclass
class PullProgress:
    """Événement de progression d'un pull de modèle."""

    status: str  # ex: "pulling manifest", "downloading", "verifying sha256 digest", "success"
    completed: int | None  # octets téléchargés (peut être None pour étapes hors-DL)
    total: int | None  # taille totale (peut être None)
    detail: str = ""

    @property
    def percent(self) -> float | None:
        if self.completed is None or self.total is None or self.total == 0:
            return None
        return 100.0 * self.completed / self.total


def pull_model(model_name: str) -> Iterator[PullProgress]:
    """Stream le pull d'un modèle Ollama (`POST /api/pull`).

    Yield des `PullProgress` au fur et à mesure. L'appelant (page Streamlit)
    met à jour la barre de progression sur chaque yield.

    Lève RuntimeError si daemon down.
    """
    url = f"{_ollama_api_base()}/api/pull"
    body = json.dumps({"name": model_name, "stream": True}).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 — localhost Ollama
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        # Pas de timeout pour la connexion long-lived ; le daemon stream pendant
        # plusieurs heures pour les modèles 32B (~20 Go).
        resp = urllib.request.urlopen(req, timeout=10)  # noqa: S310 — localhost Ollama
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Daemon Ollama injoignable ({exc}) — démarrer d'abord.") from exc

    with resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            try:
                payload: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue
            yield PullProgress(
                status=payload.get("status", ""),
                completed=payload.get("completed"),
                total=payload.get("total"),
                detail=payload.get("digest", ""),
            )
            if payload.get("status") == "success":
                return


def build_sandbox_image() -> Iterator[str]:  # pragma: no cover
    """Lance `docker build` pour `iaa-sandbox:latest`, yield les lignes stdout/stderr.

    Sécurité : args entièrement statiques (pas d'input utilisateur),
    donc OK noqa S603/S607.

    pragma: no cover — wrapper `docker build` subprocess streaming ; mocker
    Popen.stdout iter ligne par ligne ne valide pas grand chose. Validation
    manuelle au premier déclenchement du bouton "Build l'image" en GUI.
    """
    s = get_settings()
    dockerfile = s.project_root / "infra" / "docker" / "sandbox.Dockerfile"
    if not dockerfile.exists():
        yield f"FAIL: Dockerfile absent : {dockerfile}"
        return

    docker_exe = shutil.which("docker")
    if docker_exe is None:
        yield "FAIL: `docker` introuvable dans le PATH — installer Docker Desktop."
        return

    cmd = [
        docker_exe,
        "build",
        "-t",
        "iaa-sandbox:latest",
        "-f",
        str(dockerfile),
        str(dockerfile.parent),
    ]
    yield f"$ {' '.join(cmd)}"
    try:
        proc = subprocess.Popen(  # noqa: S603 — args statiques + chemin résolu
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        yield "FAIL: `docker` introuvable dans le PATH — installer Docker Desktop."
        return

    if proc.stdout is None:
        yield "FAIL: subprocess.Popen n'a pas fourni de pipe stdout."
        return
    for line in proc.stdout:
        yield line.rstrip()
    rc = proc.wait()
    if rc == 0:
        yield "✅ Image `iaa-sandbox:latest` construite avec succès."
    else:
        yield f"❌ docker build a échoué (exit {rc})."


def create_env_from_example() -> ActionResult:
    """Copie `.env.example` → `.env` si absent."""
    s = get_settings()
    env_path = s.project_root / ".env"
    example_path = s.project_root / ".env.example"
    if env_path.exists():
        return ActionResult(success=True, message=".env existe déjà — pas écrasé.")
    if not example_path.exists():
        return ActionResult(
            success=False,
            message=f".env.example absent à {example_path} — repo incomplet ?",
        )
    try:
        shutil.copyfile(example_path, env_path)
    except OSError as exc:
        return ActionResult(success=False, message=f"Échec copie : {exc}")
    return ActionResult(success=True, message=f".env créé : {env_path}")


def read_env_content() -> str:
    """Lit le contenu de .env pour édition GUI (vide si absent)."""
    env_path = get_settings().project_root / ".env"
    if not env_path.exists():
        return ""
    return env_path.read_text(encoding="utf-8")


def write_env_content(content: str) -> ActionResult:
    """Écrit le contenu fourni dans .env (utilisé par le st.text_area de la page)."""
    env_path = get_settings().project_root / ".env"
    try:
        env_path.write_text(content, encoding="utf-8", newline="\n")
    except OSError as exc:
        return ActionResult(success=False, message=f"Échec écriture .env : {exc}")
    return ActionResult(success=True, message=f".env sauvegardé ({len(content)} octets)")


def start_docker_desktop() -> ActionResult:  # pragma: no cover
    """Lance Docker Desktop sur Windows (Mac/Linux : no-op explicite).

    Cherche l'exécutable aux emplacements standards et le lance détaché.

    pragma: no cover — résolution chemin Docker Desktop + Popen DETACHED ;
    OS-spécifique Windows et requiert l'install réelle. Validation manuelle
    au premier déclenchement du bouton "Démarrer Docker Desktop" en GUI.
    """
    if sys.platform != "win32":
        return ActionResult(
            success=False,
            message=(
                "Démarrage automatique disponible uniquement sous Windows. "
                "Sur Mac : lancer Docker Desktop depuis Applications. "
                "Sur Linux : `systemctl start docker` (ou démarrer le service)."
            ),
        )
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files"))
        / "Docker"
        / "Docker"
        / "Docker Desktop.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "Docker"
        / "Docker"
        / "Docker Desktop.exe",
    ]
    exe = next((p for p in candidates if p.exists()), None)
    if exe is None:
        return ActionResult(
            success=False,
            message=(
                "Docker Desktop.exe introuvable aux chemins standards. "
                f"Cherché : {[str(p) for p in candidates]}"
            ),
        )
    try:
        detached_process = 0x00000008
        create_new_process_group = 0x00000200
        subprocess.Popen(  # noqa: S603 — chemin contrôlé, pas d'input externe
            [str(exe)],
            creationflags=detached_process | create_new_process_group,
            close_fds=True,
        )
    except Exception as exc:
        return ActionResult(
            success=False,
            message=f"Échec lancement : {type(exc).__name__}: {exc}",
        )
    return ActionResult(
        success=True,
        message=(
            "Docker Desktop démarré. Le daemon met 30-60 s à devenir joignable. "
            "Recharge la page pour re-détecter."
        ),
    )
