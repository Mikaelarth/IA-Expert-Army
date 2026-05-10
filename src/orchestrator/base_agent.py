"""BaseAgent — classe de base pour tous les agents de l'armée.

Cycle de vie d'un agent en Phase 1 :
1. Charge son system prompt depuis `prompts/<path>.md` (avec frontmatter)
2. Reçoit un AgentInput (mission_id + task + context)
3. Construit les messages Claude (system + user contextualisé)
4. Appelle Claude via AsyncAnthropic
5. Logue un episode dans la mémoire fichier
6. Retourne un AgentOutput

À partir de la Phase 2, on injectera des few-shot examples depuis Chroma.
À partir de la Phase 5, on fera de l'A/B testing sur les prompts versionnés.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from src.core.config import Settings, get_settings
from src.core.logging import get_logger
from src.core.pricing import estimate_cost
from src.memory.file_memory import FileMemory, MemoryRecord


class AgentInput(BaseModel):
    mission_id: UUID
    task: str
    context: dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    agent_name: str
    raw_text: str
    parsed: Any | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    success: bool = True
    error: str | None = None


class BaseAgent:
    """Agent générique. Chaque rôle hérite et override `parse_output` si besoin."""

    def __init__(
        self,
        name: str,
        prompt_path: Path,
        model: str,
        memory: FileMemory,
        settings: Settings | None = None,
        client: AsyncAnthropic | None = None,
        max_tokens: int = 2048,
    ) -> None:
        self.name = name
        self.prompt_path = prompt_path
        self.model = model
        self.memory = memory
        self.settings = settings or get_settings()
        self.max_tokens = max_tokens
        self._log = get_logger(f"agent.{name}")

        if client is not None:
            self.client = client
        else:
            self.client = AsyncAnthropic(
                api_key=self.settings.anthropic_api_key.get_secret_value()
            )

        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        if not self.prompt_path.exists():
            raise FileNotFoundError(f"System prompt absent : {self.prompt_path}")
        text = self.prompt_path.read_text(encoding="utf-8")
        record = MemoryRecord.from_markdown(text)
        return record.body

    def build_user_message(self, agent_input: AgentInput) -> str:
        """Assemble le message utilisateur en injectant la tâche et le contexte."""
        parts = [f"# Tâche\n\n{agent_input.task.strip()}"]
        if agent_input.context:
            ctx_lines = []
            for key, value in agent_input.context.items():
                if isinstance(value, str):
                    ctx_lines.append(f"## {key}\n\n{value.strip()}")
                else:
                    ctx_lines.append(f"## {key}\n\n```json\n{value}\n```")
            parts.append("# Contexte\n\n" + "\n\n".join(ctx_lines))
        return "\n\n".join(parts)

    def parse_output(self, raw: str, agent_input: AgentInput) -> Any:
        """Override pour interpréter la sortie (yaml, json, code blocks…). Default = passthrough."""
        return None

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        user_message = self.build_user_message(agent_input)
        started = time.perf_counter()
        started_at = datetime.now(UTC)

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
            tokens_in = response.usage.input_tokens
            tokens_out = response.usage.output_tokens
            cost = estimate_cost(self.model, tokens_in, tokens_out)
            duration = time.perf_counter() - started
            parsed = self.parse_output(raw, agent_input)

            output = AgentOutput(
                agent_name=self.name,
                raw_text=raw,
                parsed=parsed,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
                duration_seconds=duration,
                success=True,
            )
            self._log.info(
                "agent.run.ok",
                agent=self.name,
                mission=str(agent_input.mission_id),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=round(cost, 6),
                duration_s=round(duration, 2),
            )
        except Exception as exc:  # noqa: BLE001
            duration = time.perf_counter() - started
            self._log.error(
                "agent.run.failed",
                agent=self.name,
                mission=str(agent_input.mission_id),
                error=str(exc),
                exc_info=True,
            )
            output = AgentOutput(
                agent_name=self.name,
                raw_text="",
                parsed=None,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                duration_seconds=duration,
                success=False,
                error=str(exc),
            )

        self._record_episode(agent_input, output, started_at)
        return output

    def _record_episode(
        self, agent_input: AgentInput, output: AgentOutput, started_at: datetime
    ) -> None:
        ended_at = datetime.now(UTC)
        record = MemoryRecord(
            metadata={
                "mission_id": str(agent_input.mission_id),
                "agent": self.name,
                "model": self.model,
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "tokens_in": output.tokens_in,
                "tokens_out": output.tokens_out,
                "cost_usd": round(output.cost_usd, 6),
                "duration_seconds": round(output.duration_seconds, 3),
                "success": output.success,
                "error": output.error,
            },
            body=(
                f"## Tâche\n\n{agent_input.task}\n\n"
                f"## Sortie brute\n\n{output.raw_text or '(aucune)'}\n"
            ),
        )
        self.memory.write_episode(agent_input.mission_id, self.name, record)
