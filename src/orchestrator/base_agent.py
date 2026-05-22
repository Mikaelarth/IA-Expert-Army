"""BaseAgent — classe de base pour tous les agents de l'armée.

Cycle de vie d'un agent en Phase 1 :
1. Charge son system prompt depuis `prompts/<path>.md` (avec frontmatter)
2. Reçoit un AgentInput (mission_id + task + context)
3. Construit les messages Claude (system + user contextualisé)
4. Appelle le LLM via AsyncOpenAI (Ollama OpenAI-compatible)
5. Logue un episode dans la mémoire fichier
6. Retourne un AgentOutput

À partir de la Phase 2, on injectera des few-shot examples depuis Chroma.
À partir de la Phase 5, on fera de l'A/B testing sur les prompts versionnés.

Bascule v0.4.0 (ADR-025) : le backend LLM est passé d'AsyncAnthropic
(API Claude payante) à AsyncOpenAI pointé sur Ollama local. L'interface
expose la même surface aux agents (`run()` → `AgentOutput`), mais les
mappings techniques changent :
- `system=...` devient un message `{"role": "system", "content": ...}`
- `response.content[0].text` devient `response.choices[0].message.content`
- `response.usage.input_tokens` → `response.usage.prompt_tokens`
- `response.usage.output_tokens` → `response.usage.completion_tokens`
- `stop_reason="max_tokens"` (Anthropic) → `finish_reason="length"` (OpenAI)
- coût USD systématiquement 0 (local)
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from openai import AsyncOpenAI
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
    # Détecté soit explicitement (finish_reason == "length" côté OpenAI/Ollama,
    # équivalent du "max_tokens" Anthropic), soit en garde-fou quand tokens_out
    # atteint quasi le plafond. Une saturation invisible était la cause des
    # incidents Tech Watch (mission 7b5759b1) et Research Reviewer (mission
    # 359bfa08) : sortie tronquée → YAML cassé → verdict default REJECTED.
    saturated: bool = False
    stop_reason: str | None = None
    # v0.9.0 A2 — si l'A/B testing prompts est activé pour cet agent, on
    # tracke quelle variante a été utilisée. None = canonique ou A/B désactivé.
    # Le Workflow exploitera ce field en fin de mission pour persister les
    # outcomes via PromptAB.track_outcome().
    prompt_variant_label: str | None = None


class BaseAgent:
    """Agent générique. Chaque rôle hérite et override `parse_output` si besoin."""

    def __init__(
        self,
        name: str,
        prompt_path: Path,
        model: str,
        memory: FileMemory,
        settings: Settings | None = None,
        client: AsyncOpenAI | None = None,
        max_tokens: int = 2048,
        vector_memory: VectorMemory | None = None,
        rag_top_k: int = 2,
        rag_max_distance: float = 0.7,
        skills_library: SkillsLibrary | None = None,
        skills_top_k: int = 2,
        prompt_ab: Any | None = None,  # PromptAB — duck-typed pour éviter cycle import
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
        # v0.9.0 A2 — A/B testing des variantes de prompts. Si fourni ET
        # `self.name` est dans `settings.ab_testing_agents_set`, on pick
        # une variante par mission_id (déterministe). Sinon canonique.
        self.prompt_ab = prompt_ab
        self._log = get_logger(f"agent.{name}")

        if client is not None:
            self.client = client
        else:
            # Client OpenAI-compatible pointé sur Ollama (ADR-025). Ollama
            # ignore l'api_key mais le SDK la requiert : on passe un
            # placeholder. Retries + timeout configurables — généreux car
            # un Qwen 32B local peut prendre plusieurs minutes à générer
            # 16k tokens sans GPU costaud.
            self.client = AsyncOpenAI(
                base_url=self.settings.ollama_base_url,
                api_key=self.settings.ollama_api_key,
                max_retries=self.settings.ollama_max_retries,
                timeout=self.settings.ollama_timeout_seconds,
            )
            self._log.debug(
                "client.configured",
                base_url=self.settings.ollama_base_url,
                max_retries=self.settings.ollama_max_retries,
                timeout_s=self.settings.ollama_timeout_seconds,
            )

        # v0.8.0 F4 — si hot_reload_prompts=True (opt-in via Settings),
        # le prompt est re-lu disque à chaque appel via `_get_system_prompt()`.
        # Sinon, il est chargé une fois ici et caché dans self._system_prompt_cache.
        self._system_prompt_cache = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        if not self.prompt_path.exists():
            raise FileNotFoundError(f"System prompt absent : {self.prompt_path}")
        text = self.prompt_path.read_text(encoding="utf-8")
        record = MemoryRecord.from_markdown(text)
        return record.body

    @property
    def system_prompt(self) -> str:
        """Prompt système courant. Re-lit le disque si hot_reload activé.

        v0.8.0 F4 — opt-in via Settings.hot_reload_prompts. Quand True,
        permet de modifier prompts/**/*.md sans redémarrer Streamlit/CLI.
        Overhead négligeable (~10 ms par appel LLM de 30s+).
        """
        if self.settings.hot_reload_prompts:
            try:
                return self._load_system_prompt()
            except (OSError, FileNotFoundError) as exc:
                # Si le fichier est en cours d'édition (write atomique en 2 temps),
                # on retombe sur le cache pour ne pas crasher la mission.
                self._log.warning(
                    "prompt.hot_reload.fallback_to_cache",
                    error=str(exc),
                    path=str(self.prompt_path),
                )
                return self._system_prompt_cache
        return self._system_prompt_cache

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
            from src.learning.skills_library import SkillsLibrary

            parts.append(SkillsLibrary.render_for_prompt(skills))
        return "\n\n".join(parts)

    def _retrieve_skills(self, agent_input: AgentInput | None = None) -> list[Skill]:
        """Charge les N skills les plus pertinentes (sémantique si possible, sinon récentes).

        v0.7.0 — exclut les skills produites à partir d'épisodes de la mission
        courante (`exclude_mission_ids={agent_input.mission_id}`) pour parer le
        risque de boucle auto-référentielle si un mining online était déployé.
        """
        if self.skills_library is None or self.skills_top_k <= 0:
            return []
        query = agent_input.task if agent_input is not None else None
        exclude: set[str] | None = None
        if agent_input is not None and agent_input.mission_id:
            exclude = {str(agent_input.mission_id)}
        try:
            return self.skills_library.search_skills(
                self.name,
                query=query,
                n_results=self.skills_top_k,
                exclude_mission_ids=exclude,
            )
        except Exception as exc:
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

    def _detect_saturation(self, tokens_out: int, max_tokens: int, stop_reason: str | None) -> bool:
        """Vrai si la réponse a été coupée par max_tokens.

        Deux signaux convergents :
        - finish_reason == "length" → l'API OpenAI/Ollama le dit explicitement
          (équivalent du "max_tokens" Anthropic, signal fort)
        - tokens_out >= max_tokens × 0.99 → garde-fou si l'API a un finish_reason
          ambigu mais que le compteur est au taquet
        """
        if stop_reason == "length":
            return True
        return max_tokens > 0 and tokens_out >= int(max_tokens * self._SATURATION_TOKEN_RATIO)

    def _resolve_system_prompt(self, agent_input: AgentInput) -> tuple[str, str | None]:
        """Retourne (prompt_text, variant_label) à utiliser pour cet appel.

        v0.9.0 A2 — si `self.prompt_ab` est fourni ET l'agent est listé dans
        `settings.ab_testing_agents_set`, on pick une variante par mission_id
        (déterministe, resume-safe). Sinon, on retourne le système prompt
        canonique (avec hot-reload si activé).

        Tolérant : si la résolution A/B plante (fichier manquant, etc.), on
        fallback sur le canonique sans crasher la mission.
        """
        if self.prompt_ab is None:
            return self.system_prompt, None
        try:
            variant = self.prompt_ab.pick_variant(
                self.prompt_path,
                mission_id=str(agent_input.mission_id),
                enabled_agents=self.settings.ab_testing_agents_set,
            )
            if variant.is_canonical:
                return self.system_prompt, None
            text = variant.path.read_text(encoding="utf-8")
            body = MemoryRecord.from_markdown(text).body
            return body, variant.label
        except Exception as exc:
            self._log.warning(
                "prompt_ab.resolve.fallback",
                agent=self.name,
                error=str(exc),
            )
            return self.system_prompt, None

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
        except Exception as exc:
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
        user_message = self.build_user_message(agent_input, precedents=precedents, skills=skills)
        started = time.perf_counter()
        started_at = datetime.now(UTC)

        # v0.9.0 A2 — résolution A/B de la variante de prompt à utiliser.
        # Si A/B activé pour cet agent : variante pickée par mission_id ;
        # son body remplace self.system_prompt. Le label est attaché à l'output
        # pour tracking ultérieur par le Workflow.
        system_prompt_text, variant_label = self._resolve_system_prompt(agent_input)

        try:
            # Chat completions OpenAI-compatible : le system devient un message
            # avec role="system" en tête (Ollama suit la même convention).
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt_text},
                    {"role": "user", "content": user_message},
                ],
            )
            choice = response.choices[0]
            raw = choice.message.content or ""
            usage = response.usage
            tokens_in = getattr(usage, "prompt_tokens", 0) if usage is not None else 0
            tokens_out = getattr(usage, "completion_tokens", 0) if usage is not None else 0
            stop_reason = choice.finish_reason
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
                prompt_variant_label=variant_label,
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
        except Exception as exc:
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
            except Exception as exc:
                self._log.warning("rag.index.failed", error=str(exc))
