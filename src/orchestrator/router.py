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
from src.core.tracing import observe
from src.guilds.business.workflow import BusinessMissionResult, BusinessWorkflow
from src.guilds.creative.workflow import CreativeMissionResult, CreativeWorkflow
from src.guilds.research.workflow import ResearchMissionResult, ResearchWorkflow
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory
from src.orchestrator.workflow import MissionResult, Workflow

log = get_logger("router")

# Mots-clés (insensibles à la casse) qui orientent vers la Guild Research.
# On vise des termes peu ambigus + des phrases longues caractéristiques d'une
# tâche méta (synthèse / guide / comparatif) plutôt que d'une tâche d'écriture
# de code. Le scoring compte chaque keyword UNE FOIS et pondère le titre 2×
# pour éviter qu'un mot répété ("test", "module") n'écrase la classification.
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
    # Ajouts pour les missions méta sur du logiciel (extracteurs forts)
    "meilleures pratiques",
    "best practices",
    "guide",
    "stratégies",
    "strategies",
    "documente",
    "documenter",
    "explique",
    "comparatif",
    "tour d'horizon",
    "pour ou contre",
    "pros and cons",
    "trade-off",
    "tradeoff",
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

# Verbes d'action FORTS qui expriment une intention claire et doivent peser plus
# que les mots-noms ambigus (e.g. "code" dans "dans le code applicatif" est un nom
# qui parle de code existant, alors que "synthétise" est un verbe d'action explicite
# qui demande de produire une synthèse). Bonus +2 sur body et title quand un de ces
# mots est trouvé. Découvert mission 7c98893b (observabilité) où "code" et
# "synthétise" se neutralisaient et la mission research était routée à eng.
_STRONG_ACTION_VERBS = (
    # research
    "compare",
    "comparer",
    "synthèse",
    "synthese",
    "synthétise",
    "synthétiser",
    "synthesize",
    "analyse",
    "analyser",
    "analyze",
    "étudie",
    "etudie",
    "study",
    "documente",
    "documenter",
    # engineering
    "implémente",
    "implemente",
    "implement",
    # creative
    "rédige",
    "rediger",
    "rédiger",
    "write",
    "écris",
    "ecris",
    "écrire",
    "draft",
    "compose",
)


# Mots-clés Guild Creative — production de contenu (texte, marketing, éditorial)
_CREATIVE_KEYWORDS = (
    "rédige",
    "rediger",
    "rédiger",
    "write",
    "écris",
    "ecris",
    "écrire",
    "draft",
    "compose",
    "landing page",
    "pitch",
    "copywriting",
    "tagline",
    "newsletter",
    "email marketing",
    "blog post",
    "post de blog",
    "communiqué de presse",
    "press release",
    "case study",
    "cas client",
    "argumentaire",
    "page d'accueil",
    "homepage copy",
    "headline",
    "slogan",
    "marketing",
)


# Mots-clés Guild Business — pilotage projet, viabilité économique, conformité.
# Volontairement orientés "intention de cadrage/analyse" (pas "exécution").
_BUSINESS_KEYWORDS = (
    "roadmap",
    "planning",
    "milestones",
    "milestone",
    "jalons",
    "business plan",
    "business case",
    "go-to-market",
    "go to market",
    "gtm",
    "viabilité",
    "viability",
    "rentabilité",
    "profitability",
    "modèle économique",
    "business model",
    "monetization",
    "monétisation",
    "tarification",
    "pricing strategy",
    "kpis",
    "okrs",
    "roi",
    "tco",
    "p&l",
    "rgpd",
    "gdpr",
    "compliance",
    "conformité",
    "ai act",
    "contrat",
    "cgu",
    "cgv",
    "stakeholders",
    "parties prenantes",
)


class _GuildClassifier(Protocol):
    def classify(self, title: str, description: str) -> str: ...


class HeuristicGuildClassifier:
    """Heuristique mots-clés. Engineering par défaut (la plus mature des guildes)."""

    def __init__(
        self,
        research_keywords: tuple[str, ...] = _RESEARCH_KEYWORDS,
        engineering_keywords: tuple[str, ...] = _ENGINEERING_KEYWORDS,
        creative_keywords: tuple[str, ...] = _CREATIVE_KEYWORDS,
        business_keywords: tuple[str, ...] = _BUSINESS_KEYWORDS,
    ) -> None:
        self.research_keywords = research_keywords
        self.engineering_keywords = engineering_keywords
        self.creative_keywords = creative_keywords
        self.business_keywords = business_keywords

    # Poids du titre. Un keyword dans le titre = TITLE_WEIGHT points ; dans le body
    # uniquement = 1 point (ou +2 pour un verbe d'action fort).
    TITLE_WEIGHT = 3
    # Bonus appliqué quand le keyword est dans _STRONG_ACTION_VERBS — exprime une
    # intention plus claire qu'un nom commun.
    STRONG_VERB_BONUS = 2

    def classify(self, title: str, description: str) -> str:
        title_lower = title.lower()
        full_lower = f"{title}\n{description}".lower()

        # Comptage en KEYWORDS UNIQUES (chaque mot-clé contribue au plus 1× au score)
        # pour éviter qu'un terme commun répété ne domine artificiellement.
        scores = {
            "engineering": self._score(self.engineering_keywords, title_lower, full_lower),
            "research": self._score(self.research_keywords, title_lower, full_lower),
            "creative": self._score(self.creative_keywords, title_lower, full_lower),
            "business": self._score(self.business_keywords, title_lower, full_lower),
        }
        max_score = max(scores.values())
        # Tie-break selon ordre de maturité (ADR-001) : engineering > research > creative > business
        for guild in ("engineering", "research", "creative", "business"):
            if scores[guild] == max_score:
                return guild
        return "engineering"  # safety

    @classmethod
    def _score(cls, keywords: tuple[str, ...], title_text: str, full_text: str) -> int:
        score = 0
        for kw in keywords:
            in_title = cls._matches(kw, title_text)
            in_body = cls._matches(kw, full_text)
            is_strong = kw in _STRONG_ACTION_VERBS
            if in_title:
                score += cls.TITLE_WEIGHT + (cls.STRONG_VERB_BONUS if is_strong else 0)
            elif in_body:
                score += 1 + (cls.STRONG_VERB_BONUS if is_strong else 0)
        return score

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

    def decide(
        self, title: str, description: str, force_guild: str | None = None
    ) -> RoutingDecision:
        if force_guild:
            return RoutingDecision(guild=force_guild, reason="forced by caller")
        guild = self.classifier.classify(title, description)
        return RoutingDecision(guild=guild, reason="heuristic keyword classification")

    @observe(name="mission.router.run")
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

        if decision.guild == "creative":
            wf_cre = CreativeWorkflow(**common)
            cre_result: CreativeMissionResult = await wf_cre.run(
                title=title, description=description
            )
            return UnifiedMissionResult(
                mission_id=str(cre_result.mission_id),
                title=cre_result.title,
                guild="creative",
                success=cre_result.success,
                final_verdict=cre_result.final_verdict,
                quality_score=cre_result.quality_score,
                total_cost_usd=cre_result.total_cost_usd,
                total_duration_seconds=cre_result.total_duration_seconds,
                summary=cre_result.review_summary,
                raw_result=cre_result.model_dump(mode="json"),
            )

        if decision.guild == "business":
            wf_biz = BusinessWorkflow(**common)
            biz_result: BusinessMissionResult = await wf_biz.run(
                title=title, description=description
            )
            return UnifiedMissionResult(
                mission_id=str(biz_result.mission_id),
                title=biz_result.title,
                guild="business",
                success=biz_result.success,
                final_verdict=biz_result.final_verdict,
                quality_score=biz_result.quality_score,
                total_cost_usd=biz_result.total_cost_usd,
                total_duration_seconds=biz_result.total_duration_seconds,
                summary=biz_result.review_summary,
                raw_result=biz_result.model_dump(mode="json"),
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
