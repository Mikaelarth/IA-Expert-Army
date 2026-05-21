"""memory_browser — wrappers FileMemory pour la GUI.

Fournit des fonctions de haut niveau pour lister/lire les artefacts archivés
(missions, episodes, skills) avec parsing du frontmatter et tri par date.
Cachable via Streamlit (`st.cache_data`) côté caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from src.core.config import get_settings


@dataclass
class MissionSummary:
    """Vue compacte d'une mission archivée pour la liste GUI."""

    mission_id: str
    title: str
    guild: str
    final_verdict: str
    quality_score: float | None
    total_cost_usd: float
    total_duration_seconds: float
    started_at: str
    ended_at: str
    files_produced_count: int
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    body: str = ""


@dataclass
class SkillSummary:
    """Vue compacte d'une skill auto-extraite."""

    skill_id: str
    agent: str
    title: str
    summary: str
    created_at: str
    sources_count: int
    sources_avg_score: float
    path: Path


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extrait le frontmatter YAML + corps markdown."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    body = parts[2].lstrip("\n")
    return meta, body


def list_missions(missions_dir: Path | None = None) -> list[MissionSummary]:
    """Retourne la liste des missions, plus récente d'abord."""
    if missions_dir is None:
        missions_dir = get_settings().project_root / "data" / "memory" / "missions"
    if not missions_dir.exists():
        return []

    summaries: list[MissionSummary] = []
    for path in sorted(missions_dir.glob("*.md"), reverse=True):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = _parse_frontmatter(text)
        # Inférence guilde depuis l'archi : engineering = défaut, sinon depuis metadata
        guild = str(meta.get("guild") or _infer_guild_from_body(body)).lower() or "engineering"
        summaries.append(
            MissionSummary(
                mission_id=str(meta.get("mission_id") or path.stem),
                title=str(meta.get("title") or path.stem),
                guild=guild,
                final_verdict=str(meta.get("final_verdict") or "?"),
                quality_score=meta.get("quality_score")
                if isinstance(meta.get("quality_score"), (int, float))
                else None,
                total_cost_usd=float(meta.get("total_cost_usd") or 0.0),
                total_duration_seconds=float(meta.get("total_duration_seconds") or 0.0),
                started_at=str(meta.get("started_at") or ""),
                ended_at=str(meta.get("ended_at") or ""),
                files_produced_count=int(meta.get("files_produced_count") or 0),
                raw_metadata=meta,
                body=body,
            )
        )
    return summaries


def _infer_guild_from_body(body: str) -> str:
    """Fallback : cherche 'engineering|research|creative|business' dans le résumé."""
    lower = body.lower()[:2000]
    for guild in ("engineering", "research", "creative", "business"):
        if f"guilde : {guild}" in lower or f"guild: {guild}" in lower:
            return guild
    return ""


def list_skills(skills_root: Path | None = None) -> dict[str, list[SkillSummary]]:
    """Retourne les skills groupées par agent, plus récente d'abord par agent."""
    if skills_root is None:
        skills_root = get_settings().project_root / "skills"
    if not skills_root.exists():
        return {}

    out: dict[str, list[SkillSummary]] = {}
    for agent_dir in sorted(skills_root.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent = agent_dir.name
        skills: list[SkillSummary] = []
        for path in sorted(agent_dir.glob("*.md"), reverse=True):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            meta, _body = _parse_frontmatter(text)
            skills.append(
                SkillSummary(
                    skill_id=str(meta.get("skill_id") or path.stem),
                    agent=agent,
                    title=str(meta.get("title") or path.stem),
                    summary=str(meta.get("summary") or "").strip(),
                    created_at=str(meta.get("created_at") or ""),
                    sources_count=int(
                        meta.get("extracted_from") or len(meta.get("sources", []) or [])
                    ),
                    sources_avg_score=float(meta.get("sources_avg_score") or 0.0),
                    path=path,
                )
            )
        if skills:
            out[agent] = skills
    return out


def read_mission_body(mission_id: str, missions_dir: Path | None = None) -> str | None:
    """Lit le corps markdown d'une mission par UUID."""
    if missions_dir is None:
        missions_dir = get_settings().project_root / "data" / "memory" / "missions"
    path = missions_dir / f"{mission_id}.md"
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    _, body = _parse_frontmatter(text)
    return body


def read_skill_body(path: Path) -> str | None:
    """Lit le corps markdown d'une skill."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    _, body = _parse_frontmatter(text)
    return body


def stats(missions: list[MissionSummary]) -> dict[str, Any]:
    """Calcule des stats agrégées pour la page Historique."""
    if not missions:
        return {
            "total": 0,
            "approved": 0,
            "approval_rate": 0.0,
            "avg_score": None,
            "avg_duration_s": None,
            "by_guild": {},
            "by_verdict": {},
        }
    approved = [m for m in missions if m.final_verdict == "APPROVED"]
    scores = [m.quality_score for m in missions if m.quality_score is not None]
    durations = [m.total_duration_seconds for m in missions if m.total_duration_seconds > 0]
    by_guild: dict[str, int] = {}
    by_verdict: dict[str, int] = {}
    for m in missions:
        by_guild[m.guild] = by_guild.get(m.guild, 0) + 1
        by_verdict[m.final_verdict] = by_verdict.get(m.final_verdict, 0) + 1
    return {
        "total": len(missions),
        "approved": len(approved),
        "approval_rate": round(100 * len(approved) / len(missions), 1),
        "avg_score": round(sum(scores) / len(scores), 3) if scores else None,
        "avg_duration_s": round(sum(durations) / len(durations), 1) if durations else None,
        "by_guild": by_guild,
        "by_verdict": by_verdict,
    }


def fmt_duration(seconds: float) -> str:
    """Format humain : '21 min 12 s' ou '45 s'."""
    if seconds < 60:
        return f"{seconds:.0f} s"
    m, s = divmod(int(seconds), 60)
    return f"{m} min {s:02d} s"


def fmt_datetime(iso: str) -> str:
    """ISO → 'YYYY-MM-DD HH:MM' lisible."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso[:16]
