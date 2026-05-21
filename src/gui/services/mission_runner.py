"""mission_runner — wrappers MissionRouter pour la GUI.

Encapsule la création du MissionRouter (FileMemory + VectorMemory + SkillsLibrary)
et l'exécution d'une mission avec gestion d'erreurs et options --apply/--validate.

Le lancement reste synchrone (`asyncio.run`) côté caller (button handler
Streamlit). Pas de streaming live des logs en MVP (cf. ADR-026).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from src.core.budget import BudgetController
from src.core.config import get_settings
from src.core.killswitch import Killswitch
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory
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
    return MissionRouter(
        memory=memory,
        settings=settings,
        vector_memory=vector_memory_episodes,
        skills_library=skills_library,
        budget=budget,
        killswitch=killswitch,
    )


def run_mission_sync(req: MissionRunRequest) -> MissionRunOutcome:
    """Lance une mission et applique optionnellement les fichiers + sandbox.

    Synchrone du point de vue du caller (le `asyncio.run` est interne).
    Renvoie un MissionRunOutcome consolidé pour l'affichage.
    """
    router = build_router()
    result: UnifiedMissionResult = asyncio.run(
        router.run(
            title=req.title,
            description=req.description,
            force_guild=req.force_guild,
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
