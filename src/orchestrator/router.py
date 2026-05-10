"""MissionRouter — point d'entrée unifié qui dispatch vers la bonne guilde.

Phase 4 MVP — classifieur heuristique simple (mots-clés). Pas d'appel LLM
juste pour décider la guilde : si l'utilisateur précise explicitement le type
de mission, on respecte. Sinon, on déduit du vocabulaire.

Phase 4+ : remplacera l'heuristique par un mini-classifier Claude (Haiku) qui
note les ambiguïtés et redirige vers la bonne guilde — ou par un Chief
Orchestrator enrichi qui inclut `target_guild` dans sa décomposition YAML.
"""
from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic import BaseModel

from src.core.budget import BudgetController
from src.core.config import Settings, get_settings
from src.core.killswitch import Killswitch
from src.core.logging import get_logger
from src.guilds.research.workflow import ResearchMissionResult, ResearchWorkflow
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory
from src.orchestrator.workflow import MissionResult, Workflow

log = get_logger("router")

# Mots-clés (insensibles à la casse) qui orientent vers la Guild Research.
# Le set est intentionnellement court : on vise la précision, pas le rappel.
_RESEARCH_KEYWORDS = (
    "recherche",
    "researcher",
    "compare",
    "comparer",
    "comparaison",
    "analyse",
    "analyze",
    "synthèse",
    "synthese",
    "synthétise",
    "synthesize",
    "étudie",
    "etudie",
    "rapport",
    "report",
    "veille",
    "état de l'art",
    "etat de l'art",
    "state of the art",
    "literature review",
    "panorama",
    "benchmark",  # peut être borderline mais souvent research
)

# Mots-clés qui orientent fortement vers Engineering (priorité s'ils apparaissent)
_ENGINEERING_KEYWORDS = (
    "endpoint",
    "api",
    "implémente",
    "implemente",
    "implement",
    "code",
    "fonction",
    "function",
    "module",
    "class ",
    "classe",
    "test",
    "pytest",
    "router",
    "fastapi",
    "django",
    "flask",
    "sql",
    "schema",
    "migration",
    "ci/cd",
    "dockerfile",
    "deploy",
)


class _GuildClassifier(Protocol):
    def classify(self, title: str, description: str) -> str: ...


class HeuristicGuildClassifier:
    """Heuristique mots-clés. Engineering par défaut (la plus mature des guildes)."""

    def __init__(
        self,
        research_keywords: tuple[str, ...] = _RESEARCH_KEYWORDS,
        engineering_keywords: tuple[str, ...] = _ENGINEERING_KEYWORDS,
    ) -> None:
        self.research_keywords = research_keywords
        self.engineering_keywords = engineering_keywords

    def classify(self, title: str, description: str) -> str:
        text = f"{title}\n{description}".lower()
        eng_hits = sum(1 for kw in self.engineering_keywords if self._matches(kw, text))
        res_hits = sum(1 for kw in self.research_keywords if self._matches(kw, text))
        # Engineering "wins" en cas d'égalité (par ADR-001 : guilde la plus mature).
        if res_hits > eng_hits:
            return "research"
        return "engineering"

    @staticmethod
    def _matches(keyword: str, text: str) -> bool:
        # Match par mot entier quand possible (évite "API" qui match "rapide")
        if " " in keyword:
            return keyword in text
        return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


class RoutingDecision(BaseModel):
    guild: str
    reason: str


class UnifiedMissionResult(BaseModel):
    mission_id: str
    title: str
    guild: str
    success: bool
    final_verdict: str
    quality_score: float | None
    total_cost_usd: float
    total_duration_seconds: float
    summary: str
    raw_result: dict[str, Any]


class MissionRouter:
    """Point d'entrée : reçoit (title, description), choisit la guilde, exécute,
    retourne un résultat unifié."""

    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        vector_memory: VectorMemory | None = None,
        skills_library: SkillsLibrary | None = None,
        budget: BudgetController | None = None,
        killswitch: Killswitch | None = None,
        classifier: _GuildClassifier | None = None,
    ) -> None:
        self.memory = memory
        self.settings = settings or get_settings()
        self.vector_memory = vector_memory
        self.skills_library = skills_library
        self.budget = budget
        self.killswitch = killswitch
        self.classifier = classifier or HeuristicGuildClassifier()

    def decide(self, title: str, description: str, force_guild: str | None = None) -> RoutingDecision:
        if force_guild:
            return RoutingDecision(guild=force_guild, reason="forced by caller")
        guild = self.classifier.classify(title, description)
        return RoutingDecision(guild=guild, reason="heuristic keyword classification")

    async def run(
        self,
        title: str,
        description: str,
        force_guild: str | None = None,
    ) -> UnifiedMissionResult:
        decision = self.decide(title, description, force_guild=force_guild)
        log.info("router.dispatch", guild=decision.guild, reason=decision.reason, title=title)

        common = {
            "memory": self.memory,
            "settings": self.settings,
            "vector_memory": self.vector_memory,
            "skills_library": self.skills_library,
            "budget": self.budget,
            "killswitch": self.killswitch,
        }

        if decision.guild == "research":
            wf = ResearchWorkflow(**common)
            result: ResearchMissionResult = await wf.run(title=title, description=description)
            return UnifiedMissionResult(
                mission_id=str(result.mission_id),
                title=result.title,
                guild="research",
                success=result.success,
                final_verdict=result.final_verdict,
                quality_score=result.quality_score,
                total_cost_usd=result.total_cost_usd,
                total_duration_seconds=result.total_duration_seconds,
                summary=result.review_summary,
                raw_result=result.model_dump(mode="json"),
            )

        # Default = engineering
        wf_eng = Workflow(**common)
        eng_result: MissionResult = await wf_eng.run(title=title, description=description)
        return UnifiedMissionResult(
            mission_id=str(eng_result.mission_id),
            title=eng_result.title,
            guild="engineering",
            success=eng_result.success,
            final_verdict=eng_result.final_verdict,
            quality_score=eng_result.quality_score,
            total_cost_usd=eng_result.total_cost_usd,
            total_duration_seconds=eng_result.total_duration_seconds,
            summary=eng_result.review_summary,
            raw_result=eng_result.model_dump(mode="json"),
        )
