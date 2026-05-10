"""FileMemory — mémoire persistante simple sur disque, format Markdown + frontmatter YAML.

C'est l'équivalent Phase 1 de la mémoire 4-niveaux du plan d'architecture :
- working/   : mémoire de travail volatile (mission en cours)
- episodes/  : mémoire épisodique (un fichier par exécution d'agent)
- missions/  : récap des missions accomplies
- procedural/: skills (référencé via le dossier `skills/` à la racine du projet)

L'API privilégie la simplicité : open + read + write de fichiers texte.
On migrera vers SQLite + Chroma en Phase 2 sans changer cette interface publique.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from pydantic import BaseModel, Field


class MemoryRecord(BaseModel):
    """Un enregistrement mémoire = frontmatter (metadata) + corps (markdown)."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    body: str = ""

    def to_markdown(self) -> str:
        front = yaml.safe_dump(self.metadata, sort_keys=False, allow_unicode=True).strip()
        return f"---\n{front}\n---\n\n{self.body.strip()}\n"

    @classmethod
    def from_markdown(cls, text: str) -> MemoryRecord:
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
        if not match:
            return cls(metadata={}, body=text)
        meta = yaml.safe_load(match.group(1)) or {}
        return cls(metadata=meta, body=match.group(2).strip())


class FileMemory:
    """Mémoire fichier (Phase 1). Thread-unsafe par construction — un orchestrateur à la fois."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.episodes_dir = self.root / "episodes"
        self.missions_dir = self.root / "missions"
        self.working_dir = self.root / "working"
        for d in (self.episodes_dir, self.missions_dir, self.working_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ----- working memory (volatile) -----

    def set_working(self, key: str, record: MemoryRecord) -> Path:
        path = self.working_dir / f"{key}.md"
        path.write_text(record.to_markdown(), encoding="utf-8")
        return path

    def get_working(self, key: str) -> MemoryRecord | None:
        path = self.working_dir / f"{key}.md"
        if not path.exists():
            return None
        return MemoryRecord.from_markdown(path.read_text(encoding="utf-8"))

    def clear_working(self) -> int:
        count = 0
        for f in self.working_dir.glob("*.md"):
            f.unlink()
            count += 1
        return count

    # ----- episodic memory (permanent, append-only) -----

    def write_episode(
        self,
        mission_id: UUID | str,
        agent_name: str,
        record: MemoryRecord,
    ) -> Path:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "_", agent_name.lower()).strip("_")
        filename = f"{ts}_{str(mission_id)[:8]}_{slug}.md"
        path = self.episodes_dir / filename
        path.write_text(record.to_markdown(), encoding="utf-8")
        return path

    def list_episodes(self, mission_id: UUID | str | None = None) -> list[Path]:
        files = sorted(self.episodes_dir.glob("*.md"))
        if mission_id is None:
            return files
        prefix_id = str(mission_id)[:8]
        return [f for f in files if prefix_id in f.name]

    def read_episode(self, path: Path) -> MemoryRecord:
        return MemoryRecord.from_markdown(path.read_text(encoding="utf-8"))

    def update_episode_metadata(self, path: Path, **fields: Any) -> MemoryRecord:
        """Patch les champs de frontmatter d'un épisode existant et réécrit le fichier.

        Utilisé par le Workflow pour injecter quality_score + final_verdict sur
        chaque épisode après le verdict du Reviewer. La clé `None` n'est pas écrite
        (préserve les valeurs existantes pour les champs effacés explicitement).
        """
        record = self.read_episode(path)
        for key, value in fields.items():
            record.metadata[key] = value
        path.write_text(record.to_markdown(), encoding="utf-8")
        return record

    # ----- mission summaries (permanent) -----

    def write_mission_summary(self, mission_id: UUID | str, record: MemoryRecord) -> Path:
        path = self.missions_dir / f"{mission_id}.md"
        path.write_text(record.to_markdown(), encoding="utf-8")
        return path

    def get_mission_summary(self, mission_id: UUID | str) -> MemoryRecord | None:
        path = self.missions_dir / f"{mission_id}.md"
        if not path.exists():
            return None
        return MemoryRecord.from_markdown(path.read_text(encoding="utf-8"))

    def list_missions(self) -> list[Path]:
        return sorted(self.missions_dir.glob("*.md"))

    # ----- search (basique Phase 1, vector DB en Phase 2) -----

    def search_episodes(self, query: str, limit: int = 5) -> list[Path]:
        """Recherche naïve par occurrence de mots-clés. Sera remplacée par RAG en Phase 2."""
        terms = [t.lower() for t in query.split() if len(t) > 2]
        scored: list[tuple[int, Path]] = []
        for f in self.episodes_dir.glob("*.md"):
            try:
                content = f.read_text(encoding="utf-8").lower()
            except OSError:
                continue
            score = sum(content.count(t) for t in terms)
            if score > 0:
                scored.append((score, f))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:limit]]
