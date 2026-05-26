"""ResearchWorkflow — pipeline linéaire de la Guild Research (Phase 4 MVP).

Pattern : Research Lead → Tech Watch → Document Synthesizer → Research Reviewer.

Le repair loop (max 1×) ré-exécute **les 4 agents** dans l'ordre sur
NEEDS_CHANGES, pas seulement Synth + Reviewer comme la v1 (avant Sprint WW).

Pourquoi inclure Lead + Watch : si le Reviewer flagge un problème de
cadrage (« le plan initial n'a pas couvert la sous-question X » ou
« les findings sont biaisés/superficiels »), le Synthesizer seul ne peut
pas remédier — sa matière première amont est figée. Pattern méta-leçon
appliqué symétriquement après Sprint PP (Business) et SS (Engineering).

Phase 4+ : parallélisme Tech Watch / sources, web MCP, Knowledge Curator.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel

from src.core.budget import BudgetController, BudgetExceeded
from src.core.checkpoint import CheckpointStore
from src.core.config import Settings, get_settings
from src.core.killswitch import Killswitch, KillswitchEngaged
from src.core.logging import get_logger
from src.guilds.research.agents import (
    DocumentSynthesizer,
    ResearchLead,
    ResearchReviewer,
    TechWatch,
)
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory, MemoryRecord
from src.memory.vector_memory import VectorMemory
from src.orchestrator._checkpoint_helper import run_with_checkpoint
from src.orchestrator.base_agent import AgentInput, AgentOutput
from src.orchestrator.progress import ProgressCallback, emit, make_event

log = get_logger("research_workflow")

VERDICT_APPROVED = "APPROVED"
VERDICT_NEEDS_CHANGES = "NEEDS_CHANGES"
VERDICT_REJECTED = "REJECTED"


class ResearchMissionResult(BaseModel):
    mission_id: UUID
    title: str
    success: bool
    final_verdict: str
    quality_score: float | None
    total_cost_usd: float
    total_duration_seconds: float
    synthesis_markdown: str
    review_summary: str
    episodes_count: int
    guild: str = "research"


class ResearchWorkflow:
    """Pipeline Research-spécifique. Compose 4 agents (sans le Chief Orchestrator,
    qui décide en amont quelle guilde activer)."""

    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        vector_memory: VectorMemory | None = None,
        skills_library: SkillsLibrary | None = None,
        budget: BudgetController | None = None,
        killswitch: Killswitch | None = None,
        checkpoint_store: CheckpointStore | None = None,
    ) -> None:
        self.memory = memory
        self.vector_memory = vector_memory
        self.skills_library = skills_library
        self.settings = settings or get_settings()
        self.budget = budget
        self.killswitch = killswitch
        # v0.9.5 — F1 checkpoint resume étendu à Research
        self.checkpoint_store = checkpoint_store
        common = {"vector_memory": vector_memory, "skills_library": skills_library}
        self.lead = ResearchLead(memory, self.settings, **common)
        self.watch = TechWatch(memory, self.settings, **common)
        self.synth = DocumentSynthesizer(memory, self.settings, **common)
        self.reviewer = ResearchReviewer(memory, self.settings, **common)

    async def run(
        self,
        title: str,
        description: str,
        mission_id: UUID | None = None,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> ResearchMissionResult:
        mission_id = mission_id or uuid4()
        started = datetime.now(UTC)
        outputs: list[AgentOutput] = []
        log.info("research.workflow.start", mission=str(mission_id), title=title)
        emit(
            on_progress,
            make_event(
                "mission_started",
                f"Mission Research démarrée : {title}",
                mission_id=str(mission_id),
                title=title,
                guild="research",
            ),
        )

        # Garde-fous (au cas où on appelle ce workflow directement)
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

        # Step 1 — Lead produit le plan de recherche
        lead_out = await run_with_checkpoint(
            self.lead,
            AgentInput(
                mission_id=mission_id,
                task=f"Mission de recherche : {title}\n\n{description}\n\n"
                "Produis le plan de recherche YAML attendu.",
            ),
            step_index=0,
            agent_name="research_lead",
            checkpoint_store=self.checkpoint_store,
            mission_id=mission_id,
            on_progress=on_progress,
        )
        outputs.append(lead_out)
        if not lead_out.success:
            return self._fail(
                mission_id, title, started, outputs, "research_lead.failed", lead_out.error or ""
            )

        # Step 2 — Tech Watch fouille pour chaque sous-question
        watch_out = await run_with_checkpoint(
            self.watch,
            AgentInput(
                mission_id=mission_id,
                task=f"Pour chaque sous-question du plan ci-dessous, produis tes findings YAML.\n\n"
                f"Plan de recherche :\n{lead_out.raw_text}",
                context={"mission_description": description},
            ),
            step_index=1,
            agent_name="tech_watch",
            checkpoint_store=self.checkpoint_store,
            mission_id=mission_id,
            on_progress=on_progress,
        )
        outputs.append(watch_out)
        if not watch_out.success:
            return self._fail(
                mission_id, title, started, outputs, "tech_watch.failed", watch_out.error or ""
            )

        # Step 3 — Synthesizer rédige
        synth_out = await run_with_checkpoint(
            self.synth,
            AgentInput(
                mission_id=mission_id,
                task="Rédige la synthèse Markdown qui répond à la mission.",
                context={
                    "mission_description": description,
                    "research_plan_yaml": lead_out.raw_text,
                    "findings_yaml": watch_out.raw_text,
                },
            ),
            step_index=2,
            agent_name="document_synthesizer",
            checkpoint_store=self.checkpoint_store,
            mission_id=mission_id,
            on_progress=on_progress,
        )
        outputs.append(synth_out)
        if not synth_out.success:
            return self._fail(
                mission_id, title, started, outputs, "synthesizer.failed", synth_out.error or ""
            )

        # Step 4 — Reviewer juge
        review_out = await run_with_checkpoint(
            self.reviewer,
            AgentInput(
                mission_id=mission_id,
                task="Juge la qualité de la synthèse selon tes critères. Produis ton verdict YAML.",
                context={
                    "mission_description": description,
                    "research_plan_yaml": lead_out.raw_text,
                    "findings_yaml": watch_out.raw_text,
                    "synthesis_markdown": synth_out.raw_text,
                },
            ),
            step_index=3,
            agent_name="research_reviewer",
            checkpoint_store=self.checkpoint_store,
            mission_id=mission_id,
            on_progress=on_progress,
        )
        outputs.append(review_out)
        if not review_out.success:
            return self._fail(
                mission_id,
                title,
                started,
                outputs,
                "research_reviewer.failed",
                review_out.error or "",
            )

        verdict = (review_out.parsed or {}).get("verdict", VERDICT_REJECTED)

        # Repair loop (max 1×) — Lead → Watch → Synth → Reviewer dans l'ordre.
        # Pattern méta-leçon Sprint PP/SS : chaque producteur upstream doit
        # pouvoir réagir au feedback du reviewer, sinon oscillation possible.
        if verdict == VERDICT_NEEDS_CHANGES:
            log.info("research.workflow.repair_loop", mission=str(mission_id))
            emit(
                on_progress,
                make_event(
                    "repair_loop_started",
                    "Repair loop Research démarré (Lead → Watch → Synth → Reviewer)",
                    mission_id=str(mission_id),
                ),
            )

            # Step 1 (repair) — Lead révise éventuellement le plan
            lead_out2 = await run_with_checkpoint(
                self.lead,
                AgentInput(
                    mission_id=mission_id,
                    task=f"Mission de recherche : {title}\n\n{description}\n\n"
                    "Revoie le plan de recherche en intégrant le feedback Reviewer. "
                    "Si le plan initial cadre déjà bien les sous-questions, "
                    "re-produis-le inchangé ; sinon ajuste (ex. ajouter une "
                    "sous-question manquée, reformuler une zone floue).",
                    context={
                        "previous_plan_yaml": lead_out.raw_text,
                        "previous_findings_yaml": watch_out.raw_text,
                        "previous_synthesis_md": synth_out.raw_text,
                        "review_feedback_yaml": review_out.raw_text,
                    },
                ),
                step_index=4,
                agent_name="research_lead",
                checkpoint_store=self.checkpoint_store,
                mission_id=mission_id,
                on_progress=on_progress,
            )
            outputs.append(lead_out2)
            current_lead = lead_out2 if lead_out2.success else lead_out

            # Step 2 (repair) — Watch étend/corrige les findings sur le plan mis à jour
            watch_out2 = await run_with_checkpoint(
                self.watch,
                AgentInput(
                    mission_id=mission_id,
                    task="Pour chaque sous-question du plan ci-dessous, "
                    "produis tes findings YAML en intégrant le feedback "
                    "Reviewer (sources insuffisantes, biais à corriger, etc.).\n\n"
                    f"Plan de recherche :\n{current_lead.raw_text}",
                    context={
                        "mission_description": description,
                        "previous_findings_yaml": watch_out.raw_text,
                        "review_feedback_yaml": review_out.raw_text,
                    },
                ),
                step_index=5,
                agent_name="tech_watch",
                checkpoint_store=self.checkpoint_store,
                mission_id=mission_id,
                on_progress=on_progress,
            )
            outputs.append(watch_out2)
            current_watch = watch_out2 if watch_out2.success else watch_out

            # Step 3 (repair) — Synth re-rédige avec les inputs amont mis à jour
            synth_out2 = await run_with_checkpoint(
                self.synth,
                AgentInput(
                    mission_id=mission_id,
                    task="Re-rédige la synthèse en intégrant le feedback du Reviewer "
                    "et les findings mis à jour.",
                    context={
                        "mission_description": description,
                        "research_plan_yaml": current_lead.raw_text,
                        "findings_yaml": current_watch.raw_text,
                        "previous_synthesis_md": synth_out.raw_text,
                        "review_feedback_yaml": review_out.raw_text,
                    },
                ),
                step_index=6,
                agent_name="document_synthesizer",
                checkpoint_store=self.checkpoint_store,
                mission_id=mission_id,
                on_progress=on_progress,
            )
            outputs.append(synth_out2)

            # Step 4 (repair) — Reviewer juge l'ensemble v2
            if synth_out2.success:
                review_out2 = await run_with_checkpoint(
                    self.reviewer,
                    AgentInput(
                        mission_id=mission_id,
                        task="Juge la nouvelle synthèse, le plan révisé et les findings mis à jour.",
                        context={
                            "mission_description": description,
                            "research_plan_yaml": current_lead.raw_text,
                            "findings_yaml": current_watch.raw_text,
                            "synthesis_markdown": synth_out2.raw_text,
                            "previous_review_yaml": review_out.raw_text,
                        },
                    ),
                    step_index=7,
                    agent_name="research_reviewer",
                    checkpoint_store=self.checkpoint_store,
                    mission_id=mission_id,
                    on_progress=on_progress,
                )
                outputs.append(review_out2)
                if review_out2.success:
                    review_out = review_out2
                    synth_out = synth_out2
                    watch_out = current_watch
                    lead_out = current_lead
                    verdict = (review_out2.parsed or {}).get("verdict", VERDICT_REJECTED)

        review_data = review_out.parsed or {}
        quality_score = review_data.get("quality_score")
        review_summary = str(review_data.get("summary", "(no summary)"))

        ended = datetime.now(UTC)
        total_cost = sum(o.cost_usd for o in outputs)
        total_duration = (ended - started).total_seconds()

        result = ResearchMissionResult(
            mission_id=mission_id,
            title=title,
            success=verdict == VERDICT_APPROVED,
            final_verdict=verdict,
            quality_score=quality_score if isinstance(quality_score, (int, float)) else None,
            total_cost_usd=total_cost,
            total_duration_seconds=total_duration,
            synthesis_markdown=synth_out.raw_text,
            review_summary=review_summary,
            episodes_count=len(outputs),
        )

        self._write_summary(mission_id, title, description, started, ended, outputs, result)
        self._propagate_score_to_episodes(mission_id, result)

        if self.budget is not None and total_cost > 0:
            try:
                self.budget.record(total_cost)
            except Exception as exc:
                log.warning("research.workflow.budget.record_failed", error=str(exc))

        log.info(
            "research.workflow.end",
            mission=str(mission_id),
            verdict=verdict,
            cost_usd=round(total_cost, 6),
            duration_s=round(total_duration, 2),
        )

        # v0.9.5 — Cleanup checkpoints + mission_completed event
        if self.checkpoint_store is not None:
            self.checkpoint_store.clear(str(mission_id))

        emit(
            on_progress,
            make_event(
                "mission_completed",
                f"Mission Research terminée — verdict {verdict} (score {quality_score})",
                mission_id=str(mission_id),
                verdict=verdict,
                quality_score=quality_score,
                total_cost_usd=total_cost,
                total_duration_seconds=total_duration,
            ),
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
    ) -> ResearchMissionResult:
        ended = datetime.now(UTC)
        return ResearchMissionResult(
            mission_id=mission_id,
            title=title,
            success=False,
            final_verdict=f"FAILED:{stage}",
            quality_score=None,
            total_cost_usd=sum(o.cost_usd for o in outputs),
            total_duration_seconds=(ended - started).total_seconds(),
            synthesis_markdown="",
            review_summary=error,
            episodes_count=len(outputs),
        )

    def _propagate_score_to_episodes(self, mission_id: UUID, result: ResearchMissionResult) -> None:
        if result.quality_score is None and result.final_verdict == "":
            return
        for path in self.memory.list_episodes(mission_id):
            try:
                self.memory.update_episode_metadata(
                    path,
                    quality_score=result.quality_score,
                    final_verdict=result.final_verdict,
                    mission_title=result.title,
                    guild="research",
                )
            except OSError as exc:
                log.warning("research.workflow.score_propagation.failed", error=str(exc))

    def _write_summary(
        self,
        mission_id: UUID,
        title: str,
        description: str,
        started: datetime,
        ended: datetime,
        outputs: list[AgentOutput],
        result: ResearchMissionResult,
    ) -> None:
        body_lines = [
            f"# {title}",
            "",
            f"**Mission ID :** `{mission_id}`",
            "**Guilde :** Research",
            f"**Status :** {'✅ ' if result.success else '❌ '}{result.final_verdict}",
            f"**Quality score :** {result.quality_score if result.quality_score is not None else 'n/a'}",
            f"**Coût total :** ${result.total_cost_usd:.4f}",
            f"**Durée :** {result.total_duration_seconds:.2f} s",
            "",
            "## Description",
            "",
            description,
            "",
            "## Résumé du Reviewer",
            "",
            result.review_summary,
            "",
            "## Synthèse produite",
            "",
            result.synthesis_markdown[:5000]
            + (
                "\n\n*…[tronqué dans le résumé, voir l'épisode synthesizer pour le texte complet]*"
                if len(result.synthesis_markdown) > 5000
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
                "guild": "research",
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
