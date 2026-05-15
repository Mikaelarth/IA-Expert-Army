"""Agents concrets de la Guild Research (Phase 4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from src.core.config import Settings, get_settings
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory
from src.orchestrator.agents._parsers import extract_yaml
from src.orchestrator.base_agent import AgentInput, BaseAgent

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts" / "guilds" / "research"


class ResearchLead(BaseAgent):
    # Plan de recherche YAML : 4-6 sous-questions × ~200 tokens chacune
    # + sources + criteria + risks. 2048 trop court pour des plans riches.
    DEFAULT_MAX_TOKENS = 3072

    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        client: AsyncAnthropic | None = None,
        vector_memory: VectorMemory | None = None,
        skills_library: SkillsLibrary | None = None,
    ) -> None:
        s = settings or get_settings()
        super().__init__(
            name="research_lead",
            prompt_path=_PROMPTS_DIR / "research_lead.md",
            # Opus : plan de recherche (découpage en sous-questions critique
            # pour qualité downstream). ADR-016 catégorie B — vague 2 EEE
            # candidate après smoke validation.
            model=s.model_strategic,
            memory=memory,
            settings=s,
            client=client,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            vector_memory=vector_memory,
            skills_library=skills_library,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> dict[str, Any] | None:
        return extract_yaml(raw)


class TechWatch(BaseAgent):
    # max_tokens élevé : Tech Watch produit des findings YAML pour 3-6 sous-questions
    # à raison de 3-7 findings par sous-question. La saturation à 4096 tokens
    # observée en prod (mission 7b5759b1) coupait à mi-SQ4, laissant SQ5/SQ6 vides
    # et provoquant un REJECTED par le Reviewer (sourcing manquant en aval).
    # Haiku gère 8192 tokens sans surcoût significatif (~$0.03 supplémentaires
    # max au lieu de tronquer le pipeline).
    DEFAULT_MAX_TOKENS = 8192

    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        client: AsyncAnthropic | None = None,
        vector_memory: VectorMemory | None = None,
        skills_library: SkillsLibrary | None = None,
    ) -> None:
        s = settings or get_settings()
        super().__init__(
            name="tech_watch",
            prompt_path=_PROMPTS_DIR / "tech_watch.md",
            model=s.model_bulk,  # Haiku — économe pour un balayage de connaissances
            memory=memory,
            settings=s,
            client=client,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            vector_memory=vector_memory,
            skills_library=skills_library,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> dict[str, Any] | None:
        return extract_yaml(raw)


class DocumentSynthesizer(BaseAgent):
    # Markdown structuré : TL;DR + N sections (1 par sous-question) + divergences
    # + conclusion + sources consolidées. Pour 5-6 SQ, ça dépasse 4096 tokens
    # systématiquement (saturé sur 7+ épisodes consécutifs en prod). Fix préventif
    # aligné sur TechWatch (8192) après détection via le miner qui excluait
    # tous les épisodes synthesizer pour cause de saturation.
    DEFAULT_MAX_TOKENS = 8192

    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        client: AsyncAnthropic | None = None,
        vector_memory: VectorMemory | None = None,
        skills_library: SkillsLibrary | None = None,
    ) -> None:
        s = settings or get_settings()
        super().__init__(
            name="document_synthesizer",
            prompt_path=_PROMPTS_DIR / "document_synthesizer.md",
            model=s.model_operational,
            memory=memory,
            settings=s,
            client=client,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            vector_memory=vector_memory,
            skills_library=skills_library,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> str:
        # Le synthesizer renvoie du Markdown brut (pas YAML).
        # On ne parse rien : le raw est déjà le livrable.
        return raw


class ResearchReviewer(BaseAgent):
    # Verdict YAML : summary + strengths + plusieurs issues détaillées
    # (severity, category, location, message, suggestion par issue).
    # Itérations successives :
    #   2048 → saturait (mission 359bfa08, commit 1c08da5)
    #   4096 → saturait encore sur missions complexes (38fd387d) avec 8+ issues
    #          détaillées + suggestions + repair-loop précédente à analyser
    #   8192 → marge confortable, aligné avec TechWatch et DocSynth
    DEFAULT_MAX_TOKENS = 8192

    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        client: AsyncAnthropic | None = None,
        vector_memory: VectorMemory | None = None,
        skills_library: SkillsLibrary | None = None,
    ) -> None:
        s = settings or get_settings()
        super().__init__(
            name="research_reviewer",
            prompt_path=_PROMPTS_DIR / "research_reviewer.md",
            model=s.model_operational,
            memory=memory,
            settings=s,
            client=client,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            vector_memory=vector_memory,
            skills_library=skills_library,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> dict[str, Any] | None:
        return extract_yaml(raw)
