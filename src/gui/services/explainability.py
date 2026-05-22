"""explainability — services pour la page "🔍 Explainability" (v0.9.0 C1).

Trois capacités séparées, regroupées dans un seul module pour limiter le
nombre de services GUI :

1. `explain_guild_classification` — pour une mission (title + description),
   re-joue le scoring détaillé de l'HeuristicGuildClassifier : score par
   guilde + mots-clés matchés + tie-break. Permet de comprendre POURQUOI
   le router a tranché engineering plutôt que research.

2. `compute_agent_metrics` — agrège depuis FileMemory les métriques par
   agent (latence moyenne, score moyen, taux d'échec, nombre d'épisodes).
   Permet d'identifier les agents qui dérivent (drift de qualité, latence
   en hausse).

3. `explain_mission_verdict` — pour un mission_id, recharge le summary +
   épisodes et extrait le raisonnement du Reviewer (résumé + score
   composantes si disponibles dans le YAML brut). Permet de répondre
   à "pourquoi 0.87 et pas 0.95 ?".

Aucune dépendance Streamlit ici — pure logique testable hors AppTest.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from src.memory.file_memory import FileMemory, MemoryRecord
from src.orchestrator.router import (
    _BUSINESS_KEYWORDS,
    _CREATIVE_KEYWORDS,
    _ENGINEERING_KEYWORDS,
    _RESEARCH_KEYWORDS,
    _STRONG_ACTION_VERBS,
    HeuristicGuildClassifier,
)

# ============================================================================
# 1. Classifier explainability
# ============================================================================


@dataclass
class KeywordMatch:
    """Un mot-clé matché dans une mission, avec son poids et sa position."""

    keyword: str
    in_title: bool
    is_strong_verb: bool
    weight: int  # points contribués (calculés via TITLE_WEIGHT + bonus)


@dataclass
class GuildScore:
    """Score détaillé pour une guilde donnée."""

    guild: str
    total_score: int
    matches: list[KeywordMatch] = field(default_factory=list)


@dataclass
class ClassificationExplanation:
    """Explication complète du choix de guilde par l'héuristique."""

    title: str
    description: str
    scores: list[GuildScore]  # une entrée par guilde, triée par score desc
    winner: str
    is_tie: bool  # True si ≥ 2 guildes à égalité (tie-break par maturité a tranché)
    tie_break_order: list[str] = field(
        default_factory=lambda: ["engineering", "research", "creative", "business"]
    )


_GUILD_KEYWORDS = {
    "engineering": _ENGINEERING_KEYWORDS,
    "research": _RESEARCH_KEYWORDS,
    "creative": _CREATIVE_KEYWORDS,
    "business": _BUSINESS_KEYWORDS,
}


def explain_guild_classification(title: str, description: str) -> ClassificationExplanation:
    """Re-joue le classifier héuristique en collectant les matchs détaillés.

    Cohérent avec `HeuristicGuildClassifier.classify()` : mêmes keywords,
    mêmes poids (TITLE_WEIGHT + STRONG_VERB_BONUS), même tie-break ordre.
    """
    title_lower = title.lower()
    full_lower = f"{title}\n{description}".lower()

    scores: list[GuildScore] = []
    for guild, keywords in _GUILD_KEYWORDS.items():
        matches: list[KeywordMatch] = []
        total = 0
        for kw in keywords:
            in_title = HeuristicGuildClassifier._matches(kw, title_lower)
            in_body = HeuristicGuildClassifier._matches(kw, full_lower)
            is_strong = kw in _STRONG_ACTION_VERBS
            if in_title:
                weight = HeuristicGuildClassifier.TITLE_WEIGHT + (
                    HeuristicGuildClassifier.STRONG_VERB_BONUS if is_strong else 0
                )
            elif in_body:
                weight = 1 + (HeuristicGuildClassifier.STRONG_VERB_BONUS if is_strong else 0)
            else:
                continue
            matches.append(
                KeywordMatch(keyword=kw, in_title=in_title, is_strong_verb=is_strong, weight=weight)
            )
            total += weight
        # Tri matches par poids desc pour le rendu GUI
        matches.sort(key=lambda m: m.weight, reverse=True)
        scores.append(GuildScore(guild=guild, total_score=total, matches=matches))

    scores.sort(key=lambda s: s.total_score, reverse=True)

    # Détection tie + détermination winner via le même tie-break order que
    # HeuristicGuildClassifier (engineering > research > creative > business)
    max_score = scores[0].total_score
    tied_guilds = [s.guild for s in scores if s.total_score == max_score]
    is_tie = len(tied_guilds) > 1
    tie_break = ["engineering", "research", "creative", "business"]
    winner = next((g for g in tie_break if g in tied_guilds), tied_guilds[0])

    return ClassificationExplanation(
        title=title,
        description=description,
        scores=scores,
        winner=winner,
        is_tie=is_tie,
        tie_break_order=tie_break,
    )


# ============================================================================
# 2. Agent metrics (depuis FileMemory)
# ============================================================================


@dataclass
class AgentMetrics:
    """Métriques agrégées d'un agent sur tous ses épisodes."""

    agent_name: str
    n_episodes: int = 0
    n_success: int = 0
    n_saturated: int = 0
    avg_duration_seconds: float = 0.0
    avg_quality_score: float | None = None  # quand quality_score propagé
    avg_tokens_out: float = 0.0
    total_cost_usd: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.n_success / self.n_episodes if self.n_episodes else 0.0

    @property
    def saturation_rate(self) -> float:
        return self.n_saturated / self.n_episodes if self.n_episodes else 0.0


def compute_agent_metrics(memory: FileMemory) -> list[AgentMetrics]:
    """Parcourt tous les épisodes archivés et agrège par agent.

    Tolérant : un épisode malformé est skip silencieusement. Retourne une
    liste triée par n_episodes décroissant (les plus actifs d'abord).
    """
    grouped: dict[str, list[MemoryRecord]] = defaultdict(list)
    for path in memory.list_episodes():
        try:
            record = memory.read_episode(path)
        except OSError:
            continue
        agent = str(record.metadata.get("agent", "")).strip()
        if not agent:
            continue
        grouped[agent].append(record)

    metrics: list[AgentMetrics] = []
    for agent, episodes in grouped.items():
        n = len(episodes)
        if n == 0:
            continue
        m = AgentMetrics(agent_name=agent, n_episodes=n)
        for r in episodes:
            meta = r.metadata
            if meta.get("success"):
                m.n_success += 1
            if meta.get("saturated"):
                m.n_saturated += 1
            duration = meta.get("duration_seconds", 0.0)
            tokens_out = meta.get("tokens_out", 0)
            cost = meta.get("cost_usd", 0.0)
            if isinstance(duration, (int, float)):
                m.avg_duration_seconds += float(duration)
            if isinstance(tokens_out, (int, float)):
                m.avg_tokens_out += float(tokens_out)
            if isinstance(cost, (int, float)):
                m.total_cost_usd += float(cost)
        m.avg_duration_seconds = round(m.avg_duration_seconds / n, 2)
        m.avg_tokens_out = round(m.avg_tokens_out / n, 1)
        m.total_cost_usd = round(m.total_cost_usd, 6)

        # Quality score moyen (uniquement les épisodes où le score a été propagé)
        scored = [
            meta.get("quality_score")
            for r in episodes
            if isinstance((meta := r.metadata).get("quality_score"), (int, float))
        ]
        if scored:
            m.avg_quality_score = round(sum(scored) / len(scored), 3)

        metrics.append(m)

    metrics.sort(key=lambda x: x.n_episodes, reverse=True)
    return metrics


# ============================================================================
# 3. Mission verdict explainability
# ============================================================================


@dataclass
class MissionVerdictExplanation:
    """Détail du verdict d'une mission pour répondre à 'pourquoi 0.87 ?'."""

    mission_id: str
    title: str
    final_verdict: str
    quality_score: float | None
    review_summary: str
    review_raw_yaml: str | None  # output brut du Reviewer si retrouvable
    reviewer_episode_path: str | None
    qg_verdict: str | None = None
    qg_rationale: str | None = None


def explain_mission_verdict(
    memory: FileMemory, mission_id: str
) -> MissionVerdictExplanation | None:
    """Recharge le summary + épisode du Reviewer pour expliquer le verdict.

    Retourne None si le summary n'existe pas. Si on ne trouve pas l'épisode
    Reviewer, on retourne quand même l'explication avec `review_raw_yaml=None`.
    """
    summary = memory.get_mission_summary(mission_id)
    if summary is None:
        return None

    meta = summary.metadata
    explanation = MissionVerdictExplanation(
        mission_id=str(mission_id),
        title=str(meta.get("title", "")),
        final_verdict=str(meta.get("final_verdict", "")),
        quality_score=meta.get("quality_score")
        if isinstance(meta.get("quality_score"), (int, float))
        else None,
        review_summary=str(meta.get("review_summary", "") or ""),
        review_raw_yaml=None,
        reviewer_episode_path=None,
        qg_verdict=meta.get("qg_verdict"),
        qg_rationale=meta.get("qg_rationale"),
    )

    # Cherche l'épisode du Reviewer dans data/memory/episodes/<mission_id>/
    reviewer_episode = _find_reviewer_episode(memory, mission_id)
    if reviewer_episode is not None:
        explanation.reviewer_episode_path = str(reviewer_episode[0])
        explanation.review_raw_yaml = reviewer_episode[1].body
        # Si review_summary vide dans le summary, tenter de le tirer de l'épisode
        if not explanation.review_summary:
            explanation.review_summary = str(
                reviewer_episode[1].metadata.get("summary", "") or reviewer_episode[1].body[:500]
            )

    return explanation


def _find_reviewer_episode(memory: FileMemory, mission_id: str):
    """Retourne (path, record) du dernier épisode du code_reviewer pour cette
    mission, ou None si introuvable."""
    candidates = []
    for path in memory.list_episodes(mission_id):
        try:
            record = memory.read_episode(path)
        except OSError:
            continue
        if str(record.metadata.get("agent", "")) == "code_reviewer":
            candidates.append((path, record))
    if not candidates:
        return None
    # Le plus récent (les paths sont horodatés)
    candidates.sort(key=lambda c: str(c[0]), reverse=True)
    return candidates[0]
