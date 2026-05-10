"""memory_search — serveur MCP qui expose la mémoire d'IA-Expert-Army.

Permet à un LLM tiers (Anthropic Workbench, Claude Desktop, Cursor, …) de
chercher dans nos épisodes et nos skills sans qu'on ait à embarquer tout
notre code Python dans son environnement.

2 tools exposés :
  - search_episodes(query, agent=None, n=3) : recherche sémantique dans la
    VectorMemory des épisodes (collection "agent_episodes")
  - search_skills(agent, query=None, n=2) : recherche sémantique dans la
    SkillsLibrary (collection "agent_skills"), fallback récence si pas de
    query

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
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.core.config import get_settings
from src.core.logging import get_logger
from src.learning.skills_library import SkillsLibrary
from src.memory.vector_memory import VectorMemory

log = get_logger("mcp.memory_search")


def _build_server(
    vector_episodes: VectorMemory | None = None,
    skills_library: SkillsLibrary | None = None,
) -> Server:
    """Crée et configure un serveur MCP avec les 2 tools mémoire.

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
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "search_episodes":
            return _handle_search_episodes(vector_episodes, arguments)
        if name == "search_skills":
            return _handle_search_skills(skills_library, arguments)
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
    except Exception as exc:  # noqa: BLE001
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
        skills = skills_library.search_skills(
            agent=agent, query=query_str, n_results=n
        )
    except Exception as exc:  # noqa: BLE001
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


async def serve() -> None:
    """Point d'entrée stdio. Appelé par scripts/run_memory_search_mcp.py."""
    server = _build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
