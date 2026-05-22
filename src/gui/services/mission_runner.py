"""mission_runner — wrappers MissionRouter pour la GUI.

Encapsule la création du MissionRouter (FileMemory + VectorMemory + SkillsLibrary)
et l'exécution d'une mission avec gestion d'erreurs et options --apply/--validate.

Deux modes :
- `run_mission_sync(req)` : exécution synchrone (le `asyncio.run` est interne),
  retourne directement le `MissionRunOutcome` final. Aucun streaming.
- `run_mission_streaming(req)` (v0.8.0 F2) : retourne un Iterator qui yield
  des `ProgressEvent` au fur et à mesure, puis termine par un dernier item
  spécial `MissionRunOutcome`. Permet à Streamlit d'afficher en direct via
  `st.status` ce que font les agents.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from queue import Empty, Queue
from uuid import UUID

from src.core.budget import BudgetController
from src.core.checkpoint import CheckpointStore
from src.core.config import get_settings
from src.core.killswitch import Killswitch
from src.learning.missions_rag import MISSIONS_COLLECTION, MissionsRAG
from src.learning.prompt_ab import PromptAB
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory
from src.orchestrator.progress import ProgressEvent
from src.orchestrator.router import MissionRouter, UnifiedMissionResult
from src.tools.apply_files import ApplyAction, ApplyResult, apply_files


@dataclass
class MissionRunRequest:
    title: str
    description: str
    force_guild: str | None = None
    apply_files_on_success: bool = False
    force_overwrite: bool = False
    validate_sandbox: bool = False


@dataclass
class MissionRunOutcome:
    """Résultat consolidé pour l'affichage GUI."""

    result: UnifiedMissionResult
    apply_results: list[ApplyResult] | None = None
    sandbox_exit_code: int | None = None
    sandbox_stdout: str = ""
    sandbox_stderr: str = ""
    sandbox_duration_s: float = 0.0
    sandbox_skipped_reason: str | None = None


def build_router() -> MissionRouter:
    """Construit un MissionRouter cohérent avec scripts/run_mission.py."""
    settings = get_settings()
    project_root = settings.project_root
    memory = FileMemory(project_root / "data" / "memory")
    vector_memory_episodes = VectorMemory(
        persist_dir=settings.chroma_persist_dir,
        collection_name="agent_episodes",
    )
    vector_memory_skills = VectorMemory(
        persist_dir=settings.chroma_persist_dir,
        collection_name="agent_skills",
    )
    skills_library = SkillsLibrary(project_root / "skills", vector_memory=vector_memory_skills)
    budget = BudgetController(
        state_path=project_root / "data" / "budget_state.json",
        daily_budget_usd=settings.daily_budget_usd,
    )
    killswitch = Killswitch(project_root / "data" / ".killswitch_engaged")
    # v0.8.0 F1 — checkpoint store partagé entre CLI et GUI : data/checkpoints/
    checkpoint_store = CheckpointStore(project_root / "data" / "checkpoints")
    # v0.9.0 A1 — RAG sur missions passées (collection Chroma dédiée)
    vector_memory_missions = VectorMemory(
        persist_dir=settings.chroma_persist_dir,
        collection_name=MISSIONS_COLLECTION,
    )
    missions_rag = MissionsRAG(vector_memory_missions)
    # v0.9.0 A2 — A/B testing prompts (opt-in via Settings.ab_testing_agents).
    prompt_ab = PromptAB(
        prompts_root=project_root / "prompts",
        ab_store_root=project_root / "data" / "ab_tests",
    )
    return MissionRouter(
        memory=memory,
        settings=settings,
        vector_memory=vector_memory_episodes,
        skills_library=skills_library,
        budget=budget,
        killswitch=killswitch,
        checkpoint_store=checkpoint_store,
        missions_rag=missions_rag,
        prompt_ab=prompt_ab,
    )


def run_mission_sync(
    req: MissionRunRequest,
    *,
    mission_id: UUID | None = None,
) -> MissionRunOutcome:
    """Lance une mission et applique optionnellement les fichiers + sandbox.

    Synchrone du point de vue du caller (le `asyncio.run` est interne).
    Renvoie un MissionRunOutcome consolidé pour l'affichage.

    `mission_id` (v0.8.0 F1) permet de reprendre une mission Engineering
    interrompue depuis le dernier checkpoint.
    """
    router = build_router()
    result: UnifiedMissionResult = asyncio.run(
        router.run(
            title=req.title,
            description=req.description,
            force_guild=req.force_guild,
            mission_id=mission_id,
        )
    )

    outcome = MissionRunOutcome(result=result)

    if req.apply_files_on_success and result.final_verdict == "APPROVED":
        files = _extract_files_from_result(result)
        if files:
            outcome.apply_results = apply_files(
                files=files,
                project_root=get_settings().project_root,
                force=req.force_overwrite,
            )

    if (
        req.validate_sandbox
        and req.apply_files_on_success
        and result.final_verdict == "APPROVED"
        and outcome.apply_results
    ):
        outcome = _run_sandbox(outcome)

    return outcome


# ============================================================================
# v0.8.0 F2 — Streaming mode
# ============================================================================


StreamItem = ProgressEvent | MissionRunOutcome
"""Items émis par run_mission_streaming : soit un ProgressEvent intermédiaire,
soit le MissionRunOutcome final (dernier item)."""


def run_mission_streaming(
    req: MissionRunRequest,
    *,
    mission_id: UUID | None = None,
    poll_interval_s: float = 0.5,
) -> Iterator[StreamItem]:
    """Lance la mission dans un thread worker et yield les ProgressEvents au fil
    de l'eau, puis le MissionRunOutcome final.

    Pattern producer/consumer : un Thread exécute `asyncio.run(router.run(...))`
    avec un callback qui pousse les events dans une queue. Le caller (Streamlit)
    consomme la queue dans son thread principal (compatible avec st.status).

    Le caller DOIT consommer l'itérateur jusqu'au bout — sinon le thread worker
    reste bloqué sur queue.put() si la queue se remplit. (Limité par maxsize=64
    pour pas exploser la RAM si streaming ralentit côté GUI.)
    """
    events_queue: Queue[StreamItem | None] = Queue(maxsize=64)

    def _emit_event(event: ProgressEvent) -> None:
        # put() bloque si full ; pour éviter de figer le workflow si la GUI
        # s'arrête de consommer, on tolère la perte d'un event (suppress).
        with contextlib.suppress(Exception):
            events_queue.put(event, timeout=2.0)

    def _worker() -> None:
        """Exécute la mission dans une nouvelle event loop asyncio (thread)."""
        try:
            router = build_router()
            result: UnifiedMissionResult = asyncio.run(
                router.run(
                    title=req.title,
                    description=req.description,
                    force_guild=req.force_guild,
                    mission_id=mission_id,
                    on_progress=_emit_event,
                )
            )
            outcome = MissionRunOutcome(result=result)

            # Apply + sandbox post-traitement (synchrone après mission)
            if req.apply_files_on_success and result.final_verdict == "APPROVED":
                files = _extract_files_from_result(result)
                if files:
                    outcome.apply_results = apply_files(
                        files=files,
                        project_root=get_settings().project_root,
                        force=req.force_overwrite,
                    )
            if (
                req.validate_sandbox
                and req.apply_files_on_success
                and result.final_verdict == "APPROVED"
                and outcome.apply_results
            ):
                outcome = _run_sandbox(outcome)

            events_queue.put(outcome)
        except Exception as exc:
            # Pousse une erreur "fake outcome" pour ne pas figer le caller
            fake_result = UnifiedMissionResult(
                mission_id=str(mission_id) if mission_id else "unknown",
                title=req.title,
                guild="unknown",
                success=False,
                final_verdict="CRASH",
                quality_score=None,
                total_cost_usd=0.0,
                total_duration_seconds=0.0,
                summary=f"Crash worker thread : {type(exc).__name__}: {exc}",
                raw_result={},
            )
            events_queue.put(MissionRunOutcome(result=fake_result))
        finally:
            events_queue.put(None)  # sentinelle de fin

    worker = threading.Thread(target=_worker, daemon=True, name="mission_streaming_worker")
    worker.start()

    # Consume queue
    while True:
        try:
            item = events_queue.get(timeout=poll_interval_s)
        except Empty:
            continue
        if item is None:
            break
        yield item


def _extract_files_from_result(result: UnifiedMissionResult) -> list[dict[str, str]]:
    """Récupère la liste de fichiers produits depuis le raw_result."""
    raw = result.raw_result or {}
    files = raw.get("files_produced", [])
    if not isinstance(files, list):
        return []
    valid: list[dict[str, str]] = []
    for f in files:
        if not isinstance(f, dict):
            continue
        if not f.get("path") or "content" not in f:
            continue
        valid.append({"path": str(f["path"]), "content": str(f["content"])})
    return valid


def _run_sandbox(outcome: MissionRunOutcome) -> MissionRunOutcome:
    """Lance la validation sandbox sur les fichiers appliqués."""
    from src.tools.sandbox_validate import validate_files_in_sandbox

    files: list[dict[str, str]] = []
    if outcome.apply_results:
        project_root = get_settings().project_root
        for ar in outcome.apply_results:
            if ar.action != ApplyAction.WRITTEN:
                continue
            try:
                content = (project_root / ar.path).read_text(encoding="utf-8")
            except OSError:
                continue
            files.append({"path": ar.path, "content": content})

    if not files:
        outcome.sandbox_skipped_reason = "Aucun fichier appliqué à valider."
        return outcome

    settings = get_settings()
    sandbox_result = validate_files_in_sandbox(
        files=files,
        sandbox_image=settings.sandbox_image
        if settings.sandbox_image != "python:3.12-slim"
        else "iaa-sandbox:latest",
        sandbox_timeout=settings.sandbox_timeout_seconds,
        enable_sandbox=settings.enable_sandbox,
    )
    if sandbox_result is None:
        outcome.sandbox_skipped_reason = "Sandbox indisponible (Docker down ou image absente)."
        return outcome
    outcome.sandbox_exit_code = sandbox_result.exit_code
    outcome.sandbox_stdout = sandbox_result.stdout
    outcome.sandbox_stderr = sandbox_result.stderr
    outcome.sandbox_duration_s = sandbox_result.duration_seconds
    return outcome


def available_guilds() -> list[str]:
    return ["engineering", "research", "creative", "business"]
