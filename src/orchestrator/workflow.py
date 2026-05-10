"""Workflow MVP — chaîne linéaire Orchestrator → Architect → Developer → Reviewer.

Phase 1 : pas de parallélisme, pas de multi-subtasks, pas de Quality Guardian séparé.
Boucle de réparation maximum 1 fois si Reviewer demande des changements.

Phase 3+ : ce module sera remplacé par un graphe LangGraph stateful.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel

from src.core.config import Settings, get_settings
from src.core.logging import get_logger
from src.memory.file_memory import FileMemory, MemoryRecord
from src.orchestrator.agents import (
    BackendDeveloper,
    ChiefOrchestrator,
    CodeReviewer,
    SoftwareArchitect,
)
from src.orchestrator.base_agent import AgentInput, AgentOutput

log = get_logger("workflow")

VERDICT_APPROVED = "APPROVED"
VERDICT_NEEDS_CHANGES = "NEEDS_CHANGES"
VERDICT_REJECTED = "REJECTED"


class MissionResult(BaseModel):
    mission_id: UUID
    title: str
    success: bool
    final_verdict: str
    quality_score: float | None
    total_cost_usd: float
    total_duration_seconds: float
    files_produced: list[dict[str, str]]
    review_summary: str
    episodes_count: int


class Workflow:
    """Pipeline linéaire de la Phase 1.

    Compose 4 agents et orchestre leur exécution sur une mission unique.
    Tous les épisodes sont écrits dans la mémoire fichier passée en paramètre.
    """

    def __init__(self, memory: FileMemory, settings: Settings | None = None) -> None:
        self.memory = memory
        self.settings = settings or get_settings()
        self.orchestrator = ChiefOrchestrator(memory, self.settings)
        self.architect = SoftwareArchitect(memory, self.settings)
        self.developer = BackendDeveloper(memory, self.settings)
        self.reviewer = CodeReviewer(memory, self.settings)

    async def run(self, title: str, description: str) -> MissionResult:
        mission_id = uuid4()
        started = datetime.now(UTC)
        outputs: list[AgentOutput] = []

        log.info("workflow.start", mission=str(mission_id), title=title)

        # Step 1 — Orchestrator décompose
        orch_out = await self.orchestrator.run(
            AgentInput(
                mission_id=mission_id,
                task=f"Mission : {title}\n\n{description}\n\nProduis la décomposition au format YAML attendu.",
            )
        )
        outputs.append(orch_out)
        if not orch_out.success:
            return self._fail(mission_id, title, started, outputs, "orchestrator.failed", orch_out.error or "")

        decomposition = orch_out.parsed or {}
        first_task = self._first_subtask(decomposition) or description

        # Step 2 — Architect conçoit
        arch_out = await self.architect.run(
            AgentInput(
                mission_id=mission_id,
                task=first_task,
                context={"mission": description, "decomposition_yaml": orch_out.raw_text},
            )
        )
        outputs.append(arch_out)
        if not arch_out.success:
            return self._fail(mission_id, title, started, outputs, "architect.failed", arch_out.error or "")

        # Step 3 — Developer code
        dev_out = await self.developer.run(
            AgentInput(
                mission_id=mission_id,
                task=first_task,
                context={"architecture_proposal_yaml": arch_out.raw_text},
            )
        )
        outputs.append(dev_out)
        if not dev_out.success:
            return self._fail(mission_id, title, started, outputs, "developer.failed", dev_out.error or "")

        # Step 4 — Reviewer juge
        review_out = await self.reviewer.run(
            AgentInput(
                mission_id=mission_id,
                task=first_task,
                context={
                    "architecture_proposal_yaml": arch_out.raw_text,
                    "developer_output_md": dev_out.raw_text,
                },
            )
        )
        outputs.append(review_out)
        if not review_out.success:
            return self._fail(mission_id, title, started, outputs, "reviewer.failed", review_out.error or "")

        verdict = (review_out.parsed or {}).get("verdict", VERDICT_REJECTED)

        # Optional repair loop (max once)
        if verdict == VERDICT_NEEDS_CHANGES:
            log.info("workflow.repair_loop", mission=str(mission_id))
            dev_out2 = await self.developer.run(
                AgentInput(
                    mission_id=mission_id,
                    task=first_task,
                    context={
                        "architecture_proposal_yaml": arch_out.raw_text,
                        "previous_implementation_md": dev_out.raw_text,
                        "review_feedback_yaml": review_out.raw_text,
                        "instruction": "Corrige les issues remontées par le Reviewer puis re-livre la version complète.",
                    },
                )
            )
            outputs.append(dev_out2)
            if dev_out2.success:
                review_out2 = await self.reviewer.run(
                    AgentInput(
                        mission_id=mission_id,
                        task=first_task,
                        context={
                            "architecture_proposal_yaml": arch_out.raw_text,
                            "developer_output_md": dev_out2.raw_text,
                            "previous_review_yaml": review_out.raw_text,
                        },
                    )
                )
                outputs.append(review_out2)
                if review_out2.success:
                    review_out = review_out2
                    dev_out = dev_out2
                    verdict = (review_out2.parsed or {}).get("verdict", VERDICT_REJECTED)

        review_data = review_out.parsed or {}
        quality_score = review_data.get("quality_score")
        review_summary = review_data.get("summary", "(no summary)")
        files = dev_out.parsed if isinstance(dev_out.parsed, list) else []

        ended = datetime.now(UTC)
        total_cost = sum(o.cost_usd for o in outputs)
        total_duration = (ended - started).total_seconds()

        result = MissionResult(
            mission_id=mission_id,
            title=title,
            success=verdict == VERDICT_APPROVED,
            final_verdict=verdict,
            quality_score=quality_score if isinstance(quality_score, (int, float)) else None,
            total_cost_usd=total_cost,
            total_duration_seconds=total_duration,
            files_produced=files,
            review_summary=str(review_summary),
            episodes_count=len(outputs),
        )

        self._write_summary(mission_id, title, description, started, ended, outputs, result)
        log.info(
            "workflow.end",
            mission=str(mission_id),
            verdict=verdict,
            cost_usd=round(total_cost, 6),
            duration_s=round(total_duration, 2),
        )
        return result

    def _first_subtask(self, decomposition: dict) -> str | None:
        tasks = decomposition.get("decomposition") or decomposition.get("subtasks")
        if isinstance(tasks, list) and tasks:
            first = tasks[0]
            if isinstance(first, dict):
                return first.get("title") or first.get("deliverable")
        return None

    def _fail(
        self,
        mission_id: UUID,
        title: str,
        started: datetime,
        outputs: list[AgentOutput],
        stage: str,
        error: str,
    ) -> MissionResult:
        ended = datetime.now(UTC)
        return MissionResult(
            mission_id=mission_id,
            title=title,
            success=False,
            final_verdict=f"FAILED:{stage}",
            quality_score=None,
            total_cost_usd=sum(o.cost_usd for o in outputs),
            total_duration_seconds=(ended - started).total_seconds(),
            files_produced=[],
            review_summary=error,
            episodes_count=len(outputs),
        )

    def _write_summary(
        self,
        mission_id: UUID,
        title: str,
        description: str,
        started: datetime,
        ended: datetime,
        outputs: list[AgentOutput],
        result: MissionResult,
    ) -> None:
        body_lines = [
            f"# {title}",
            "",
            f"**Mission ID :** `{mission_id}`",
            f"**Status :** {'✅ ' if result.success else '❌ '}{result.final_verdict}",
            f"**Quality score :** {result.quality_score if result.quality_score is not None else 'n/a'}",
            f"**Coût total :** ${result.total_cost_usd:.4f}",
            f"**Durée :** {result.total_duration_seconds:.2f} s",
            f"**Fichiers produits :** {len(result.files_produced)}",
            "",
            "## Description",
            "",
            description,
            "",
            "## Résumé du Reviewer",
            "",
            result.review_summary,
            "",
            "## Épisodes",
            "",
        ]
        for o in outputs:
            body_lines.append(
                f"- **{o.agent_name}** — {'ok' if o.success else 'fail'} · "
                f"in={o.tokens_in} out={o.tokens_out} cost=${o.cost_usd:.4f} "
                f"dur={o.duration_seconds:.2f}s"
            )
        record = MemoryRecord(
            metadata={
                "mission_id": str(mission_id),
                "title": title,
                "started_at": started.isoformat(),
                "ended_at": ended.isoformat(),
                "success": result.success,
                "final_verdict": result.final_verdict,
                "quality_score": result.quality_score,
                "total_cost_usd": round(result.total_cost_usd, 6),
                "total_duration_seconds": round(result.total_duration_seconds, 3),
                "files_produced_count": len(result.files_produced),
            },
            body="\n".join(body_lines),
        )
        self.memory.write_mission_summary(mission_id, record)
