"""Agents de la Guild Business (Phase 4 — MVP : 3 agents séquentiels).

Phase 4+ : ajouter Finance Analyst (modélisation financière approfondie) et
Customer Success (post-launch : feedback, support, FAQ, churn analysis).
"""
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

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts" / "guilds" / "business"


class ProjectManager(BaseAgent):
    # Plan YAML : 3-6 milestones × ~150 tokens + scope + resources + 3 risks + checkpoints.
    # Aligné avec ResearchLead (3072) — taille moyenne raisonnable pour un plan riche.
    DEFAULT_MAX_TOKENS = 4096

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
            name="project_manager",
            prompt_path=_PROMPTS_DIR / "project_manager.md",
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


class BusinessAnalyst(BaseAgent):
    # Analyse YAML riche : market + UVP + unit_economics + KPIs + risks + verdict.
    # Aligné avec les autres analystes stratégiques à 4096+. On part directement
    # à 6144 pour les analyses complexes (économies multi-segments).
    DEFAULT_MAX_TOKENS = 6144

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
            name="business_analyst",
            prompt_path=_PROMPTS_DIR / "business_analyst.md",
            model=s.model_strategic,  # Opus : besoin de raisonnement économique
            memory=memory,
            settings=s,
            client=client,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            vector_memory=vector_memory,
            skills_library=skills_library,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> dict[str, Any] | None:
        return extract_yaml(raw)


class LegalReviewer(BaseAgent):
    # Verdict YAML aligné sur les autres reviewers (8192 — précédents incidents
    # de saturation sur ResearchReviewer commits 1c08da5 et fcfa051).
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
            name="legal_reviewer",
            prompt_path=_PROMPTS_DIR / "legal_reviewer.md",
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
