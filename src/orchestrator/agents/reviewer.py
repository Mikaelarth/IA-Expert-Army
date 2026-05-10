"""CodeReviewer — juge le code produit et émet un verdict YAML."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from src.core.config import Settings, get_settings
from src.memory.file_memory import FileMemory
from src.learning.skills_library import SkillsLibrary
from src.memory.vector_memory import VectorMemory
from src.orchestrator.agents._parsers import extract_yaml
from src.orchestrator.base_agent import AgentInput, BaseAgent

_PROMPT = (
    Path(__file__).resolve().parents[3]
    / "prompts" / "guilds" / "engineering" / "code_reviewer.md"
)


class CodeReviewer(BaseAgent):
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
            name="code_reviewer",
            prompt_path=_PROMPT,
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
