"""memory_search — serveur MCP qui expose la mémoire d'IA-Expert-Army.

Permet à un LLM tiers (Anthropic Workbench, Claude Desktop, Cursor, …) de
chercher dans nos épisodes et nos skills sans qu'on ait à embarquer tout
notre code Python dans son environnement.

# audit: ignore FILE_TOO_LONG -- 509 lignes acceptées : 6 handlers MCP +
# définition complète des inputSchemas inline (séparation par fichier
# augmenterait la fragmentation sans gain. Split prévu si on dépasse 700 ou
# si on rajoute > 8 outils MCP).

6 tools exposés :
  - search_episodes(query, agent=None, n=3) : recherche sémantique dans la
    VectorMemory des épisodes (collection "agent_episodes")
  - search_skills(agent, query=None, n=2) : recherche sémantique dans la
    SkillsLibrary (collection "agent_skills"), fallback récence si pas de
    query
  - list_recent_missions(limit=10, guild=None) : navigation chronologique
    dans les missions terminées (sans recherche), filtrable par guilde
  - get_mission_summary(mission_id) : récupère le récap complet d'une
    mission (frontmatter + corps markdown) à partir de son UUID
  - list_recent_meta_missions(limit=10) : navigation chronologique dans
    les meta-missions cross-guildes (Phase 7), avec leurs sub_mission_ids
  - get_meta_mission_summary(meta_mission_id) : zoom sur une meta-mission
    (rationale + résultats des sous-missions + cumul coût/durée)

Le serveur communique via stdio (standard MCP). Lancement :
    uv run python scripts/run_memory_search_mcp.py

Configuration côté client (Claude Desktop par ex) :
    {
      "mcpServers": {
        "ia-expert-army-memory": {
          "command": "uv",
          "args": ["run", "python",
                   "D:/PROJETS/IA-Expert-Army/scripts/run_memory_search_mcp.py"]
        }
      }
    }
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.core.config import get_settings
from src.core.logging import get_logger
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory

log = get_logger("mcp.memory_search")


def _build_server(
    vector_episodes: VectorMemory | None = None,
    skills_library: SkillsLibrary | None = None,
    file_memory: FileMemory | None = None,
) -> Server:
    """Crée et configure un serveur MCP avec les 4 tools mémoire.

    Les dépendances sont injectables pour faciliter les tests unit.
    """
    settings = get_settings()

    if vector_episodes is None:
        vector_episodes = VectorMemory(
            persist_dir=settings.chroma_persist_dir,
            collection_name="agent_episodes",
        )
    if skills_library is None:
        vector_skills = VectorMemory(
            persist_dir=settings.chroma_persist_dir,
            collection_name="agent_skills",
        )
        skills_library = SkillsLibrary(
            settings.project_root / "skills", vector_memory=vector_skills
        )
    if file_memory is None:
        file_memory = FileMemory(settings.project_root / "data" / "memory")

    server: Server = Server("ia-expert-army-memory")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="search_episodes",
                description=(
                    "Cherche des épisodes (exécutions d'agents) sémantiquement "
                    "similaires à une requête. Filtre optionnel par agent. Retourne "
                    "un JSON avec id, agent, mission, distance, et un extrait du contenu."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Texte de recherche (ex. tâche similaire à résoudre)",
                        },
                        "agent": {
                            "type": "string",
                            "description": "Optionnel — filtre sur le nom d'agent (ex. 'software_architect')",
                        },
                        "n": {
                            "type": "integer",
                            "description": "Nombre de résultats (défaut 3, max 10)",
                            "default": 3,
                            "minimum": 1,
                            "maximum": 10,
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="search_skills",
                description=(
                    "Cherche les skills (recettes apprises) d'un agent donné, "
                    "optionnellement filtrées par pertinence sémantique à une "
                    "query. Sans query : retourne les N plus récentes."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agent": {
                            "type": "string",
                            "description": "Nom de l'agent (ex. 'tech_watch', 'project_manager')",
                        },
                        "query": {
                            "type": "string",
                            "description": "Optionnel — pertinence sémantique (sinon récence)",
                        },
                        "n": {
                            "type": "integer",
                            "description": "Nombre de skills (défaut 2, max 5)",
                            "default": 2,
                            "minimum": 1,
                            "maximum": 5,
                        },
                    },
                    "required": ["agent"],
                },
            ),
            Tool(
                name="list_recent_missions",
                description=(
                    "Liste les missions terminées par ordre chronologique inverse "
                    "(les plus récentes d'abord). Filtre optionnel par guilde. "
                    "Utile pour explorer ce que l'équipe a produit récemment sans "
                    "connaître a priori les sujets — complément de search_episodes "
                    "qui suppose une query."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Nombre max de missions retournées (défaut 10, max 50)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50,
                        },
                        "guild": {
                            "type": "string",
                            "description": "Optionnel — filtre sur la guilde ('engineering', 'research', 'creative', 'business')",
                        },
                    },
                    "required": [],
                },
            ),
            Tool(
                name="get_mission_summary",
                description=(
                    "Récupère le récap complet d'une mission donnée à partir de "
                    "son mission_id (UUID). Retourne le frontmatter (verdict, "
                    "score, coût, durée, …) ET le corps markdown (description, "
                    "résumé reviewer, livrables). Complémentaire à "
                    "list_recent_missions pour zoomer sur une mission précise."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "mission_id": {
                            "type": "string",
                            "description": "UUID de la mission (format complet 36 chars)",
                        },
                    },
                    "required": ["mission_id"],
                },
            ),
            Tool(
                name="list_recent_meta_missions",
                description=(
                    "Liste les meta-missions cross-guildes (Phase 7) par ordre "
                    "chronologique inverse. Une meta-mission décompose une "
                    "mission complexe en 2-4 sous-missions routées vers "
                    "différentes guildes. Retourne pour chacune : id, titre, "
                    "verdict global, score moyen, coût total cumulé, liste "
                    "des guildes traversées et IDs des sous-missions."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Nombre max retourné (défaut 10, max 50)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50,
                        },
                    },
                    "required": [],
                },
            ),
            Tool(
                name="get_meta_mission_summary",
                description=(
                    "Récupère le récap complet d'une meta-mission cross-guildes "
                    "à partir de son meta_mission_id. Retourne le frontmatter "
                    "(verdict global, score moyen, cumul coût/durée, liste des "
                    "sous-missions) ET le corps markdown (rationale de "
                    "décomposition, détail par sous-mission)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "meta_mission_id": {
                            "type": "string",
                            "description": "UUID de la meta-mission (format complet 36 chars)",
                        },
                    },
                    "required": ["meta_mission_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "search_episodes":
            return _handle_search_episodes(vector_episodes, arguments)
        if name == "search_skills":
            return _handle_search_skills(skills_library, arguments)
        if name == "list_recent_missions":
            return _handle_list_recent_missions(file_memory, arguments)
        if name == "get_mission_summary":
            return _handle_get_mission_summary(file_memory, arguments)
        if name == "list_recent_meta_missions":
            return _handle_list_recent_meta_missions(file_memory, arguments)
        if name == "get_meta_mission_summary":
            return _handle_get_meta_mission_summary(file_memory, arguments)
        return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]

    return server


def _handle_search_episodes(
    vector_episodes: VectorMemory, arguments: dict[str, Any]
) -> list[TextContent]:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return [TextContent(type="text", text=json.dumps({"error": "query is required"}))]
    n = int(arguments.get("n", 3))
    n = max(1, min(n, 10))
    agent = arguments.get("agent")

    where: dict[str, Any] | None = None
    if agent:
        where = {"agent": str(agent)}

    try:
        matches = vector_episodes.search(query=query, n_results=n, where=where)
    except Exception as exc:
        log.warning("mcp.search_episodes.failed", error=str(exc))
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    payload = {
        "query": query,
        "agent_filter": agent,
        "n_results": len(matches),
        "results": [
            {
                "episode_id": m.episode_id,
                "agent": m.metadata.get("agent"),
                "mission_id": m.metadata.get("mission_id"),
                "mission_title": m.metadata.get("mission_title"),
                "quality_score": m.metadata.get("quality_score"),
                "distance": round(m.distance, 4),
                "similarity": round(1 - m.distance, 4),
                "excerpt": (m.document or "")[:500],
            }
            for m in matches
        ],
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


def _handle_search_skills(
    skills_library: SkillsLibrary, arguments: dict[str, Any]
) -> list[TextContent]:
    agent = str(arguments.get("agent", "")).strip()
    if not agent:
        return [TextContent(type="text", text=json.dumps({"error": "agent is required"}))]
    n = int(arguments.get("n", 2))
    n = max(1, min(n, 5))
    query = arguments.get("query")
    query_str = str(query).strip() if query else None

    try:
        skills = skills_library.search_skills(agent=agent, query=query_str, n_results=n)
    except Exception as exc:
        log.warning("mcp.search_skills.failed", error=str(exc))
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    payload = {
        "agent": agent,
        "query": query_str,
        "n_results": len(skills),
        "results": [
            {
                "skill_id": s.skill_id,
                "title": s.title,
                "summary": s.summary,
                "tags": s.metadata.get("tags", []),
                "sources_avg_score": s.metadata.get("sources_avg_score"),
                "body_excerpt": s.body[:1000],
            }
            for s in skills
        ],
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


def _handle_list_recent_missions(
    file_memory: FileMemory, arguments: dict[str, Any]
) -> list[TextContent]:
    limit = int(arguments.get("limit", 10))
    limit = max(1, min(limit, 50))
    guild_filter = arguments.get("guild")
    guild_filter = str(guild_filter).strip().lower() if guild_filter else None

    try:
        # list_missions trie par nom (UUID), donc pour chronologique on lit le
        # frontmatter et on trie par started_at — on accepte le coût car le
        # nombre de missions reste petit (< quelques milliers en pratique).
        paths = file_memory.list_missions()
        records = []
        for path in paths:
            try:
                rec = file_memory.get_mission_summary(path.stem)
            except Exception as exc:
                # On continue sur erreur de parsing isolée (frontmatter corrompu) mais on
                # le logue pour ne pas le perdre silencieusement (audit S112).
                log.warning("mcp.list_recent_missions.skip", path=str(path), error=str(exc))
                continue
            if rec is None:
                continue
            meta = rec.metadata
            if guild_filter and str(meta.get("guild", "")).lower() != guild_filter:
                continue
            records.append((meta.get("started_at", ""), meta, path))
        records.sort(key=lambda r: r[0], reverse=True)
        records = records[:limit]
    except Exception as exc:
        log.warning("mcp.list_recent_missions.failed", error=str(exc))
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    payload = {
        "limit": limit,
        "guild_filter": guild_filter,
        "n_results": len(records),
        "results": [
            {
                "mission_id": str(meta.get("mission_id", path.stem)),
                "title": meta.get("title"),
                "guild": meta.get("guild"),
                "started_at": meta.get("started_at"),
                "ended_at": meta.get("ended_at"),
                "success": meta.get("success"),
                "final_verdict": meta.get("final_verdict"),
                "quality_score": meta.get("quality_score"),
                "total_cost_usd": meta.get("total_cost_usd"),
                "total_duration_seconds": meta.get("total_duration_seconds"),
            }
            for _started, meta, path in records
        ],
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


def _handle_get_mission_summary(
    file_memory: FileMemory, arguments: dict[str, Any]
) -> list[TextContent]:
    mission_id = str(arguments.get("mission_id", "")).strip()
    if not mission_id:
        return [TextContent(type="text", text=json.dumps({"error": "mission_id is required"}))]

    try:
        record = file_memory.get_mission_summary(mission_id)
    except Exception as exc:
        log.warning("mcp.get_mission_summary.failed", error=str(exc))
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    if record is None:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {"error": f"mission not found: {mission_id}", "mission_id": mission_id}
                ),
            )
        ]

    payload = {
        "mission_id": mission_id,
        "metadata": record.metadata,
        "body": record.body,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


def _handle_list_recent_meta_missions(
    file_memory: FileMemory, arguments: dict[str, Any]
) -> list[TextContent]:
    limit = int(arguments.get("limit", 10))
    limit = max(1, min(limit, 50))

    try:
        paths = file_memory.list_meta_missions()
        records = []
        for path in paths:
            try:
                rec = file_memory.get_meta_mission_summary(path.stem)
            except Exception as exc:
                # Idem que list_recent_missions : on continue mais on logue.
                log.warning("mcp.list_recent_meta_missions.skip", path=str(path), error=str(exc))
                continue
            if rec is None:
                continue
            meta = rec.metadata
            records.append((meta.get("started_at", ""), meta, path))
        records.sort(key=lambda r: r[0], reverse=True)
        records = records[:limit]
    except Exception as exc:
        log.warning("mcp.list_recent_meta_missions.failed", error=str(exc))
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    payload = {
        "limit": limit,
        "n_results": len(records),
        "results": [
            {
                "meta_mission_id": str(meta.get("meta_mission_id", path.stem)),
                "title": meta.get("title"),
                "started_at": meta.get("started_at"),
                "ended_at": meta.get("ended_at"),
                "final_verdict": meta.get("final_verdict"),
                "overall_quality_score": meta.get("overall_quality_score"),
                "total_cost_usd": meta.get("total_cost_usd"),
                "total_duration_seconds": meta.get("total_duration_seconds"),
                "n_sub_missions": meta.get("n_sub_missions"),
                "guilds": meta.get("guilds"),
                "sub_mission_ids": meta.get("sub_mission_ids"),
            }
            for _started, meta, path in records
        ],
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


def _handle_get_meta_mission_summary(
    file_memory: FileMemory, arguments: dict[str, Any]
) -> list[TextContent]:
    meta_mission_id = str(arguments.get("meta_mission_id", "")).strip()
    if not meta_mission_id:
        return [TextContent(type="text", text=json.dumps({"error": "meta_mission_id is required"}))]

    try:
        record = file_memory.get_meta_mission_summary(meta_mission_id)
    except Exception as exc:
        log.warning("mcp.get_meta_mission_summary.failed", error=str(exc))
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    if record is None:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": f"meta-mission not found: {meta_mission_id}",
                        "meta_mission_id": meta_mission_id,
                    }
                ),
            )
        ]

    payload = {
        "meta_mission_id": meta_mission_id,
        "metadata": record.metadata,
        "body": record.body,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


async def serve() -> None:
    """Point d'entrée stdio. Appelé par scripts/run_memory_search_mcp.py."""
    server = _build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
