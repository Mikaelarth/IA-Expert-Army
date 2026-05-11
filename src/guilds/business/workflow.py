"""BusinessWorkflow — pipeline linéaire PM → Analyst → Legal Reviewer.

Phase 4 MVP — 3 agents séquentiels avec repair loop 1× sur NEEDS_CHANGES.

Le repair loop **ré-exécute les 3 agents** dans l'ordre :
1. PM v2 : reçoit la BA initiale + le verdict Legal → met à jour son plan
   (typiquement pour intégrer les conformity required_actions dans les DoD
   des milestones).
2. BA v2 : analyse en s'appuyant sur le PLAN MIS À JOUR + le feedback Legal.
3. Legal v2 : re-juge sur les v2.

Pourquoi PM aussi (et pas seulement BA, comme la v1) : sur la mission
water-tracker du 2026-05-11 (cf. ADR-009), le Legal demandait que les
livrables conformité (CGU/Privacy/DPA) soient gravés dans la Definition
of Done du plan PM, pas juste recommandés dans l'analyse BA. Repair loop
v1 (BA-only) tournait éternellement à NEEDS_CHANGES car le plan PM
restait figé.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel

from src.core.budget import BudgetController, BudgetExceeded
from src.core.config import Settings, get_settings
from src.core.killswitch import Killswitch, KillswitchEngaged
from src.core.logging import get_logger
from src.guilds.business.agents import BusinessAnalyst, LegalReviewer, ProjectManager
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory, MemoryRecord
from src.memory.vector_memory import VectorMemory
from src.orchestrator.base_agent import AgentInput, AgentOutput

log = get_logger("business_workflow")

VERDICT_APPROVED = "APPROVED"
VERDICT_NEEDS_CHANGES = "NEEDS_CHANGES"
VERDICT_REJECTED = "REJECTED"


class BusinessMissionResult(BaseModel):
    mission_id: UUID
    title: str
    success: bool
    final_verdict: str
    quality_score: float | None
    total_cost_usd: float
    total_duration_seconds: float
    project_plan_yaml: str
    business_analysis_yaml: str
    review_summary: str
    episodes_count: int
    guild: str = "business"


class BusinessWorkflow:
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
        self.pm = ProjectManager(memory, self.settings, **common)
        self.analyst = BusinessAnalyst(memory, self.settings, **common)
        self.legal = LegalReviewer(memory, self.settings, **common)

    async def run(
        self,
        title: str,
        description: str,
        mission_id: UUID | None = None,
    ) -> BusinessMissionResult:
        mission_id = mission_id or uuid4()
        started = datetime.now(UTC)
        outputs: list[AgentOutput] = []
        log.info("business.workflow.start", mission=str(mission_id), title=title)

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

        # Step 1 — PM produit le plan
        pm_out = await self.pm.run(
            AgentInput(
                mission_id=mission_id,
                task=f"Mission business : {title}\n\n{description}\n\n"
                "Produis le plan projet YAML attendu.",
            )
        )
        outputs.append(pm_out)
        if not pm_out.success:
            return self._fail(mission_id, title, started, outputs, "pm.failed", pm_out.error or "")

        # Step 2 — Analyst valide la viabilité économique
        analyst_out = await self.analyst.run(
            AgentInput(
                mission_id=mission_id,
                task="Analyse business : valide ou réfute la viabilité du projet selon ton schéma YAML.",
                context={
                    "mission_description": description,
                    "project_plan_yaml": pm_out.raw_text,
                },
            )
        )
        outputs.append(analyst_out)
        if not analyst_out.success:
            return self._fail(
                mission_id, title, started, outputs, "analyst.failed", analyst_out.error or ""
            )

        # Step 3 — Legal Reviewer juge la conformité
        legal_out = await self.legal.run(
            AgentInput(
                mission_id=mission_id,
                task="Juge la conformité réglementaire et contractuelle. Produis ton verdict YAML.",
                context={
                    "mission_description": description,
                    "project_plan_yaml": pm_out.raw_text,
                    "business_analysis_yaml": analyst_out.raw_text,
                },
            )
        )
        outputs.append(legal_out)
        if not legal_out.success:
            return self._fail(
                mission_id, title, started, outputs, "legal.failed", legal_out.error or ""
            )

        verdict = (legal_out.parsed or {}).get("verdict", VERDICT_REJECTED)

        # Repair loop 1× — PM puis BA puis Legal, dans l'ordre, chacun voit
        # les sorties amont mises à jour. Cf. docstring du module pour la
        # rationale (mission water-tracker, ADR-009).
        if verdict == VERDICT_NEEDS_CHANGES:
            log.info("business.workflow.repair_loop", mission=str(mission_id))

            # Step 1 (repair) — PM met à jour le plan en intégrant le feedback Legal
            pm_out2 = await self.pm.run(
                AgentInput(
                    mission_id=mission_id,
                    task=(
                        "Re-produis le plan projet YAML en intégrant les issues "
                        "conformité signalées par Legal. Grave notamment les "
                        "required_actions de l'analyse BA dans les Definition "
                        "of Done des milestones (ex. CGU, Privacy Policy, DPA "
                        "fournisseurs)."
                    ),
                    context={
                        "mission_description": description,
                        "previous_plan_yaml": pm_out.raw_text,
                        "business_analysis_yaml": analyst_out.raw_text,
                        "legal_feedback_yaml": legal_out.raw_text,
                    },
                )
            )
            outputs.append(pm_out2)
            current_pm = pm_out2 if pm_out2.success else pm_out

            # Step 2 (repair) — BA re-analyse sur le plan MIS À JOUR
            analyst_out2 = await self.analyst.run(
                AgentInput(
                    mission_id=mission_id,
                    task="Re-analyse en intégrant les issues conformité signalées par Legal, "
                    "sur le plan PM mis à jour.",
                    context={
                        "mission_description": description,
                        "project_plan_yaml": current_pm.raw_text,
                        "previous_analysis_yaml": analyst_out.raw_text,
                        "legal_feedback_yaml": legal_out.raw_text,
                    },
                )
            )
            outputs.append(analyst_out2)

            # Step 3 (repair) — Legal re-juge l'ensemble v2
            if analyst_out2.success:
                legal_out2 = await self.legal.run(
                    AgentInput(
                        mission_id=mission_id,
                        task="Juge le nouveau plan et la nouvelle analyse.",
                        context={
                            "mission_description": description,
                            "project_plan_yaml": current_pm.raw_text,
                            "business_analysis_yaml": analyst_out2.raw_text,
                            "previous_review_yaml": legal_out.raw_text,
                        },
                    )
                )
                outputs.append(legal_out2)
                if legal_out2.success:
                    legal_out = legal_out2
                    analyst_out = analyst_out2
                    pm_out = current_pm
                    verdict = (legal_out2.parsed or {}).get("verdict", VERDICT_REJECTED)

        review_data = legal_out.parsed or {}
        quality_score = review_data.get("quality_score")
        review_summary = str(review_data.get("summary", "(no summary)"))

        ended = datetime.now(UTC)
        total_cost = sum(o.cost_usd for o in outputs)
        total_duration = (ended - started).total_seconds()

        result = BusinessMissionResult(
            mission_id=mission_id,
            title=title,
            success=verdict == VERDICT_APPROVED,
            final_verdict=verdict,
            quality_score=quality_score if isinstance(quality_score, (int, float)) else None,
            total_cost_usd=total_cost,
            total_duration_seconds=total_duration,
            project_plan_yaml=pm_out.raw_text,
            business_analysis_yaml=analyst_out.raw_text,
            review_summary=review_summary,
            episodes_count=len(outputs),
        )

        self._write_summary(mission_id, title, description, started, ended, outputs, result)
        self._propagate_score_to_episodes(mission_id, result)

        if self.budget is not None and total_cost > 0:
            try:
                self.budget.record(total_cost)
            except Exception as exc:
                log.warning("business.workflow.budget.record_failed", error=str(exc))

        log.info(
            "business.workflow.end",
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
    ) -> BusinessMissionResult:
        ended = datetime.now(UTC)
        return BusinessMissionResult(
            mission_id=mission_id,
            title=title,
            success=False,
            final_verdict=f"FAILED:{stage}",
            quality_score=None,
            total_cost_usd=sum(o.cost_usd for o in outputs),
            total_duration_seconds=(ended - started).total_seconds(),
            project_plan_yaml="",
            business_analysis_yaml="",
            review_summary=error,
            episodes_count=len(outputs),
        )

    def _propagate_score_to_episodes(self, mission_id: UUID, result: BusinessMissionResult) -> None:
        if result.quality_score is None and result.final_verdict == "":
            return
        for path in self.memory.list_episodes(mission_id):
            try:
                self.memory.update_episode_metadata(
                    path,
                    quality_score=result.quality_score,
                    final_verdict=result.final_verdict,
                    mission_title=result.title,
                    guild="business",
                )
            except OSError as exc:
                log.warning("business.workflow.score_propagation.failed", error=str(exc))

    def _write_summary(
        self,
        mission_id: UUID,
        title: str,
        description: str,
        started: datetime,
        ended: datetime,
        outputs: list[AgentOutput],
        result: BusinessMissionResult,
    ) -> None:
        body_lines = [
            f"# {title}",
            "",
            f"**Mission ID :** `{mission_id}`",
            "**Guilde :** Business",
            f"**Status :** {'✅ ' if result.success else '❌ '}{result.final_verdict}",
            f"**Quality score :** {result.quality_score if result.quality_score is not None else 'n/a'}",
            f"**Coût total :** ${result.total_cost_usd:.4f}",
            f"**Durée :** {result.total_duration_seconds:.2f} s",
            "",
            "## Description",
            "",
            description,
            "",
            "## Résumé du Legal Reviewer",
            "",
            result.review_summary,
            "",
            "## Plan projet (PM)",
            "",
            result.project_plan_yaml[:3000]
            + (
                "\n\n*…[tronqué dans le résumé, voir l'épisode pm pour la version complète]*"
                if len(result.project_plan_yaml) > 3000
                else ""
            ),
            "",
            "## Analyse business (BA)",
            "",
            result.business_analysis_yaml[:3000]
            + (
                "\n\n*…[tronqué, voir l'épisode analyst]*"
                if len(result.business_analysis_yaml) > 3000
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
                "guild": "business",
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
