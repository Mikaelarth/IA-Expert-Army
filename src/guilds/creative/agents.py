"""Agents de la Guild Creative (Phase 4 — MVP : 3 agents séquentiels).

Phase 4+ : ajouter Marketing Specialist (campagnes/SEO/social) et Visual
Designer (génération de prompts d'images via API tierce).
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

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts" / "guilds" / "creative"


class ContentStrategist(BaseAgent):
    # Brief YAML structuré : audience + positioning + proofs + tone + structure.
    # Préventif : aligné avec ResearchLead à 3072 (briefs riches).
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
            name="content_strategist",
            prompt_path=_PROMPTS_DIR / "content_strategist.md",
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


class Copywriter(BaseAgent):
    # Markdown final : peut être assez long (landing page, email long-format).
    # Aligné avec DocumentSynthesizer.
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
            name="copywriter",
            prompt_path=_PROMPTS_DIR / "copywriter.md",
            model=s.model_operational,
            memory=memory,
            settings=s,
            client=client,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            vector_memory=vector_memory,
            skills_library=skills_library,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> str:
        # Le copywriter renvoie du markdown final, pas de YAML à parser.
        return raw


class Editor(BaseAgent):
    # Verdict YAML avec issues détaillées par catégorie.
    # Aligné avec les autres reviewers à 8192.
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
            name="editor",
            prompt_path=_PROMPTS_DIR / "editor.md",
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
