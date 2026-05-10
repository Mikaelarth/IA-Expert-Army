"""CreativeWorkflow — pipeline linéaire Strategist → Copywriter → Editor.

Phase 4 MVP — 3 agents séquentiels avec repair loop 1× sur NEEDS_CHANGES.
Phase 4+ : ajouter Marketing Specialist (CTA + SEO) et Visual Designer
(prompts d'images) en parallèle entre Strategist et Editor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel

from src.core.budget import BudgetController, BudgetExceeded
from src.core.config import Settings, get_settings
from src.core.killswitch import Killswitch, KillswitchEngaged
from src.core.logging import get_logger
from src.guilds.creative.agents import ContentStrategist, Copywriter, Editor
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory, MemoryRecord
from src.memory.vector_memory import VectorMemory
from src.orchestrator.base_agent import AgentInput, AgentOutput

log = get_logger("creative_workflow")

VERDICT_APPROVED = "APPROVED"
VERDICT_NEEDS_CHANGES = "NEEDS_CHANGES"
VERDICT_REJECTED = "REJECTED"


class CreativeMissionResult(BaseModel):
    mission_id: UUID
    title: str
    success: bool
    final_verdict: str
    quality_score: float | None
    total_cost_usd: float
    total_duration_seconds: float
    final_text_markdown: str
    review_summary: str
    episodes_count: int
    guild: str = "creative"


class CreativeWorkflow:
    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        vector_memory: VectorMemory | None = None,
        skills_library: SkillsLibrary | None = None,
        budget: BudgetController | None = None,
        killswitch: Killswitch | None = None,
    ) -> None:
        self.memory = memory
        self.vector_memory = vector_memory
        self.skills_library = skills_library
        self.settings = settings or get_settings()
        self.budget = budget
        self.killswitch = killswitch
        common = {"vector_memory": vector_memory, "skills_library": skills_library}
        self.strategist = ContentStrategist(memory, self.settings, **common)
        self.copywriter = Copywriter(memory, self.settings, **common)
        self.editor = Editor(memory, self.settings, **common)

    async def run(
        self,
        title: str,
        description: str,
        mission_id: UUID | None = None,
    ) -> CreativeMissionResult:
        mission_id = mission_id or uuid4()
        started = datetime.now(UTC)
        outputs: list[AgentOutput] = []
        log.info("creative.workflow.start", mission=str(mission_id), title=title)

        # Garde-fous
        if self.killswitch is not None:
            try:
                self.killswitch.assert_clear()
            except KillswitchEngaged as exc:
                return self._fail(
                    mission_id, title, started, outputs, "killswitch.engaged", str(exc)
                )
        if self.budget is not None:
            try:
                self.budget.assert_can_proceed(estimated_cost=0.0)
            except BudgetExceeded as exc:
                return self._fail(mission_id, title, started, outputs, "budget.exceeded", str(exc))

        # Step 1 — Strategist produit le brief
        strat_out = await self.strategist.run(
            AgentInput(
                mission_id=mission_id,
                task=f"Mission de création : {title}\n\n{description}\n\n"
                "Produis le brief stratégique YAML attendu.",
            )
        )
        outputs.append(strat_out)
        if not strat_out.success:
            return self._fail(
                mission_id, title, started, outputs, "strategist.failed", strat_out.error or ""
            )

        # Step 2 — Copywriter rédige
        copy_out = await self.copywriter.run(
            AgentInput(
                mission_id=mission_id,
                task="Rédige le texte final selon le brief stratégique.",
                context={
                    "mission_description": description,
                    "strategy_brief_yaml": strat_out.raw_text,
                },
            )
        )
        outputs.append(copy_out)
        if not copy_out.success:
            return self._fail(
                mission_id, title, started, outputs, "copywriter.failed", copy_out.error or ""
            )

        # Step 3 — Editor juge
        editor_out = await self.editor.run(
            AgentInput(
                mission_id=mission_id,
                task="Juge la qualité éditoriale du texte selon tes critères. Produis ton verdict YAML.",
                context={
                    "mission_description": description,
                    "strategy_brief_yaml": strat_out.raw_text,
                    "final_text_markdown": copy_out.raw_text,
                },
            )
        )
        outputs.append(editor_out)
        if not editor_out.success:
            return self._fail(
                mission_id, title, started, outputs, "editor.failed", editor_out.error or ""
            )

        verdict = (editor_out.parsed or {}).get("verdict", VERDICT_REJECTED)

        # Repair loop 1×
        if verdict == VERDICT_NEEDS_CHANGES:
            log.info("creative.workflow.repair_loop", mission=str(mission_id))
            copy_out2 = await self.copywriter.run(
                AgentInput(
                    mission_id=mission_id,
                    task="Réécris le texte en intégrant le feedback de l'Editor.",
                    context={
                        "mission_description": description,
                        "strategy_brief_yaml": strat_out.raw_text,
                        "previous_text_markdown": copy_out.raw_text,
                        "editor_feedback_yaml": editor_out.raw_text,
                    },
                )
            )
            outputs.append(copy_out2)
            if copy_out2.success:
                editor_out2 = await self.editor.run(
                    AgentInput(
                        mission_id=mission_id,
                        task="Juge le nouveau texte.",
                        context={
                            "mission_description": description,
                            "strategy_brief_yaml": strat_out.raw_text,
                            "final_text_markdown": copy_out2.raw_text,
                            "previous_review_yaml": editor_out.raw_text,
                        },
                    )
                )
                outputs.append(editor_out2)
                if editor_out2.success:
                    editor_out = editor_out2
                    copy_out = copy_out2
                    verdict = (editor_out2.parsed or {}).get("verdict", VERDICT_REJECTED)

        review_data = editor_out.parsed or {}
        quality_score = review_data.get("quality_score")
        review_summary = str(review_data.get("summary", "(no summary)"))

        ended = datetime.now(UTC)
        total_cost = sum(o.cost_usd for o in outputs)
        total_duration = (ended - started).total_seconds()

        result = CreativeMissionResult(
            mission_id=mission_id,
            title=title,
            success=verdict == VERDICT_APPROVED,
            final_verdict=verdict,
            quality_score=quality_score if isinstance(quality_score, (int, float)) else None,
            total_cost_usd=total_cost,
            total_duration_seconds=total_duration,
            final_text_markdown=copy_out.raw_text,
            review_summary=review_summary,
            episodes_count=len(outputs),
        )

        self._write_summary(mission_id, title, description, started, ended, outputs, result)
        self._propagate_score_to_episodes(mission_id, result)

        if self.budget is not None and total_cost > 0:
            try:
                self.budget.record(total_cost)
            except Exception as exc:
                log.warning("creative.workflow.budget.record_failed", error=str(exc))

        log.info(
            "creative.workflow.end",
            mission=str(mission_id),
            verdict=verdict,
            cost_usd=round(total_cost, 6),
            duration_s=round(total_duration, 2),
        )
        return result

    def _fail(
        self,
        mission_id: UUID,
        title: str,
        started: datetime,
        outputs: list[AgentOutput],
        stage: str,
        error: str,
    ) -> CreativeMissionResult:
        ended = datetime.now(UTC)
        return CreativeMissionResult(
            mission_id=mission_id,
            title=title,
            success=False,
            final_verdict=f"FAILED:{stage}",
            quality_score=None,
            total_cost_usd=sum(o.cost_usd for o in outputs),
            total_duration_seconds=(ended - started).total_seconds(),
            final_text_markdown="",
            review_summary=error,
            episodes_count=len(outputs),
        )

    def _propagate_score_to_episodes(self, mission_id: UUID, result: CreativeMissionResult) -> None:
        if result.quality_score is None and result.final_verdict == "":
            return
        for path in self.memory.list_episodes(mission_id):
            try:
                self.memory.update_episode_metadata(
                    path,
                    quality_score=result.quality_score,
                    final_verdict=result.final_verdict,
                    mission_title=result.title,
                    guild="creative",
                )
            except OSError as exc:
                log.warning("creative.workflow.score_propagation.failed", error=str(exc))

    def _write_summary(
        self,
        mission_id: UUID,
        title: str,
        description: str,
        started: datetime,
        ended: datetime,
        outputs: list[AgentOutput],
        result: CreativeMissionResult,
    ) -> None:
        body_lines = [
            f"# {title}",
            "",
            f"**Mission ID :** `{mission_id}`",
            "**Guilde :** Creative",
            f"**Status :** {'✅ ' if result.success else '❌ '}{result.final_verdict}",
            f"**Quality score :** {result.quality_score if result.quality_score is not None else 'n/a'}",
            f"**Coût total :** ${result.total_cost_usd:.4f}",
            f"**Durée :** {result.total_duration_seconds:.2f} s",
            "",
            "## Description",
            "",
            description,
            "",
            "## Résumé de l'Editor",
            "",
            result.review_summary,
            "",
            "## Texte final produit",
            "",
            result.final_text_markdown[:5000]
            + (
                "\n\n*…[tronqué dans le résumé, voir l'épisode copywriter pour le texte complet]*"
                if len(result.final_text_markdown) > 5000
                else ""
            ),
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
                "guild": "creative",
                "started_at": started.isoformat(),
                "ended_at": ended.isoformat(),
                "success": result.success,
                "final_verdict": result.final_verdict,
                "quality_score": result.quality_score,
                "total_cost_usd": round(result.total_cost_usd, 6),
                "total_duration_seconds": round(result.total_duration_seconds, 3),
            },
            body="\n".join(body_lines),
        )
        self.memory.write_mission_summary(mission_id, record)
