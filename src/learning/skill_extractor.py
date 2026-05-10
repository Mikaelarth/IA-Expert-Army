"""SkillExtractor — agent qui synthétise une skill markdown depuis N épisodes réussis.

Hérite de BaseAgent → bénéficie de l'infra commune (logging, pricing, FileMemory).
On ne lui passe PAS de vector_memory : il ne doit pas s'auto-influencer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from src.core.config import Settings, get_settings
from src.memory.file_memory import FileMemory
from src.orchestrator.agents._parsers import extract_yaml
from src.orchestrator.base_agent import AgentInput, BaseAgent

_PROMPT = (
    Path(__file__).resolve().parents[2]
    / "prompts" / "orchestrator" / "skill_extractor.md"
)


class SkillExtractor(BaseAgent):
    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        client: AsyncAnthropic | None = None,
    ) -> None:
        s = settings or get_settings()
        super().__init__(
            name="skill_extractor",
            prompt_path=_PROMPT,
            model=s.model_strategic,  # Opus : besoin de discernement
            memory=memory,
            settings=s,
            client=client,
            max_tokens=2048,
            vector_memory=None,  # explicit : pas d'auto-influence
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> dict[str, Any] | None:
        return extract_yaml(raw)
