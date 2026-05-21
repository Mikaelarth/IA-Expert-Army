"""BackendDeveloper — implémente le code à partir d'une proposition d'architecture."""

from __future__ import annotations

from pathlib import Path

from openai import AsyncOpenAI

from src.core.config import Settings, get_settings
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory
from src.orchestrator.agents._parsers import extract_files
from src.orchestrator.base_agent import AgentInput, BaseAgent

_PROMPT = (
    Path(__file__).resolve().parents[3]
    / "prompts"
    / "guilds"
    / "engineering"
    / "backend_developer.md"
)


class BackendDeveloper(BaseAgent):
    # Code multi-fichiers (jusqu'à ~10 modules + tests + Dockerfile). 4096 saturait
    # SYSTÉMATIQUEMENT sur les missions étalon Sprint DDD (mission 70652f89 du
    # 2026-05-14 : conftest tronqué + tests/test_*.py manquants + Dockerfile absent
    # aux 2 itérations du repair loop). 16384 donne la marge pour ~500 lignes de
    # code idiomatique multi-fichiers. Cf. ADR-005 incident 8 et ADR-015.
    DEFAULT_MAX_TOKENS = 16384

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
            name="backend_developer",
            prompt_path=_PROMPT,
            model=s.model_operational,
            memory=memory,
            settings=s,
            client=client,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            vector_memory=vector_memory,
            skills_library=skills_library,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> list[dict[str, str]]:
        return extract_files(raw)
