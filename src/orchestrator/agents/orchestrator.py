"""ChiefOrchestrator — décompose une mission en sous-tâches."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from src.core.config import Settings, get_settings
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory
from src.orchestrator.agents._parsers import extract_yaml
from src.orchestrator.base_agent import AgentInput, BaseAgent

_PROMPT = Path(__file__).resolve().parents[3] / "prompts" / "orchestrator" / "chief_orchestrator.md"


class ChiefOrchestrator(BaseAgent):
    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        client: AsyncOpenAI | None = None,
        vector_memory: VectorMemory | None = None,
        skills_library: SkillsLibrary | None = None,
    ) -> None:
        s = settings or get_settings()
        super().__init__(
            name="chief_orchestrator",
            prompt_path=_PROMPT,
            # Opus : routage + classification de mission. ADR-016 catégorie B
            # (template-guidé) — vague 2 EEE candidate après smoke validation
            # sur 5+ missions live (pas encore fait, donc on garde Opus prudent).
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
