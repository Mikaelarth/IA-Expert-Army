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
from src.core.tracing import observe
from src.learning.skills_library import Skill, SkillsLibrary
from src.memory.file_memory import FileMemory, MemoryRecord
from src.memory.vector_memory import EpisodeMatch, VectorMemory


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
    # Marqueur de saturation : True si la réponse a été coupée par max_tokens.
    # Détecté soit explicitement (stop_reason == "max_tokens"), soit en garde-fou
    # quand tokens_out atteint quasi le plafond. Une saturation invisible était la
    # cause des incidents Tech Watch (mission 7b5759b1) et Research Reviewer
    # (mission 359bfa08) : sortie tronquée → YAML cassé → verdict default REJECTED.
    saturated: bool = False
    stop_reason: str | None = None


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
        vector_memory: VectorMemory | None = None,
        rag_top_k: int = 2,
        rag_max_distance: float = 0.7,
        skills_library: SkillsLibrary | None = None,
        skills_top_k: int = 2,
    ) -> None:
        self.name = name
        self.prompt_path = prompt_path
        self.model = model
        self.memory = memory
        self.vector_memory = vector_memory
        self.rag_top_k = rag_top_k
        self.rag_max_distance = rag_max_distance
        self.skills_library = skills_library
        self.skills_top_k = skills_top_k
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

    def build_user_message(
        self,
        agent_input: AgentInput,
        precedents: list[EpisodeMatch] | None = None,
        skills: list[Skill] | None = None,
    ) -> str:
        """Assemble le message utilisateur : tâche + contexte + précédents + skills."""
        parts = [f"# Tâche\n\n{agent_input.task.strip()}"]
        if agent_input.context:
            ctx_lines = []
            for key, value in agent_input.context.items():
                if isinstance(value, str):
                    ctx_lines.append(f"## {key}\n\n{value.strip()}")
                else:
                    ctx_lines.append(f"## {key}\n\n```json\n{value}\n```")
            parts.append("# Contexte\n\n" + "\n\n".join(ctx_lines))
        if precedents:
            prec_lines = [
                "# Précédents pertinents (mémoire de l'équipe)",
                "",
                "Voici des épisodes passés similaires de TON propre rôle. Inspire-toi de ce qui a marché, "
                "évite ce qui a échoué. Cite explicitement un précédent si tu réutilises son approche.",
                "",
            ]
            for i, p in enumerate(precedents, 1):
                title = p.metadata.get("mission_title") or p.metadata.get("agent") or "épisode"
                score = p.metadata.get("quality_score")
                score_str = f" · score {score:.2f}" if isinstance(score, (int, float)) else ""
                prec_lines.append(
                    f"## Précédent {i} : « {title} »{score_str} (similarité : {1 - p.distance:.2f})"
                )
                prec_lines.append("")
                prec_lines.append(self._truncate(p.document, 800))
                prec_lines.append("")
            parts.append("\n".join(prec_lines))
        if skills:
            from src.learning.skills_library import SkillsLibrary as _SL
            parts.append(_SL.render_for_prompt(skills))
        return "\n\n".join(parts)

    def _retrieve_skills(self, agent_input: AgentInput | None = None) -> list[Skill]:
        """Charge les N skills les plus pertinentes (sémantique si possible, sinon récentes)."""
        if self.skills_library is None or self.skills_top_k <= 0:
            return []
        query = agent_input.task if agent_input is not None else None
        try:
            return self.skills_library.search_skills(
                self.name, query=query, n_results=self.skills_top_k
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning("skills.load.failed", error=str(exc))
            return []

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "\n…[tronqué]"

    # Seuil sous lequel on considère qu'une réponse n'est PAS saturée même si
    # le compteur de tokens approche le plafond (marge pour bruit d'arrondi API).
    _SATURATION_TOKEN_RATIO = 0.99

    def _detect_saturation(
        self, tokens_out: int, max_tokens: int, stop_reason: str | None
    ) -> bool:
        """Vrai si la réponse a été coupée par max_tokens.

        Deux signaux convergents :
        - stop_reason == "max_tokens" → l'API le dit explicitement (signal fort)
        - tokens_out >= max_tokens × 0.99 → garde-fou si l'API a un stop_reason
          ambigu mais que le compteur est au taquet
        """
        if stop_reason == "max_tokens":
            return True
        if max_tokens > 0 and tokens_out >= int(max_tokens * self._SATURATION_TOKEN_RATIO):
            return True
        return False

    def _retrieve_precedents(self, agent_input: AgentInput) -> list[EpisodeMatch]:
        """Cherche dans la mémoire vectorielle les épisodes passés pertinents."""
        if self.vector_memory is None or self.vector_memory.count() == 0:
            return []
        try:
            return self.vector_memory.search(
                query=agent_input.task,
                n_results=self.rag_top_k,
                where={
                    "$and": [
                        {"agent": self.name},
                        {"success": True},
                    ]
                },
                max_distance=self.rag_max_distance,
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning("rag.search.failed", error=str(exc))
            return []

    def parse_output(self, raw: str, agent_input: AgentInput) -> Any:
        """Override pour interpréter la sortie (yaml, json, code blocks…). Default = passthrough."""
        return None

    @observe(name="agent.run", as_type="generation")
    async def run(self, agent_input: AgentInput) -> AgentOutput:
        precedents = self._retrieve_precedents(agent_input)
        if precedents:
            self._log.info(
                "rag.precedents.injected",
                agent=self.name,
                count=len(precedents),
                ids=[p.episode_id for p in precedents],
            )
        skills = self._retrieve_skills(agent_input)
        if skills:
            self._log.info(
                "skills.injected",
                agent=self.name,
                count=len(skills),
                titles=[s.title for s in skills],
            )
        user_message = self.build_user_message(
            agent_input, precedents=precedents, skills=skills
        )
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
            stop_reason = getattr(response, "stop_reason", None)
            cost = estimate_cost(self.model, tokens_in, tokens_out)
            duration = time.perf_counter() - started
            parsed = self.parse_output(raw, agent_input)
            saturated = self._detect_saturation(tokens_out, self.max_tokens, stop_reason)

            output = AgentOutput(
                agent_name=self.name,
                raw_text=raw,
                parsed=parsed,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
                duration_seconds=duration,
                success=True,
                saturated=saturated,
                stop_reason=stop_reason,
            )
            self._log.info(
                "agent.run.ok",
                agent=self.name,
                mission=str(agent_input.mission_id),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=round(cost, 6),
                duration_s=round(duration, 2),
                stop_reason=stop_reason,
            )
            if saturated:
                # Warning visible : la sortie a été coupée. Le caller (workflow)
                # n'a aucune façon de récupérer un YAML/markdown tronqué silencieusement,
                # donc on s'assure que le diagnostic est immédiat dans les logs.
                self._log.warning(
                    "agent.output.saturated",
                    agent=self.name,
                    mission=str(agent_input.mission_id),
                    tokens_out=tokens_out,
                    max_tokens=self.max_tokens,
                    stop_reason=stop_reason,
                    advice=(
                        "La réponse est probablement tronquée. Augmente max_tokens pour ce rôle "
                        "ou réduis la verbosité du system prompt."
                    ),
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
        metadata = {
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
            "saturated": output.saturated,
            "stop_reason": output.stop_reason,
        }
        body = (
            f"## Tâche\n\n{agent_input.task}\n\n"
            f"## Sortie brute\n\n{output.raw_text or '(aucune)'}\n"
        )
        record = MemoryRecord(metadata=metadata, body=body)
        self.memory.write_episode(agent_input.mission_id, self.name, record)

        # Indexation sémantique (Phase 2)
        if self.vector_memory is not None and output.success:
            try:
                # On indexe : tâche + sortie pour permettre à la fois la recherche
                # par similarité de question ET par similarité de solution.
                indexed_doc = (
                    f"Tâche: {agent_input.task}\n\n"
                    f"Sortie:\n{self._truncate(output.raw_text or '', 2000)}"
                )
                episode_id = f"{agent_input.mission_id}_{self.name}_{int(started_at.timestamp())}"
                self.vector_memory.add_episode(
                    episode_id=episode_id,
                    document=indexed_doc,
                    metadata=metadata,
                )
            except Exception as exc:  # noqa: BLE001
                self._log.warning("rag.index.failed", error=str(exc))
