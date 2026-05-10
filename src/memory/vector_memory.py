"""VectorMemory — mémoire sémantique sur Chroma (Phase 2).

Vient compléter FileMemory : chaque épisode est aussi indexé dans une collection
Chroma avec ses métadonnées (agent, mission, score, coût…). Les agents peuvent
ensuite chercher des précédents similaires à leur tâche courante via similarité
cosine sur les embeddings.

Choix techniques :
- PersistentClient : Chroma tourne in-process, pas besoin de container Docker en Phase 2.
- DefaultEmbeddingFunction : modèle ONNX léger embarqué dans chromadb (~30 MB).
- Collection unique "agent_episodes" partagée par tous les agents (filtre par `where`).
- Pas de delete : on garde tout en append-only (cf. principe d'auditabilité).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from pydantic import BaseModel


class EpisodeMatch(BaseModel):
    episode_id: str
    document: str
    metadata: dict[str, Any]
    distance: float  # cosine distance — plus c'est petit, plus c'est proche


class VectorMemory:
    """Wrapper Chroma pour la mémoire sémantique des épisodes."""

    DEFAULT_COLLECTION = "agent_episodes"

    def __init__(
        self,
        persist_dir: Path,
        collection_name: str = DEFAULT_COLLECTION,
    ) -> None:
        persist_dir.mkdir(parents=True, exist_ok=True)
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_episode(
        self,
        episode_id: str,
        document: str,
        metadata: dict[str, Any],
    ) -> None:
        """Indexe un épisode. Les métadonnées doivent être scalaires (Chroma ne stocke pas d'objets)."""
        flat_meta = self._flatten_metadata(metadata)
        # upsert pour rester idempotent si on rejoue le même épisode
        self._collection.upsert(
            ids=[episode_id],
            documents=[document],
            metadatas=[flat_meta],
        )

    def search(
        self,
        query: str,
        n_results: int = 3,
        where: dict[str, Any] | None = None,
        max_distance: float | None = None,
    ) -> list[EpisodeMatch]:
        """Cherche les épisodes les plus proches sémantiquement.

        - `where` : filtre Chroma (ex. `{"agent": "software_architect", "success": True}`)
        - `max_distance` : si fourni, ignore les résultats au-delà de ce seuil de distance
        """
        if self.count() == 0:
            return []

        # Chroma plafonne n_results à la taille de la collection
        n = min(n_results, self.count())
        result = self._collection.query(
            query_texts=[query],
            n_results=n,
            where=where,
        )

        matches: list[EpisodeMatch] = []
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        for ep_id, doc, meta, dist in zip(ids, documents, metadatas, distances, strict=False):
            if max_distance is not None and dist > max_distance:
                continue
            matches.append(
                EpisodeMatch(
                    episode_id=ep_id,
                    document=doc or "",
                    metadata=dict(meta or {}),
                    distance=float(dist),
                )
            )
        return matches

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        """Vide la collection. À utiliser uniquement en tests."""
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _flatten_metadata(meta: dict[str, Any]) -> dict[str, str | int | float | bool]:
        """Chroma n'accepte que des scalaires en metadata. Convertit les autres types en str."""
        flat: dict[str, str | int | float | bool] = {}
        for k, v in meta.items():
            if v is None:
                continue
            if isinstance(v, (str, int, float, bool)):
                flat[k] = v
            else:
                flat[k] = str(v)
        return flat
