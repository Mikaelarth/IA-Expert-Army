"""SkillsLibrary — gère les « recettes » réutilisables apprises par l'équipe.

Une skill est un fichier markdown dans `skills/<agent>/<id>.md` avec frontmatter YAML.
Format aligné avec `skills/README.md` et avec la sortie du Skill Extractor (Phase 5).

API :
- write_skill / list_skills (récence) / count
- render_for_prompt : compactage textuel pour injection dans un user_message
- search_skills : recherche sémantique si une VectorMemory est branchée,
  sinon fallback sur les N plus récentes

Quand un VectorMemory dédié (typiquement une collection séparée "agent_skills")
est passé au constructeur, chaque write_skill l'indexe automatiquement.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.core.logging import get_logger
from src.memory.file_memory import MemoryRecord
from src.memory.vector_memory import VectorMemory

_log = get_logger("skills_library")


class Skill(BaseModel):
    skill_id: str
    agent: str
    title: str
    summary: str
    body: str
    metadata: dict[str, Any]
    path: Path

    model_config = {"arbitrary_types_allowed": True}


class SkillsLibrary:
    def __init__(self, root: Path, vector_memory: VectorMemory | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.vector_memory = vector_memory

    def agent_dir(self, agent: str) -> Path:
        d = self.root / agent
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_skill(
        self,
        agent: str,
        title: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> Skill:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40] or "skill"
        skill_id = f"{ts}_{slug}"
        meta = dict(metadata or {})
        meta.update(
            {
                "skill_id": skill_id,
                "agent": agent,
                "title": title,
                "created_at": meta.get("created_at") or datetime.now(UTC).isoformat(),
            }
        )
        record = MemoryRecord(metadata=meta, body=body.strip() + "\n")
        path = self.agent_dir(agent) / f"{skill_id}.md"
        path.write_text(record.to_markdown(), encoding="utf-8")
        skill = Skill(
            skill_id=skill_id,
            agent=agent,
            title=title,
            summary=meta.get("summary", ""),
            body=body,
            metadata=meta,
            path=path,
        )
        self._index_in_vector(skill)
        return skill

    def _index_in_vector(self, skill: Skill) -> None:
        """Indexe la skill dans la VectorMemory associée (si fournie)."""
        if self.vector_memory is None:
            return
        try:
            document = f"Skill: {skill.title}\nRésumé: {skill.summary}\n\n{skill.body[:2000]}"
            self.vector_memory.add_episode(
                episode_id=f"skill_{skill.skill_id}",
                document=document,
                metadata={
                    "agent": skill.agent,
                    "title": skill.title,
                    "skill_id": skill.skill_id,
                    "summary": skill.summary,
                },
            )
        except Exception as exc:
            _log.warning("skill.index.failed", skill=skill.skill_id, error=str(exc))

    def list_skills(self, agent: str, limit: int | None = None) -> list[Skill]:
        d = self.agent_dir(agent)
        files = sorted(d.glob("*.md"), reverse=True)  # plus récents d'abord
        if limit is not None:
            files = files[:limit]
        skills: list[Skill] = []
        for f in files:
            try:
                record = MemoryRecord.from_markdown(f.read_text(encoding="utf-8"))
            except OSError:
                continue
            meta = record.metadata
            skills.append(
                Skill(
                    skill_id=meta.get("skill_id", f.stem),
                    agent=meta.get("agent", agent),
                    title=meta.get("title", f.stem),
                    summary=str(meta.get("summary", "")),
                    body=record.body,
                    metadata=meta,
                    path=f,
                )
            )
        return skills

    def count(self, agent: str | None = None) -> int:
        if agent is None:
            return sum(len(list(d.glob("*.md"))) for d in self.root.iterdir() if d.is_dir())
        return len(list(self.agent_dir(agent).glob("*.md")))

    def get_skill_by_id(self, agent: str, skill_id: str) -> Skill | None:
        path = self.agent_dir(agent) / f"{skill_id}.md"
        if not path.exists():
            return None
        record = MemoryRecord.from_markdown(path.read_text(encoding="utf-8"))
        meta = record.metadata
        return Skill(
            skill_id=meta.get("skill_id", skill_id),
            agent=meta.get("agent", agent),
            title=meta.get("title", skill_id),
            summary=str(meta.get("summary", "")),
            body=record.body,
            metadata=meta,
            path=path,
        )

    def search_skills(
        self,
        agent: str,
        query: str | None = None,
        n_results: int = 2,
        max_distance: float = 1.0,
    ) -> list[Skill]:
        """Cherche les skills les plus pertinentes pour un agent.

        - Si une VectorMemory est branchée et qu'une `query` est fournie : recherche
          sémantique (skills triées par pertinence).
        - Sinon : fallback sur les N plus récentes (list_skills).
        """
        if self.vector_memory is None or not query or self.vector_memory.count() == 0:
            return self.list_skills(agent, limit=n_results)

        try:
            matches = self.vector_memory.search(
                query=query,
                n_results=n_results,
                where={"agent": agent},
                max_distance=max_distance,
            )
        except Exception as exc:
            _log.warning("skills.semantic_search.failed", error=str(exc))
            return self.list_skills(agent, limit=n_results)

        skills: list[Skill] = []
        for match in matches:
            skill_id = match.metadata.get("skill_id")
            if not skill_id:
                continue
            skill = self.get_skill_by_id(agent, str(skill_id))
            if skill is not None:
                skills.append(skill)
        # Si la recherche sémantique ne retourne rien (skills non encore indexées),
        # fallback sur la récence pour ne pas pénaliser.
        if not skills:
            return self.list_skills(agent, limit=n_results)
        return skills

    def reindex_existing(self) -> int:
        """Backfill : indexe dans la VectorMemory toutes les skills déjà sur disque.
        Retourne le nombre de skills indexées. No-op sans VectorMemory.
        """
        if self.vector_memory is None:
            return 0
        count = 0
        for agent_dir in self.root.iterdir():
            if not agent_dir.is_dir():
                continue
            for skill in self.list_skills(agent_dir.name):
                self._index_in_vector(skill)
                count += 1
        return count

    @staticmethod
    def render_for_prompt(skills: list[Skill], max_chars_per_skill: int = 800) -> str:
        """Compose un bloc Markdown court à injecter dans un user_message."""
        if not skills:
            return ""
        parts = [
            "# Skills apprises par ton rôle (extraites de tes succès passés)",
            "",
            "Ces recettes ont été synthétisées à partir de tes meilleures missions. "
            "Applique-les par défaut, dévie seulement si la tâche actuelle l'exige.",
            "",
        ]
        for i, s in enumerate(skills, 1):
            body = (
                s.body
                if len(s.body) <= max_chars_per_skill
                else s.body[:max_chars_per_skill].rstrip() + "\n…[tronqué]"
            )
            parts.append(f"## Skill {i} : {s.title}")
            if s.summary:
                parts.append(f"*{s.summary.strip()}*")
            parts.append("")
            parts.append(body)
            parts.append("")
        return "\n".join(parts)
