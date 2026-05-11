"""MetaWorkflow — orchestration cross-guildes (Phase 7).

Une mission qui couvre plusieurs domaines (engineering + creative + business…)
est trop large pour une seule guilde. Le MetaWorkflow :

1. Appelle un MetaDecomposer (Opus) qui découpe la mission en 2-4 sous-missions,
   chacune routée vers UNE guilde, avec dépendances optionnelles.
2. Exécute chaque sous-mission via MissionRouter (réutilise tout : budget,
   killswitch, RAG, sandbox, learning loop).
3. Agrège les résultats en un MetaMissionResult unifié.

v1 : exécution séquentielle dans l'ordre topologique du graphe `depends_on`.
v2 (futur) : parallélisation des sous-missions sans dépendance via asyncio.gather.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from src.core.budget import BudgetController
from src.core.config import Settings, get_settings
from src.core.killswitch import Killswitch
from src.core.logging import get_logger
from src.core.tracing import observe
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory, MemoryRecord
from src.memory.vector_memory import VectorMemory
from src.orchestrator.agents._parsers import extract_yaml
from src.orchestrator.base_agent import AgentInput, BaseAgent
from src.orchestrator.router import MissionRouter, UnifiedMissionResult

log = get_logger("meta_workflow")

VALID_GUILDS = {"engineering", "research", "creative", "business"}

VERDICT_APPROVED = "APPROVED"
VERDICT_NEEDS_CHANGES = "NEEDS_CHANGES"
VERDICT_REJECTED = "REJECTED"

_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "orchestrator" / "meta_decomposer.md"


class SubMissionSpec(BaseModel):
    """Une sous-mission décomposée par le MetaDecomposer."""

    guild: str
    title: str
    description: str
    depends_on: list[int] = Field(default_factory=list)


class MetaDecomposition(BaseModel):
    """Résultat brut du MetaDecomposer."""

    sub_missions: list[SubMissionSpec]
    rationale: str = ""


class MetaMissionResult(BaseModel):
    """Résultat agrégé d'une mission cross-guildes."""

    meta_mission_id: UUID
    title: str
    description: str
    decomposition_rationale: str
    sub_results: list[UnifiedMissionResult]
    final_verdict: str
    overall_quality_score: float | None
    total_cost_usd: float
    total_duration_seconds: float
    started_at: datetime
    ended_at: datetime
    summary: str


class MetaDecomposer(BaseAgent):
    """Agent stratégique (Opus) qui découpe une mission cross-domaine."""

    DEFAULT_MAX_TOKENS = 4096

    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        client: AsyncAnthropic | None = None,
    ) -> None:
        s = settings or get_settings()
        super().__init__(
            name="meta_decomposer",
            prompt_path=_PROMPT,
            model=s.model_strategic,
            memory=memory,
            settings=s,
            client=client,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            vector_memory=None,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> dict[str, Any] | None:
        return extract_yaml(raw)


class MetaDecompositionError(RuntimeError):
    """Levée quand le MetaDecomposer ne produit pas un YAML exploitable."""


class MetaWorkflow:
    """Pipeline cross-guildes : decompose → dispatch (séquentiel) → aggregate."""

    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        vector_memory: VectorMemory | None = None,
        skills_library: SkillsLibrary | None = None,
        budget: BudgetController | None = None,
        killswitch: Killswitch | None = None,
        router: MissionRouter | None = None,
        decomposer: MetaDecomposer | None = None,
    ) -> None:
        self.memory = memory
        self.settings = settings or get_settings()
        self.vector_memory = vector_memory
        self.skills_library = skills_library
        self.budget = budget
        self.killswitch = killswitch
        self.router = router or MissionRouter(
            memory=memory,
            settings=self.settings,
            vector_memory=vector_memory,
            skills_library=skills_library,
            budget=budget,
            killswitch=killswitch,
        )
        self.decomposer = decomposer or MetaDecomposer(memory=memory, settings=self.settings)

    @observe(name="meta_workflow.run")
    async def run(self, title: str, description: str) -> MetaMissionResult:
        meta_id = uuid4()
        started_at = datetime.now(UTC)
        log.info("meta.start", meta_id=str(meta_id), title=title)

        decomposition = await self._decompose(meta_id, title, description)
        log.info(
            "meta.decomposed",
            meta_id=str(meta_id),
            n_sub_missions=len(decomposition.sub_missions),
            guilds=[s.guild for s in decomposition.sub_missions],
        )

        ordered_indices = _topological_order(decomposition.sub_missions)

        sub_results: dict[int, UnifiedMissionResult] = {}
        for idx in ordered_indices:
            sub = decomposition.sub_missions[idx]
            upstream = [sub_results[d] for d in sub.depends_on if d in sub_results]
            enriched_description = _enrich_description(sub.description, upstream)
            log.info(
                "meta.dispatch",
                meta_id=str(meta_id),
                sub_index=idx,
                guild=sub.guild,
                title=sub.title,
                depends_on=sub.depends_on,
            )
            res = await self.router.run(
                title=sub.title,
                description=enriched_description,
                force_guild=sub.guild,
            )
            sub_results[idx] = res

        ordered_results = [sub_results[i] for i in range(len(decomposition.sub_missions))]
        result = self._aggregate(
            meta_id=meta_id,
            title=title,
            description=description,
            decomposition=decomposition,
            sub_results=ordered_results,
            started_at=started_at,
        )
        self._persist(result)
        return result

    async def _decompose(
        self, meta_id: UUID, title: str, description: str
    ) -> MetaDecomposition:
        agent_input = AgentInput(
            mission_id=meta_id,
            task=f"Mission cross-domaine à décomposer.\n\nTitre : {title}\n\nDescription :\n{description}",
        )
        out = await self.decomposer.run(agent_input)
        if not out.success or out.parsed is None:
            raise MetaDecompositionError(
                f"MetaDecomposer a échoué : success={out.success}, parsed={out.parsed is not None}, error={out.error}"
            )
        return _parse_decomposition(out.parsed)

    def _aggregate(
        self,
        meta_id: UUID,
        title: str,
        description: str,
        decomposition: MetaDecomposition,
        sub_results: list[UnifiedMissionResult],
        started_at: datetime,
    ) -> MetaMissionResult:
        ended_at = datetime.now(UTC)
        total_cost = sum(r.total_cost_usd for r in sub_results)
        total_duration = (ended_at - started_at).total_seconds()
        scores = [r.quality_score for r in sub_results if r.quality_score is not None]
        overall_score = sum(scores) / len(scores) if scores else None

        verdicts = [r.final_verdict for r in sub_results]
        if any(v == VERDICT_REJECTED for v in verdicts):
            final_verdict = VERDICT_REJECTED
        elif all(v == VERDICT_APPROVED for v in verdicts):
            final_verdict = VERDICT_APPROVED
        else:
            final_verdict = VERDICT_NEEDS_CHANGES

        summary = _render_summary(title, decomposition, sub_results, final_verdict, overall_score)

        return MetaMissionResult(
            meta_mission_id=meta_id,
            title=title,
            description=description,
            decomposition_rationale=decomposition.rationale,
            sub_results=sub_results,
            final_verdict=final_verdict,
            overall_quality_score=overall_score,
            total_cost_usd=total_cost,
            total_duration_seconds=total_duration,
            started_at=started_at,
            ended_at=ended_at,
            summary=summary,
        )

    def _persist(self, result: MetaMissionResult) -> None:
        meta_dir = self.memory.root / "meta_missions"
        meta_dir.mkdir(parents=True, exist_ok=True)
        path = meta_dir / f"{result.meta_mission_id}.md"
        record = MemoryRecord(
            metadata={
                "meta_mission_id": str(result.meta_mission_id),
                "title": result.title,
                "started_at": result.started_at.isoformat(),
                "ended_at": result.ended_at.isoformat(),
                "final_verdict": result.final_verdict,
                "overall_quality_score": result.overall_quality_score,
                "total_cost_usd": result.total_cost_usd,
                "total_duration_seconds": result.total_duration_seconds,
                "n_sub_missions": len(result.sub_results),
                "guilds": [r.guild for r in result.sub_results],
                "sub_mission_ids": [r.mission_id for r in result.sub_results],
            },
            body=result.summary,
        )
        path.write_text(record.to_markdown(), encoding="utf-8")
        log.info("meta.persisted", meta_id=str(result.meta_mission_id), path=str(path))


def _parse_decomposition(parsed: dict[str, Any]) -> MetaDecomposition:
    raw_subs = parsed.get("sub_missions") or []
    if not isinstance(raw_subs, list) or not raw_subs:
        raise MetaDecompositionError("YAML sans sub_missions ou liste vide")
    if len(raw_subs) > 4:
        raise MetaDecompositionError(f"Trop de sub_missions ({len(raw_subs)}), max 4")

    subs: list[SubMissionSpec] = []
    for i, item in enumerate(raw_subs):
        if not isinstance(item, dict):
            raise MetaDecompositionError(f"sub_mission {i} n'est pas un dict")
        guild = str(item.get("guild", "")).strip().lower()
        if guild not in VALID_GUILDS:
            raise MetaDecompositionError(
                f"sub_mission {i} : guilde invalide '{guild}' (valides : {sorted(VALID_GUILDS)})"
            )
        title = str(item.get("title", "")).strip()
        description = str(item.get("description", "")).strip()
        if not title or not description:
            raise MetaDecompositionError(f"sub_mission {i} : title ou description manquant")
        depends_raw = item.get("depends_on", []) or []
        if not isinstance(depends_raw, list):
            raise MetaDecompositionError(f"sub_mission {i} : depends_on doit être une liste")
        depends_on = [int(d) for d in depends_raw]
        for d in depends_on:
            if d < 0 or d >= len(raw_subs) or d == i:
                raise MetaDecompositionError(
                    f"sub_mission {i} : depends_on={d} invalide (hors borne ou auto-référence)"
                )
        subs.append(
            SubMissionSpec(guild=guild, title=title, description=description, depends_on=depends_on)
        )

    rationale = str(parsed.get("rationale", "")).strip()
    return MetaDecomposition(sub_missions=subs, rationale=rationale)


def _topological_order(sub_missions: list[SubMissionSpec]) -> list[int]:
    """Tri topologique (Kahn). Lève si cycle détecté."""
    n = len(sub_missions)
    in_degree = [len(s.depends_on) for s in sub_missions]
    children: list[list[int]] = [[] for _ in range(n)]
    for i, s in enumerate(sub_missions):
        for d in s.depends_on:
            children[d].append(i)

    queue = [i for i, deg in enumerate(in_degree) if deg == 0]
    order: list[int] = []
    while queue:
        # Stable order : tri pour reproductibilité (idx croissants en cas d'ex-aequo)
        queue.sort()
        node = queue.pop(0)
        order.append(node)
        for c in children[node]:
            in_degree[c] -= 1
            if in_degree[c] == 0:
                queue.append(c)

    if len(order) != n:
        raise MetaDecompositionError(
            f"Cycle détecté dans les dépendances (résolu {len(order)}/{n} sous-missions)"
        )
    return order


def _enrich_description(description: str, upstream_results: list[UnifiedMissionResult]) -> str:
    """Injecte le résumé des livrables amont en haut de la description aval."""
    if not upstream_results:
        return description
    parts = ["## Contexte amont (livrables des sous-missions précédentes)"]
    for r in upstream_results:
        parts.append(f"\n### {r.guild.title()} — « {r.title} »")
        parts.append(f"Verdict : {r.final_verdict}")
        if r.summary:
            parts.append(f"\nRésumé :\n{r.summary[:1500]}")
    parts.append("\n---\n")
    parts.append("## Mission")
    parts.append(description)
    return "\n".join(parts)


def _render_summary(
    title: str,
    decomposition: MetaDecomposition,
    sub_results: list[UnifiedMissionResult],
    final_verdict: str,
    overall_score: float | None,
) -> str:
    lines = [f"# {title}", ""]
    lines.append(f"**Verdict global :** {final_verdict}")
    if overall_score is not None:
        lines.append(f"**Score qualité moyen :** {overall_score:.2f}")
    lines.append(f"**Coût total :** ${sum(r.total_cost_usd for r in sub_results):.4f}")
    lines.append(f"**Sous-missions :** {len(sub_results)}")
    lines.append("")
    if decomposition.rationale:
        lines.append("## Rationale de décomposition")
        lines.append("")
        lines.append(decomposition.rationale)
        lines.append("")
    lines.append("## Sous-missions et résultats")
    lines.append("")
    for i, r in enumerate(sub_results):
        score_str = f" · score {r.quality_score:.2f}" if r.quality_score is not None else ""
        lines.append(f"### {i + 1}. [{r.guild}] {r.title}")
        lines.append(
            f"**Verdict :** {r.final_verdict}{score_str} · **Coût :** ${r.total_cost_usd:.4f} · "
            f"**Durée :** {r.total_duration_seconds:.1f}s · **Mission ID :** `{r.mission_id}`"
        )
        lines.append("")
        if r.summary:
            lines.append(r.summary[:800])
            lines.append("")
    return "\n".join(lines)
