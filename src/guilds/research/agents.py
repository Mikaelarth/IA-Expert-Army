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
            model=s.model_strategic,
            memory=memory,
            settings=s,
            client=client,
            max_tokens=2048,
            vector_memory=vector_memory,
            skills_library=skills_library,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> dict[str, Any] | None:
        return extract_yaml(raw)


class TechWatch(BaseAgent):
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
            max_tokens=4096,
            vector_memory=vector_memory,
            skills_library=skills_library,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> dict[str, Any] | None:
        return extract_yaml(raw)


class DocumentSynthesizer(BaseAgent):
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
            max_tokens=4096,
            vector_memory=vector_memory,
            skills_library=skills_library,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> str:
        # Le synthesizer renvoie du Markdown brut (pas YAML).
        # On ne parse rien : le raw est déjà le livrable.
        return raw


class ResearchReviewer(BaseAgent):
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
            max_tokens=2048,
            vector_memory=vector_memory,
            skills_library=skills_library,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> dict[str, Any] | None:
        return extract_yaml(raw)
