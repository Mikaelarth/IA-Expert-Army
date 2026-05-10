"""BackendDeveloper — implémente le code à partir d'une proposition d'architecture."""
from __future__ import annotations

from pathlib import Path

from anthropic import AsyncAnthropic

from src.core.config import Settings, get_settings
from src.memory.file_memory import FileMemory
from src.learning.skills_library import SkillsLibrary
from src.memory.vector_memory import VectorMemory
from src.orchestrator.agents._parsers import extract_files
from src.orchestrator.base_agent import AgentInput, BaseAgent

_PROMPT = (
    Path(__file__).resolve().parents[3]
    / "prompts" / "guilds" / "engineering" / "backend_developer.md"
)


class BackendDeveloper(BaseAgent):
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
            name="backend_developer",
            prompt_path=_PROMPT,
            model=s.model_operational,
            memory=memory,
            settings=s,
            client=client,
            max_tokens=4096,
            vector_memory=vector_memory,
            skills_library=skills_library,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> list[dict[str, str]]:
        return extract_files(raw)
