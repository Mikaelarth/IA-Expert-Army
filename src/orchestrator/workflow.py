"""Workflow MVP — chaîne linéaire Orchestrator → Architect → Developer → Reviewer.

Phase 1 : pas de parallélisme, pas de multi-subtasks, pas de Quality Guardian séparé.

Le repair loop (max 1×) ré-exécute **Architect + Developer + Reviewer** sur
NEEDS_CHANGES, pas seulement le Developer comme la v1 (avant Sprint SS).

Pourquoi inclure l'Architect : un verdict NEEDS_CHANGES du Reviewer peut
porter sur l'architecture (mauvaise abstraction, séparation manquante,
faille design) — dans ce cas, le Developer seul ne peut pas corriger car
sa proposition d'architecture amont est figée. Pattern méta-leçon
Sprint PP (BusinessWorkflow) appliqué ici symétriquement.

v0.8.0 — câblage CheckpointStore (F1) + ProgressEvent emission (F2).

Phase 3+ : ce module sera remplacé par un graphe LangGraph stateful.

# audit: ignore FILE_TOO_LONG -- 506 lignes acceptées : workflow nominal +
# repair loop + propagation score + summary writer + helpers — cohérence
# fonctionnelle d'un seul pipeline guilde Engineering. Split par phase
# (run/repair/persist) ferait perdre la lisibilité linéaire qui fait
# justement la valeur de ce fichier.
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
from src.learning.missions_rag import MissionsRAG
from src.learning.prompt_ab import PromptAB
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory, MemoryRecord
from src.memory.vector_memory import VectorMemory
from src.orchestrator._checkpoint_helper import run_with_checkpoint
from src.orchestrator.agents import (
    BackendDeveloper,
    ChiefOrchestrator,
    CodeReviewer,
    SecurityAuditor,
    SoftwareArchitect,
)
from src.orchestrator.agents.security_auditor import has_downgrade_findings
from src.orchestrator.base_agent import AgentInput, AgentOutput
from src.orchestrator.progress import ProgressCallback, emit, make_event

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

    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        vector_memory: VectorMemory | None = None,
        skills_library: SkillsLibrary | None = None,
        budget: BudgetController | None = None,
        killswitch: Killswitch | None = None,
        checkpoint_store: CheckpointStore | None = None,
        missions_rag: MissionsRAG | None = None,
        prompt_ab: PromptAB | None = None,
    ) -> None:
        self.memory = memory
        self.vector_memory = vector_memory
        self.skills_library = skills_library
        self.settings = settings or get_settings()
        self.budget = budget
        self.killswitch = killswitch
        self.checkpoint_store = checkpoint_store
        # v0.9.0 A1 — RAG sur missions passées. Si fourni : (1) indexe la
        # mission courante en fin de run, (2) injecte les missions similaires
        # dans le contexte de l'orchestrator au début du run.
        self.missions_rag = missions_rag
        # v0.9.0 A2 — A/B testing prompts. Si fourni, les 4 agents core
        # peuvent utiliser une variante (selon Settings.ab_testing_agents_set).
        # Le tracking par mission est fait en fin de run.
        self.prompt_ab = prompt_ab
        common = {
            "vector_memory": vector_memory,
            "skills_library": skills_library,
            "prompt_ab": prompt_ab,
        }
        self.orchestrator = ChiefOrchestrator(memory, self.settings, **common)
        self.architect = SoftwareArchitect(memory, self.settings, **common)
        self.developer = BackendDeveloper(memory, self.settings, **common)
        self.reviewer = CodeReviewer(memory, self.settings, **common)

    async def run(
        self,
        title: str,
        description: str,
        *,
        mission_id: UUID | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> MissionResult:
        # v0.8.0 — mission_id peut être fourni pour reprendre une mission
        # interrompue. Si None, on en génère un nouveau (cas nominal).
        mission_id = mission_id or uuid4()
        started = datetime.now(UTC)
        outputs: list[AgentOutput] = []

        log.info("workflow.start", mission=str(mission_id), title=title)
        emit(
            on_progress,
            make_event(
                "mission_started",
                f"Mission engineering démarrée : {title}",
                mission_id=str(mission_id),
                title=title,
            ),
        )

        # Garde-fous Phase 6 — vérifications avant tout appel LLM
        if self.killswitch is not None:
            try:
                self.killswitch.assert_clear()
            except KillswitchEngaged as exc:
                log.warning("workflow.killswitch.refused", mission=str(mission_id), error=str(exc))
                return self._fail(
                    mission_id, title, started, outputs, "killswitch.engaged", str(exc)
                )
        if self.budget is not None:
            try:
                self.budget.assert_can_proceed(estimated_cost=0.0)
            except BudgetExceeded as exc:
                log.warning("workflow.budget.refused", mission=str(mission_id), error=str(exc))
                return self._fail(mission_id, title, started, outputs, "budget.exceeded", str(exc))

        # v0.9.0 A1 — RAG sur missions passées. On cherche jusqu'à 3 missions
        # similaires APPROVED et on injecte un résumé compact dans le contexte
        # de l'orchestrator (pas dans le system prompt, pour ne pas polluer
        # toutes les invocations futures). Best-effort : si le RAG échoue,
        # la mission continue sans contexte enrichi.
        rag_context = ""
        if self.missions_rag is not None:
            try:
                similar = self.missions_rag.find_similar(
                    title=title,
                    description=description,
                    n_results=3,
                    guild="engineering",
                    exclude_mission_id=str(mission_id),
                )
                if similar:
                    rag_context = self.missions_rag.render_for_prompt(similar)
                    log.info(
                        "workflow.rag.injected",
                        mission=str(mission_id),
                        matches=len(similar),
                        top_relevance=round(similar[0].relevance, 2),
                    )
            except Exception as exc:
                log.warning("workflow.rag.failed", error=str(exc))

        orch_task = f"Mission : {title}\n\n{description}\n\nProduis la décomposition au format YAML attendu."
        if rag_context:
            orch_task = f"{rag_context}\n\n---\n\n{orch_task}"

        # Step 1 — Orchestrator décompose
        orch_out = await run_with_checkpoint(
            self.orchestrator,
            AgentInput(
                mission_id=mission_id,
                task=orch_task,
            ),
            step_index=0,
            agent_name="chief_orchestrator",
            checkpoint_store=self.checkpoint_store,
            mission_id=mission_id,
            on_progress=on_progress,
        )
        outputs.append(orch_out)
        if not orch_out.success:
            return self._fail(
                mission_id, title, started, outputs, "orchestrator.failed", orch_out.error or ""
            )

        decomposition = orch_out.parsed or {}
        first_task = self._first_subtask(decomposition) or description

        # Step 2 — Architect conçoit
        arch_out = await run_with_checkpoint(
            self.architect,
            AgentInput(
                mission_id=mission_id,
                task=first_task,
                context={"mission": description, "decomposition_yaml": orch_out.raw_text},
            ),
            step_index=1,
            agent_name="software_architect",
            checkpoint_store=self.checkpoint_store,
            mission_id=mission_id,
            on_progress=on_progress,
        )
        outputs.append(arch_out)
        if not arch_out.success:
            return self._fail(
                mission_id, title, started, outputs, "architect.failed", arch_out.error or ""
            )

        # Step 3 — Developer code
        dev_out = await run_with_checkpoint(
            self.developer,
            AgentInput(
                mission_id=mission_id,
                task=first_task,
                context={"architecture_proposal_yaml": arch_out.raw_text},
            ),
            step_index=2,
            agent_name="backend_developer",
            checkpoint_store=self.checkpoint_store,
            mission_id=mission_id,
            on_progress=on_progress,
        )
        outputs.append(dev_out)
        if not dev_out.success:
            return self._fail(
                mission_id, title, started, outputs, "developer.failed", dev_out.error or ""
            )

        # Step 4 — Reviewer juge
        review_out = await run_with_checkpoint(
            self.reviewer,
            AgentInput(
                mission_id=mission_id,
                task=first_task,
                context={
                    "architecture_proposal_yaml": arch_out.raw_text,
                    "developer_output_md": dev_out.raw_text,
                },
            ),
            step_index=3,
            agent_name="code_reviewer",
            checkpoint_store=self.checkpoint_store,
            mission_id=mission_id,
            on_progress=on_progress,
        )
        outputs.append(review_out)
        if not review_out.success:
            return self._fail(
                mission_id, title, started, outputs, "reviewer.failed", review_out.error or ""
            )

        verdict = (review_out.parsed or {}).get("verdict", VERDICT_REJECTED)

        # Sprint AAA — SecurityAuditor (opt-in via Settings.enable_security_auditor)
        # Lancé UNIQUEMENT sur missions APPROVED par le CodeReviewer — pas la peine
        # d'auditer un code que la guilde a déjà refusé.
        sec_out: AgentOutput | None = None
        if self.settings.enable_security_auditor and verdict == VERDICT_APPROVED:
            log.info("workflow.security_audit.start", mission=str(mission_id))
            sec_auditor = SecurityAuditor(
                memory=self.memory,
                settings=self.settings,
                vector_memory=self.vector_memory,
                skills_library=self.skills_library,
            )
            sec_out = await sec_auditor.run(
                AgentInput(
                    mission_id=mission_id,
                    task=first_task,
                    context={
                        "architecture_proposal_yaml": arch_out.raw_text,
                        "developer_output_md": dev_out.raw_text,
                        "code_review_verdict_yaml": review_out.raw_text,
                    },
                )
            )
            outputs.append(sec_out)
            if sec_out.success and has_downgrade_findings(sec_out.parsed):
                log.warning(
                    "workflow.security_audit.downgrade",
                    mission=str(mission_id),
                    n_findings=len(sec_out.parsed.get("findings", [])) if sec_out.parsed else 0,
                )
                verdict = VERDICT_NEEDS_CHANGES

        # Optional repair loop (max once) — Architect → Developer → Reviewer
        # dans l'ordre, chacun voit les sorties amont mises à jour. Cf. docstring
        # du module pour la rationale (pattern méta-leçon Sprint PP).
        if verdict == VERDICT_NEEDS_CHANGES:
            log.info("workflow.repair_loop", mission=str(mission_id))

            # Sprint AAA — si le SecurityAuditor a flaggué le downgrade, on injecte
            # ses findings dans le contexte pour que Architect/Developer y répondent.
            security_findings_yaml = sec_out.raw_text if sec_out is not None else ""

            # Step 1 (repair) — Architect révise éventuellement la proposition
            arch_repair_context = {
                "mission": description,
                "decomposition_yaml": orch_out.raw_text,
                "previous_architecture_yaml": arch_out.raw_text,
                "previous_implementation_md": dev_out.raw_text,
                "review_feedback_yaml": review_out.raw_text,
                "instruction": (
                    "Revoie la proposition d'architecture en intégrant les issues "
                    "remontées par le Reviewer. Si l'archi initiale tient debout et "
                    "que les issues sont purement code-level, re-produis la même "
                    "structure ; sinon ajuste-la (séparation des couches, validation, "
                    "etc.) avant que le Developer ne re-livre."
                ),
            }
            if security_findings_yaml:
                arch_repair_context["security_findings_yaml"] = security_findings_yaml
            arch_out2 = await self.architect.run(
                AgentInput(mission_id=mission_id, task=first_task, context=arch_repair_context)
            )
            outputs.append(arch_out2)
            current_arch = arch_out2 if arch_out2.success else arch_out

            # Step 2 (repair) — Developer code sur l'archi mise à jour
            dev_repair_context = {
                "architecture_proposal_yaml": current_arch.raw_text,
                "previous_implementation_md": dev_out.raw_text,
                "review_feedback_yaml": review_out.raw_text,
                "instruction": (
                    "Corrige les issues remontées par le Reviewer sur l'archi mise à "
                    "jour puis re-livre la version complète."
                ),
            }
            if security_findings_yaml:
                dev_repair_context["security_findings_yaml"] = security_findings_yaml
            dev_out2 = await self.developer.run(
                AgentInput(mission_id=mission_id, task=first_task, context=dev_repair_context)
            )
            outputs.append(dev_out2)

            # Step 3 (repair) — Reviewer juge l'ensemble v2
            if dev_out2.success:
                review_out2 = await self.reviewer.run(
                    AgentInput(
                        mission_id=mission_id,
                        task=first_task,
                        context={
                            "architecture_proposal_yaml": current_arch.raw_text,
                            "developer_output_md": dev_out2.raw_text,
                            "previous_review_yaml": review_out.raw_text,
                        },
                    )
                )
                outputs.append(review_out2)
                if review_out2.success:
                    review_out = review_out2
                    dev_out = dev_out2
                    arch_out = current_arch
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
        self._propagate_score_to_episodes(mission_id, result)

        # Enregistre la dépense effective dans le budget controller
        if self.budget is not None and total_cost > 0:
            try:
                self.budget.record(total_cost)
            except Exception as exc:
                log.warning("workflow.budget.record_failed", error=str(exc))

        log.info(
            "workflow.end",
            mission=str(mission_id),
            verdict=verdict,
            cost_usd=round(total_cost, 6),
            duration_s=round(total_duration, 2),
        )

        # v0.8.0 F1 — mission terminée (succès OU verdict définitif type
        # REJECTED) : on nettoie les checkpoints, plus besoin de les garder.
        # Si la mission a échoué via _fail() en cours de chemin, les checkpoints
        # sont conservés pour permettre le resume après fix manuel.
        if self.checkpoint_store is not None:
            self.checkpoint_store.clear(str(mission_id))

        # v0.8.0 F2 — émission finale
        emit(
            on_progress,
            make_event(
                "mission_completed",
                f"Mission terminée — verdict {verdict} (score {quality_score})",
                mission_id=str(mission_id),
                verdict=verdict,
                quality_score=quality_score,
                total_cost_usd=total_cost,
                total_duration_seconds=total_duration,
                files_count=len(files),
            ),
        )

        return result

    def _propagate_score_to_episodes(self, mission_id: UUID, result: MissionResult) -> None:
        """Patche chaque épisode de la mission avec quality_score + final_verdict.

        Permet au PatternMiner de filtrer correctement par quality_score et au
        VectorMemory de retourner des résultats triables par qualité réelle.
        Re-indexe aussi dans la VectorMemory si présente.
        """
        if result.quality_score is None and result.final_verdict == "":
            return
        for path in self.memory.list_episodes(mission_id):
            try:
                updated = self.memory.update_episode_metadata(
                    path,
                    quality_score=result.quality_score,
                    final_verdict=result.final_verdict,
                    mission_title=result.title,
                )
            except OSError as exc:
                log.warning("workflow.score_propagation.failed", path=str(path), error=str(exc))
                continue
            # Re-index avec le score à jour si VectorMemory branchée et succès
            if self.vector_memory is not None and updated.metadata.get("success"):
                try:
                    indexed_doc = (
                        f"Tâche: {updated.body.split('## Tâche', 1)[-1].split('## Sortie', 1)[0].strip()}\n\n"
                        f"Sortie:\n{updated.body.split('## Sortie brute', 1)[-1][:2000].strip()}"
                    )
                    self.vector_memory.add_episode(
                        episode_id=path.stem,
                        document=indexed_doc,
                        metadata=updated.metadata,
                    )
                except Exception as exc:
                    log.warning("workflow.reindex.failed", path=str(path), error=str(exc))

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
                # v0.9.0 A1 — fields exploités par le RAG missions
                "guild": "engineering",
                "review_summary": result.review_summary,
            },
            body="\n".join(body_lines),
        )
        self.memory.write_mission_summary(mission_id, record)

        # v0.9.0 A1 — Indexation auto dans le RAG. Filtré côté MissionsRAG
        # (APPROVED uniquement). Best-effort : un échec n'interrompt pas la
        # mission (le summary disque reste source de vérité).
        if self.missions_rag is not None:
            try:
                self.missions_rag.index_mission(
                    mission_id=str(mission_id),
                    title=title,
                    description=description,
                    summary_record=record,
                )
            except Exception as exc:
                log.warning(
                    "workflow.rag.index_failed",
                    mission=str(mission_id),
                    error=str(exc),
                )

        # v0.9.0 A2 — Tracking A/B des variantes utilisées. Pour chaque output
        # d'un agent listé dans Settings.ab_testing_agents_set, on enregistre
        # le résultat final dans data/ab_tests/<role>/<label>/. label="" si
        # canonique a été utilisé, sinon nom de la variante.
        if self.prompt_ab is not None:
            ab_agents = self.settings.ab_testing_agents_set
            tracked_agents: set[str] = set()
            for o in reversed(outputs):
                # Dans le repair loop, on prend le DERNIER output de chaque
                # agent (donc on parcourt à l'envers et on skip si déjà tracké).
                if o.agent_name in tracked_agents or o.agent_name not in ab_agents:
                    continue
                try:
                    self.prompt_ab.track_outcome(
                        role=o.agent_name,
                        label=o.prompt_variant_label or "",
                        mission_id=str(mission_id),
                        final_verdict=result.final_verdict,
                        quality_score=result.quality_score,
                        cost_usd=o.cost_usd,
                        duration_seconds=o.duration_seconds,
                    )
                    tracked_agents.add(o.agent_name)
                except Exception as exc:
                    log.warning(
                        "workflow.ab.track_failed",
                        mission=str(mission_id),
                        agent=o.agent_name,
                        error=str(exc),
                    )
