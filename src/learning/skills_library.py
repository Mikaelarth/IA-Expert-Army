"""SkillsLibrary — gère les « recettes » réutilisables apprises par l'équipe.

Une skill est un fichier markdown dans `skills/<agent>/<id>.md` avec frontmatter YAML.
Format aligné avec `skills/README.md` et avec la sortie du Skill Extractor (Phase 5).

L'API est volontairement minimaliste pour la Phase 5 MVP :
- Liste des skills d'un agent (les N plus récentes)
- Écriture d'une nouvelle skill (versionne dans Git via le commit habituel)
- Compactage textuel pour injection dans le prompt d'un agent

Phase 5 complète (plus tard) : indexation Chroma sémantique, A/B testing entre
versions de skills, expiration automatique des skills sous-performantes.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.memory.file_memory import MemoryRecord


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
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

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
        return Skill(
            skill_id=skill_id,
            agent=agent,
            title=title,
            summary=meta.get("summary", ""),
            body=body,
            metadata=meta,
            path=path,
        )

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
            body = s.body if len(s.body) <= max_chars_per_skill else s.body[:max_chars_per_skill].rstrip() + "\n…[tronqué]"
            parts.append(f"## Skill {i} : {s.title}")
            if s.summary:
                parts.append(f"*{s.summary.strip()}*")
            parts.append("")
            parts.append(body)
            parts.append("")
        return "\n".join(parts)
