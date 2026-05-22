"""missions_rag — RAG sur les missions archivées (v0.9.0 A1).

Capitalise sur l'historique : avant de lancer une nouvelle mission, on
cherche les missions sémantiquement similaires dans les archives et on
injecte un résumé dans le contexte de l'orchestrator. Les agents
bénéficient ainsi de l'apprentissage passé sans avoir à fine-tuner.

Architecture :
- Une collection Chroma dédiée `agent_missions` (séparée des épisodes
  et des skills, pour des distances cohérentes intra-collection).
- `index_mission(summary)` : appelé en hook post-mission (Workflow), indexe
  un mission summary avec ses métadonnées clés (guild, verdict, score…).
- `find_similar(title, description, n=3)` : retourne les top-N missions
  similaires avec score de pertinence ; filtrable par guilde, verdict
  minimum, exclusion d'une mission_id (typiquement la mission courante).
- `render_for_prompt(matches)` : compacte les matches en texte injectable.

Politique de qualité : on n'indexe QUE les missions APPROVED (les NEEDS_CHANGES
ou REJECTED pollueraient les suggestions futures). Le filtrage est appliqué
au moment de l'indexation, pas du search — comme ça si on désactive un
critère plus tard, l'historique reste exploitable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.logging import get_logger
from src.memory.file_memory import MemoryRecord
from src.memory.vector_memory import EpisodeMatch, VectorMemory

_log = get_logger("missions_rag")

# Collection Chroma dédiée — séparée des "agent_episodes" (épisodes individuels
# d'agents) et "agent_skills" (skills extraites). Distances cohérentes
# intra-collection (cosine sur embeddings textuels Chroma défaut).
MISSIONS_COLLECTION = "agent_missions"


@dataclass
class SimilarMission:
    """Une mission similaire trouvée par RAG, présentée à l'orchestrator."""

    mission_id: str
    title: str
    guild: str
    final_verdict: str
    quality_score: float | None
    summary: str  # tronqué/résumé pour ne pas exploser le contexte
    distance: float  # 0 = identique, ~1 = orthogonal (cosine)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def relevance(self) -> float:
        """Score 0..1 (1 = très similaire). `1 - distance` capé à [0, 1]."""
        return max(0.0, min(1.0, 1.0 - self.distance))


class MissionsRAG:
    """Service de RAG sur les missions archivées.

    Construit en injectant une `VectorMemory` configurée sur la collection
    `agent_missions`. L'appelant gère la persistance Chroma (déjà fait par
    `VectorMemory(persist_dir=...)`).
    """

    def __init__(self, vector_memory: VectorMemory) -> None:
        self.vector_memory = vector_memory

    # ------------------------------------------------------------------
    # Indexation
    # ------------------------------------------------------------------

    def index_mission(
        self,
        mission_id: str,
        title: str,
        description: str,
        summary_record: MemoryRecord,
    ) -> bool:
        """Indexe une mission dans la collection.

        Politique : n'indexe QUE les missions APPROVED (les autres polluent).
        Retourne True si indexé, False si filtré (verdict non APPROVED, ou
        données manquantes).

        L'`episode_id` est `mission_{mission_id}` pour le distinguer
        des épisodes agent dans une collection partagée éventuelle.
        """
        meta = summary_record.metadata
        verdict = str(meta.get("final_verdict", "")).upper()
        if verdict != "APPROVED":
            _log.debug(
                "missions_rag.skip.verdict",
                mission_id=mission_id,
                verdict=verdict,
            )
            return False

        # Document = titre + description + résumé du reviewer. C'est ce
        # qu'on cherchera sémantiquement plus tard (par titre+description
        # d'une nouvelle mission). Inclure le summary capture le "comment
        # ça s'est résolu", utile pour suggérer des approches.
        document = (
            f"# {title}\n\n"
            f"## Description\n{description}\n\n"
            f"## Résumé du Reviewer\n{meta.get('review_summary', '') or '(pas de résumé)'}\n"
        )

        flat_meta: dict[str, Any] = {
            "mission_id": str(mission_id),
            "title": title[:200],
            "guild": str(meta.get("guild", "")),
            "final_verdict": verdict,
            "quality_score": _safe_float(meta.get("quality_score")),
            "total_cost_usd": _safe_float(meta.get("total_cost_usd")),
            "total_duration_seconds": _safe_float(meta.get("total_duration_seconds")),
        }

        try:
            self.vector_memory.add_episode(
                episode_id=f"mission_{mission_id}",
                document=document[:8000],  # garde-fou Chroma
                metadata=flat_meta,
            )
        except Exception as exc:
            _log.warning(
                "missions_rag.index.failed",
                mission_id=mission_id,
                error=str(exc),
            )
            return False

        _log.info("missions_rag.indexed", mission_id=mission_id, guild=flat_meta["guild"])
        return True

    # ------------------------------------------------------------------
    # Recherche
    # ------------------------------------------------------------------

    def find_similar(
        self,
        title: str,
        description: str,
        n_results: int = 3,
        guild: str | None = None,
        min_quality_score: float | None = None,
        max_distance: float = 0.85,
        exclude_mission_id: str | None = None,
    ) -> list[SimilarMission]:
        """Cherche les missions les plus similaires.

        - `n_results` : top-N à retourner.
        - `guild` : filtre Chroma sur la guilde (optionnel).
        - `min_quality_score` : filtre Python post-Chroma sur le score.
        - `max_distance` : seuil de pertinence (0.85 par défaut = très permissif,
          baisser à 0.5 pour des matches plus serrés).
        - `exclude_mission_id` : exclut une mission spécifique (typiquement
          la mission en cours, pour éviter le self-reference).
        """
        query = f"# {title}\n\n{description}"
        where: dict[str, Any] | None = None
        if guild:
            where = {"guild": guild}

        # Sur-demande pour absorber les filtres Python en aval
        raw_n = n_results * 3 if (exclude_mission_id or min_quality_score) else n_results
        try:
            matches: list[EpisodeMatch] = self.vector_memory.search(
                query=query,
                n_results=raw_n,
                where=where,
                max_distance=max_distance,
            )
        except Exception as exc:
            _log.warning("missions_rag.search.failed", error=str(exc))
            return []

        results: list[SimilarMission] = []
        for m in matches:
            mid = str(m.metadata.get("mission_id", "")).strip()
            if not mid:
                continue
            if exclude_mission_id and mid == str(exclude_mission_id):
                continue
            score = m.metadata.get("quality_score")
            if min_quality_score is not None and (
                not isinstance(score, (int, float)) or score < min_quality_score
            ):
                continue
            results.append(
                SimilarMission(
                    mission_id=mid,
                    title=str(m.metadata.get("title", "(no title)")),
                    guild=str(m.metadata.get("guild", "")),
                    final_verdict=str(m.metadata.get("final_verdict", "")),
                    quality_score=score if isinstance(score, (int, float)) else None,
                    summary=_extract_summary_from_document(m.document),
                    distance=m.distance,
                    raw_metadata=dict(m.metadata),
                )
            )
            if len(results) >= n_results:
                break
        return results

    # ------------------------------------------------------------------
    # Rendu pour prompt
    # ------------------------------------------------------------------

    @staticmethod
    def render_for_prompt(
        matches: list[SimilarMission],
        max_chars_per_match: int = 400,
    ) -> str:
        """Compacte les matches en texte injectable dans un prompt.

        Format minimaliste : titre + verdict + score + extrait du résumé.
        Optimisé pour ne pas exploser le contexte (~150-200 tokens pour 3 matches).
        """
        if not matches:
            return ""
        lines = [
            "## Missions similaires déjà réalisées (RAG)",
            "",
            "Apprends de ces missions passées avant de proposer ta décomposition :",
            "",
        ]
        for i, m in enumerate(matches, start=1):
            score_str = f"{m.quality_score:.2f}" if m.quality_score is not None else "—"
            summary_excerpt = m.summary[:max_chars_per_match].strip()
            if len(m.summary) > max_chars_per_match:
                summary_excerpt += "…"
            lines.extend(
                [
                    f"### #{i} — {m.title} (relevance {m.relevance:.0%})",
                    f"- **Guilde** : `{m.guild}`",
                    f"- **Verdict** : `{m.final_verdict}` · score `{score_str}`",
                    f"- **Résumé** : {summary_excerpt or '(pas de résumé disponible)'}",
                    "",
                ]
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float | None:
    """Convertit en float si possible, sinon None (pour métadonnées Chroma)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_summary_from_document(document: str) -> str:
    """Extrait le ## Résumé du Reviewer depuis le document indexé.

    Le document a la structure :
        # <title>
        ## Description
        <description>
        ## Résumé du Reviewer
        <résumé>

    On retourne juste la partie résumé (utile pour le rendu de prompt).
    """
    marker = "## Résumé du Reviewer"
    if marker not in document:
        return document[:500]  # fallback : début du document brut
    return document.split(marker, 1)[1].strip()
