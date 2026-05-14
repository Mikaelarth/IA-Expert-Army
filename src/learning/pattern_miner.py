"""PatternMiner — pour chaque agent, sélectionne ses meilleurs épisodes et
demande au SkillExtractor d'en synthétiser une skill réutilisable.

Phase 5 MVP — algorithme :
1. Lit tous les épisodes via FileMemory
2. Filtre : success=True ET (quality_score absent OU >= min_quality)
3. Groupe par agent
4. Pour chaque agent ayant >= min_episodes épisodes :
   - Sélectionne les top-K épisodes (par quality_score décroissant, fallback récence)
   - Concat dans un prompt
   - Appelle SkillExtractor
   - Parse YAML → écrit la skill dans SkillsLibrary
5. Retourne un MiningReport
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from src.core.config import Settings, get_settings
from src.core.logging import get_logger
from src.learning.skill_extractor import SkillExtractor
from src.learning.skills_library import Skill, SkillsLibrary
from src.memory.file_memory import FileMemory, MemoryRecord
from src.orchestrator.base_agent import AgentInput

log = get_logger("pattern_miner")


class AgentMiningResult(BaseModel):
    agent: str
    episodes_considered: int
    skill_extracted: Skill | None
    cost_usd: float = 0.0
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class MiningReport(BaseModel):
    started_at: datetime
    ended_at: datetime
    total_episodes_scanned: int
    agents_processed: int
    skills_created: int
    total_cost_usd: float
    per_agent: list[AgentMiningResult]


class PatternMiner:
    """Orchestre le mining nocturne. Stateless — ré-instancie à chaque run."""

    # Agents pour lesquels on extrait des skills (tous les agents productifs des
    # guildes). Le skill_extractor lui-même est exclu (sinon récursion).
    # NOTE : à mettre à jour à chaque nouvelle guilde — pattern récurrent
    # observé sur Research puis Creative. Phase 5+ : charger dynamiquement
    # depuis les workflows pour éviter les oublis.
    AGENT_WHITELIST: tuple[str, ...] = (
        # Comité de direction
        "chief_orchestrator",
        # Guild Engineering
        "software_architect",
        "backend_developer",
        "code_reviewer",
        "security_auditor",  # Sprint AAA — audit OWASP/secrets/pratiques sécu
        # Guild Research (ajoutée Phase 4)
        "research_lead",
        "tech_watch",
        "document_synthesizer",
        "research_reviewer",
        # Guild Creative (ajoutée Phase 4 MVP)
        "content_strategist",
        "copywriter",
        "editor",
        # Guild Business (ajoutée Phase 4 MVP)
        "project_manager",
        "business_analyst",
        "legal_reviewer",
    )

    def __init__(
        self,
        memory: FileMemory,
        skills: SkillsLibrary,
        settings: Settings | None = None,
        extractor: SkillExtractor | None = None,
        min_episodes: int = 2,
        top_k: int = 3,
        min_quality: float = 0.85,
        agents: tuple[str, ...] | None = None,
    ) -> None:
        self.memory = memory
        self.skills = skills
        self.settings = settings or get_settings()
        self.extractor = extractor or SkillExtractor(memory=memory, settings=self.settings)
        self.min_episodes = min_episodes
        self.top_k = top_k
        self.min_quality = min_quality
        # Sous-ensemble facultatif d'agents à miner (par défaut tous le whitelist).
        # Permet de cibler une guilde précise sans re-miner inutilement les autres.
        self.agents = agents or self.AGENT_WHITELIST

    def _load_eligible_episodes(self) -> dict[str, list[tuple[Path, MemoryRecord]]]:
        """Retourne {agent: [(path, record), ...]} filtré sur succès + quality.

        Ignore aussi les épisodes saturés (sortie tronquée par max_tokens) car
        leur YAML est probablement incomplet et minerait sur une donnée corrompue.
        """
        grouped: dict[str, list[tuple[Path, MemoryRecord]]] = defaultdict(list)
        # Sprint ZZ.2 — cache des verdicts QG par mission_id, pour ne pas relire
        # le mission summary N fois si plusieurs épisodes de la même mission.
        qg_cache: dict[str, str | None] = {}

        for path in self.memory.list_episodes():
            try:
                record = self.memory.read_episode(path)
            except OSError:
                continue
            meta = record.metadata
            if not meta.get("success"):
                continue
            if meta.get("saturated") is True:
                # Détection ajoutée Phase 4 polish — exclut les épisodes coupés.
                continue
            # Si le verdict de mission a été propagé (post-Sprint 1, commit 62041a4),
            # on ne mine QUE les missions APPROVED. Le 'success' au niveau de l'agent
            # individuel signifie juste "l'appel API a abouti" — pas que le résultat
            # global a été validé. Cas non propagé (legacy) : on retombe sur le check
            # de quality_score plus bas.
            final_verdict = meta.get("final_verdict")
            if final_verdict and final_verdict != "APPROVED":
                continue
            agent = meta.get("agent", "")
            if agent not in self.agents:
                continue
            score = meta.get("quality_score")
            if isinstance(score, (int, float)) and score < self.min_quality:
                continue

            # Sprint ZZ.2 — filtre QG : si la mission a un qg_verdict NEEDS_REWORK
            # ou ESCALATE, on n'inclut PAS ses épisodes dans le mining. Le verdict
            # guilde est resté APPROVED (pas d'override automatique, cf. ADR-011)
            # mais le QG a flaggé un problème méta — la skill apprise serait polluée.
            mission_id = meta.get("mission_id")
            if mission_id:
                mid_str = str(mission_id)
                if mid_str not in qg_cache:
                    summary = self.memory.get_mission_summary(mid_str)
                    qg_cache[mid_str] = summary.metadata.get("qg_verdict") if summary else None
                qg_verdict = qg_cache[mid_str]
                if qg_verdict in {"NEEDS_REWORK", "ESCALATE"}:
                    continue

            grouped[agent].append((path, record))
        return grouped

    @staticmethod
    def _select_top_k(
        records: list[tuple[Path, MemoryRecord]], k: int
    ) -> list[tuple[Path, MemoryRecord]]:
        """Tri par quality_score décroissant ; fallback : ordre alphabétique du nom (récent en dernier).

        On veut les épisodes les plus prometteurs en premier.
        """

        def key(item: tuple[Path, MemoryRecord]) -> tuple[float, str]:
            score = item[1].metadata.get("quality_score")
            score_num = float(score) if isinstance(score, (int, float)) else 0.0
            return (-score_num, item[0].name)

        return sorted(records, key=key)[:k]

    def _build_extractor_input(
        self, agent: str, episodes: list[tuple[Path, MemoryRecord]]
    ) -> AgentInput:
        """Construit le prompt utilisateur du SkillExtractor."""
        sections = [
            f"Voici {len(episodes)} épisode(s) RÉUSSIS du rôle « {agent} ». "
            "Extrais la skill réutilisable comme indiqué dans ton system prompt.",
            "",
        ]
        for i, (_path, rec) in enumerate(episodes, 1):
            score = rec.metadata.get("quality_score", "n/a")
            mission = rec.metadata.get("mission_id", "?")[:8]
            sections.append(f"---\n## Épisode {i} (mission {mission}, score {score})\n")
            sections.append(rec.body)
            sections.append("")
        return AgentInput(
            mission_id=uuid4(),  # mission "synthétique" pour le mining
            task=f"Extraire une skill réutilisable pour le rôle « {agent} »",
            context={"episodes": "\n".join(sections)},
        )

    async def mine(self) -> MiningReport:
        """Lance le mining sur tous les agents éligibles. Async pour conformité avec BaseAgent."""
        started = datetime.now(UTC)
        log.info("mining.start", min_quality=self.min_quality, top_k=self.top_k)

        grouped = self._load_eligible_episodes()
        total_scanned = sum(len(v) for v in grouped.values())
        per_agent: list[AgentMiningResult] = []
        total_cost = 0.0
        skills_created = 0

        for agent in self.agents:
            episodes = grouped.get(agent, [])
            if len(episodes) < self.min_episodes:
                log.info(
                    "mining.skip",
                    agent=agent,
                    have=len(episodes),
                    need=self.min_episodes,
                )
                per_agent.append(
                    AgentMiningResult(
                        agent=agent,
                        episodes_considered=len(episodes),
                        skill_extracted=None,
                        error=f"Trop peu d'épisodes ({len(episodes)} < {self.min_episodes})",
                    )
                )
                continue

            top_episodes = self._select_top_k(episodes, self.top_k)
            agent_input = self._build_extractor_input(agent, top_episodes)
            output = await self.extractor.run(agent_input)
            total_cost += output.cost_usd

            if not output.success:
                per_agent.append(
                    AgentMiningResult(
                        agent=agent,
                        episodes_considered=len(top_episodes),
                        skill_extracted=None,
                        cost_usd=output.cost_usd,
                        error=output.error,
                    )
                )
                continue

            yaml_data = output.parsed if isinstance(output.parsed, dict) else None
            if not yaml_data or not yaml_data.get("title"):
                per_agent.append(
                    AgentMiningResult(
                        agent=agent,
                        episodes_considered=len(top_episodes),
                        skill_extracted=None,
                        cost_usd=output.cost_usd,
                        error="YAML invalide ou sans titre",
                    )
                )
                continue

            skill = self._persist_skill(agent, yaml_data, top_episodes, output.raw_text)
            skills_created += 1
            per_agent.append(
                AgentMiningResult(
                    agent=agent,
                    episodes_considered=len(top_episodes),
                    skill_extracted=skill,
                    cost_usd=output.cost_usd,
                )
            )
            log.info("mining.skill_created", agent=agent, title=skill.title)

        ended = datetime.now(UTC)
        report = MiningReport(
            started_at=started,
            ended_at=ended,
            total_episodes_scanned=total_scanned,
            agents_processed=sum(1 for r in per_agent if r.skill_extracted is not None),
            skills_created=skills_created,
            total_cost_usd=total_cost,
            per_agent=per_agent,
        )
        log.info(
            "mining.end",
            scanned=total_scanned,
            skills_created=skills_created,
            cost=round(total_cost, 6),
        )
        return report

    @staticmethod
    def _strip_outer_fence(text: str) -> str:
        """Retire un éventuel ```lang...``` wrapper, pour éviter les fences imbriqués."""
        t = text.strip()
        if not t.startswith("```"):
            return t
        first_nl = t.find("\n")
        if first_nl < 0 or not t.endswith("```"):
            return t
        return t[first_nl + 1 : -3].rstrip()

    def _persist_skill(
        self,
        agent: str,
        yaml_data: dict[str, Any],
        episodes: list[tuple[Path, MemoryRecord]],
        raw_yaml: str,
    ) -> Skill:
        title = str(yaml_data.get("title", "Untitled skill")).strip()
        summary = str(yaml_data.get("summary", "")).strip()
        clean_yaml = self._strip_outer_fence(raw_yaml)
        body_lines = [
            f"## Résumé\n\n{summary}",
            "",
            "## Patterns clés",
            *(f"- {p}" for p in yaml_data.get("key_patterns", [])),
            "",
            "## Techniques",
            *(f"- {t}" for t in yaml_data.get("techniques", [])),
            "",
            "## Pièges évités",
            *(f"- {p}" for p in yaml_data.get("pitfalls_avoided", [])),
            "",
            "## Template d'exemple",
            "",
            "```",
            str(yaml_data.get("example_template", "")).strip(),
            "```",
            "",
            "## Sources",
            *(
                f"- {ep[0].stem} (score {ep[1].metadata.get('quality_score', 'n/a')})"
                for ep in episodes
            ),
            "",
            "<details><summary>YAML brut du Skill Extractor</summary>",
            "",
            "```yaml",
            clean_yaml,
            "```",
            "",
            "</details>",
        ]
        metadata = {
            "summary": summary,
            "tags": yaml_data.get("tags", []),
            "sources": [ep[0].stem for ep in episodes],
            "sources_avg_score": round(
                sum(
                    float(ep[1].metadata.get("quality_score", 0))
                    for ep in episodes
                    if isinstance(ep[1].metadata.get("quality_score"), (int, float))
                )
                / max(len(episodes), 1),
                3,
            ),
            "extracted_from": len(episodes),
        }
        return self.skills.write_skill(
            agent=agent, title=title, body="\n".join(body_lines), metadata=metadata
        )
