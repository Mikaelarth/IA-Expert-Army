"""QualityGuardian — peer review méta cross-guilde (Sprint YY).

Le reviewer interne d'une guilde juge la qualité TECHNIQUE de l'output dans
son domaine. Le QualityGuardian juge 4 axes que personne d'autre ne juge :

1. Alignement promesse ↔ livraison (la demande utilisateur est-elle satisfaite ?)
2. Dérive de scope (over-engineering ou under-delivery)
3. Cohérence inter-guilde (pour les meta-missions)
4. Calibration du verdict guilde (score défendable ?)

Intégré dans le `MissionRouter` en mode opt-in (Setting `enable_quality_guardian`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel

from src.core.config import Settings, get_settings
from src.core.logging import get_logger
from src.memory.file_memory import FileMemory
from src.orchestrator.agents._parsers import extract_yaml
from src.orchestrator.base_agent import AgentInput, BaseAgent

log = get_logger("quality_guardian")

VERDICT_QG_ACCEPT = "ACCEPT"
VERDICT_QG_NEEDS_REWORK = "NEEDS_REWORK"
VERDICT_QG_ESCALATE = "ESCALATE"

_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "orchestrator" / "quality_guardian.md"


class QGVerdict(BaseModel):
    """Verdict structuré du Quality Guardian."""

    verdict_qg: str  # ACCEPT | NEEDS_REWORK | ESCALATE
    final_score: float | None = None
    alignment_check: str = ""
    scope_check: str = ""
    verdict_calibration: str = ""
    meta_concerns: list[str] = []
    rationale: str = ""

    @property
    def accepted(self) -> bool:
        return self.verdict_qg == VERDICT_QG_ACCEPT

    @property
    def needs_rework(self) -> bool:
        return self.verdict_qg == VERDICT_QG_NEEDS_REWORK


class QualityGuardian(BaseAgent):
    """Agent stratégique (Opus) qui audite l'alignement promesse↔livraison."""

    DEFAULT_MAX_TOKENS = 2048  # Verdict YAML compact + concerns courts

    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        s = settings or get_settings()
        super().__init__(
            name="quality_guardian",
            prompt_path=_PROMPT,
            model=s.model_strategic,  # Opus : besoin de discernement
            memory=memory,
            settings=s,
            client=client,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            vector_memory=None,  # pas d'auto-influence — le QG juge from scratch
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> dict[str, Any] | None:
        return extract_yaml(raw)


async def review_mission(
    qg: QualityGuardian,
    mission_title: str,
    mission_description: str,
    guild: str,
    guild_verdict: str,
    guild_score: float | None,
    guild_summary: str,
    raw_result_excerpt: str = "",
) -> QGVerdict | None:
    """Lance le QG sur le résultat d'une mission de guilde.

    Retourne `None` si l'appel échoue ou si la sortie ne parse pas — le caller
    décide alors de la politique de fallback (typiquement : passer outre).
    """
    # Skip si la guilde a déjà REJECTED — pas de raison d'override.
    if guild_verdict == "REJECTED":
        log.info("qg.skip_rejected", reason="guild_already_rejected")
        return QGVerdict(
            verdict_qg=VERDICT_QG_ACCEPT,
            final_score=guild_score,
            rationale="Verdict REJECTED de la guilde validé sans appel.",
        )

    score_str = f"{guild_score:.2f}" if guild_score is not None else "n/a"
    task = (
        f"## Mission utilisateur\n\n"
        f"**Titre :** {mission_title}\n\n"
        f"**Description :**\n{mission_description}\n\n"
        f"## Verdict de la guilde {guild}\n\n"
        f"**Verdict :** {guild_verdict}\n"
        f"**Score :** {score_str}\n\n"
        f"**Résumé du reviewer interne :**\n{guild_summary}\n\n"
    )
    if raw_result_excerpt:
        # On limite à 3000 chars pour ne pas saturer le QG sur de longs outputs
        task += (
            f"## Extrait de la livraison\n\n"
            f"{raw_result_excerpt[:3000]}\n"
            f"{'...[tronqué]' if len(raw_result_excerpt) > 3000 else ''}\n"
        )

    from uuid import uuid4

    out = await qg.run(AgentInput(mission_id=uuid4(), task=task))
    if not out.success or out.parsed is None:
        log.warning(
            "qg.failed",
            success=out.success,
            parsed_ok=out.parsed is not None,
            error=out.error,
        )
        return None

    parsed = out.parsed
    verdict = str(parsed.get("verdict_qg", "")).strip().upper()
    if verdict not in {VERDICT_QG_ACCEPT, VERDICT_QG_NEEDS_REWORK, VERDICT_QG_ESCALATE}:
        log.warning("qg.invalid_verdict", verdict=verdict)
        return None

    final_score_raw = parsed.get("final_score")
    final_score = float(final_score_raw) if isinstance(final_score_raw, (int, float)) else None
    concerns_raw = parsed.get("meta_concerns") or []
    if not isinstance(concerns_raw, list):
        concerns_raw = []

    return QGVerdict(
        verdict_qg=verdict,
        final_score=final_score,
        alignment_check=str(parsed.get("alignment_check", "")).strip(),
        scope_check=str(parsed.get("scope_check", "")).strip(),
        verdict_calibration=str(parsed.get("verdict_calibration", "")).strip(),
        meta_concerns=[str(c).strip() for c in concerns_raw if str(c).strip()][:3],
        rationale=str(parsed.get("rationale", "")).strip(),
    )
