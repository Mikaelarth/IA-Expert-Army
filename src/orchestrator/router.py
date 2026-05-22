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


class LLMGuildClassifier:
    """Classifier LLM qui demande à un petit modèle (Qwen 14B bulk) de
    catégoriser la mission. Fallback automatique sur l'héuristique en cas
    d'erreur (réseau, parse, réponse hors-vocabulaire).

    Designé pour les missions ambiguës où l'héuristique tranche par
    tie-break arbitraire (ex. "Implémente une API research-driven" qui
    matche autant engineering que research).

    Coût : ~0.5-2 s par classification sur Qwen 14B local.
    Opt-in via Settings.use_llm_classifier (défaut False, garde
    l'héuristique pour rétrocompat).
    """

    _GUILDS = ("engineering", "research", "creative", "business")
    _SYSTEM_PROMPT = (
        "Tu es un classifieur de missions pour un système d'agents IA "
        "multi-guildes. Tu reçois un titre + une description et tu DOIS "
        "répondre par UN SEUL mot parmi : engineering, research, creative, "
        "business.\n\n"
        "- engineering : code, API, backend, infra, refactor, tests, CI/CD\n"
        "- research : veille tech, analyse comparative, synthèse documentaire\n"
        "- creative : copywriting, landing page, contenu marketing\n"
        "- business : roadmap, plan, OKR, conformité, contrats, KPI\n\n"
        "Réponse attendue : un mot unique, en minuscules, sans ponctuation."
    )

    def __init__(self, settings: Settings, fallback: _GuildClassifier | None = None) -> None:
        self.settings = settings
        self.fallback = fallback or HeuristicGuildClassifier()
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self.settings.ollama_base_url,
                api_key=self.settings.ollama_api_key,
                timeout=10.0,  # classifier doit rester rapide
                max_retries=0,  # pas de retry — fallback heuristique
            )
        return self._client

    def classify(self, title: str, description: str) -> str:
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.settings.model_bulk,
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Titre : {title}\n\nDescription : {description}",
                    },
                ],
                max_tokens=20,
                temperature=0.0,
            )
            raw = (response.choices[0].message.content or "").strip().lower()
            # Extraction défensive : prend le premier mot dans la réponse
            first_word = raw.split()[0].strip(".,;:!?") if raw else ""
            if first_word in self._GUILDS:
                log.info(
                    "llm_classifier.decided",
                    guild=first_word,
                    raw=raw[:50],
                )
                return first_word
            log.warning("llm_classifier.unparseable", raw=raw[:100])
        except Exception as exc:
            log.warning(
                "llm_classifier.failed",
                error=f"{type(exc).__name__}: {exc}",
                title=title[:50],
            )
        # Fallback : héuristique mots-clés
        return self.fallback.classify(title, description)


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

    # === Quality Guardian (Sprint YY, opt-in via Settings) ===
    # Politique sémantique v0.7.0 (clarification L2) :
    # - `qg_verdict` est strictement INFORMATIF — il n'override JAMAIS
    #   `final_verdict`. Un caller peut ignorer un `qg_verdict=NEEDS_REWORK`
    #   et continuer à utiliser `final_verdict=APPROVED`.
    # - `qg_blocks_release` (calculé via `is_blocking_qg`) signale les cas où
    #   un consommateur prudent devrait suspendre l'usage en aval (PatternMiner
    #   filtre déjà ces missions du mining, cf. pattern_miner.py:162).
    # - Pour rendre QG bloquant (override final_verdict), il faudra une décision
    #   produit explicite + bump majeur ; cf. CHANGELOG [Unreleased].
    qg_verdict: str | None = None  # ACCEPT | NEEDS_REWORK | ESCALATE | None
    qg_final_score: float | None = None
    qg_concerns: list[str] = []
    qg_rationale: str | None = None

    @property
    def qg_blocks_release(self) -> bool:
        """True si le QG flag un risque que les consommateurs prudents
        devraient traiter comme bloquant (NEEDS_REWORK ou ESCALATE).

        N'AFFECTE PAS `final_verdict` — c'est uniquement un indicateur que le
        caller peut lire pour décider sa politique (refuser le commit, alerter
        l'opérateur, exclure du mining, etc.).
        """
        return self.qg_verdict in {"NEEDS_REWORK", "ESCALATE"}


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
        # v0.7.0 — classifier LLM opt-in via Settings.use_llm_classifier.
        # Si l'utilisateur a passé un classifier explicite, on respecte son
        # choix. Sinon : LLM si activé, héuristique sinon.
        if classifier is not None:
            self.classifier: _GuildClassifier = classifier
        elif self.settings.use_llm_classifier:
            self.classifier = LLMGuildClassifier(self.settings)
        else:
            self.classifier = HeuristicGuildClassifier()

    def decide(
        self, title: str, description: str, force_guild: str | None = None
    ) -> RoutingDecision:
        if force_guild:
            return RoutingDecision(guild=force_guild, reason="forced by caller")
        guild = self.classifier.classify(title, description)
        reason = (
            "llm classifier (Qwen 14B)"
            if isinstance(self.classifier, LLMGuildClassifier)
            else "heuristic keyword classification"
        )
        return RoutingDecision(guild=guild, reason=reason)

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
            unified = UnifiedMissionResult(
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
        elif decision.guild == "creative":
            wf_cre = CreativeWorkflow(**common)
            cre_result: CreativeMissionResult = await wf_cre.run(
                title=title, description=description
            )
            unified = UnifiedMissionResult(
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
        elif decision.guild == "business":
            wf_biz = BusinessWorkflow(**common)
            biz_result: BusinessMissionResult = await wf_biz.run(
                title=title, description=description
            )
            unified = UnifiedMissionResult(
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
        else:
            # Default = engineering
            wf_eng = Workflow(**common)
            eng_result: MissionResult = await wf_eng.run(title=title, description=description)
            unified = UnifiedMissionResult(
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

        # Sprint YY — Quality Guardian peer review méta cross-guilde (opt-in)
        if self.settings.enable_quality_guardian:
            unified = await self._apply_quality_guardian(unified, title, description)
        return unified

    async def _apply_quality_guardian(
        self, unified: UnifiedMissionResult, title: str, description: str
    ) -> UnifiedMissionResult:
        """Lance le QG sur le résultat de la guilde et enrichit le UnifiedMissionResult.

        Politique : on n'override JAMAIS le verdict guilde. On ajoute juste les
        champs `qg_*` informatifs. Le caller (run_mission.py, PatternMiner, etc.)
        décide quoi faire avec un `qg_verdict == NEEDS_REWORK` (ne pas miner, etc.).
        """
        from src.orchestrator.quality_guardian import QualityGuardian, review_mission

        try:
            qg = QualityGuardian(memory=self.memory, settings=self.settings)
            verdict = await review_mission(
                qg=qg,
                mission_title=title,
                mission_description=description,
                guild=unified.guild,
                guild_verdict=unified.final_verdict,
                guild_score=unified.quality_score,
                guild_summary=unified.summary,
                raw_result_excerpt=str(unified.raw_result)[:3000],
            )
        except Exception as exc:
            log.warning("qg.run.failed", error=str(exc))
            return unified

        if verdict is None:
            log.warning("qg.parsed_none")
            return unified

        log.info(
            "qg.complete",
            mission_id=unified.mission_id,
            qg_verdict=verdict.verdict_qg,
            qg_final_score=verdict.final_score,
            qg_concerns_count=len(verdict.meta_concerns),
        )

        # Persiste les champs qg_* dans le mission summary (Sprint ZZ.0) pour
        # que les consommateurs downstream (PatternMiner, daily_digest, MCP)
        # voient le verdict QG sans avoir à recalculer.
        try:
            self.memory.update_mission_summary_metadata(
                unified.mission_id,
                qg_verdict=verdict.verdict_qg,
                qg_final_score=verdict.final_score,
                qg_concerns=verdict.meta_concerns,
                qg_rationale=verdict.rationale,
            )
        except Exception as exc:
            log.warning("qg.persist_failed", mission_id=unified.mission_id, error=str(exc))

        # Pydantic v2 immutable update
        return unified.model_copy(
            update={
                "qg_verdict": verdict.verdict_qg,
                "qg_final_score": verdict.final_score,
                "qg_concerns": verdict.meta_concerns,
                "qg_rationale": verdict.rationale,
            }
        )
