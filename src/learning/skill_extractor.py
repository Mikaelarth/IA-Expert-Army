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

_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "orchestrator" / "skill_extractor.md"


class SkillExtractor(BaseAgent):
    # YAML structuré : title + tags + summary + N key_patterns + N techniques
    # + N pitfalls_avoided + example_template. Pour 3+ épisodes massifs en input,
    # le YAML output saturait à 2048 (mining d'avril 2026 : 2/3 skills perdues
    # sur tech_watch + research_lead, $0.87 dépensés sans résultat parseable).
    # Fix aligné sur les autres agents verbeux : 4096.
    DEFAULT_MAX_TOKENS = 4096

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
            # Sprint EEE (2026-05-14) : Opus → Sonnet. Tâche = synthèse d'épisodes
            # déjà structurés vers un template YAML strict (title + tags + summary +
            # key_patterns + techniques + pitfalls + example). Sonnet gère cette
            # synthèse template-guidée à qualité équivalente. Le miner tourne en
            # nightly (pas en path mission live) → rollback trivial si dégradation
            # détectée. Économie ~5x sur ce poste (~$0.05-0.15 par mining nightly).
            model=s.model_operational,
            memory=memory,
            settings=s,
            client=client,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            vector_memory=None,  # explicit : pas d'auto-influence
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> dict[str, Any] | None:
        return extract_yaml(raw)
