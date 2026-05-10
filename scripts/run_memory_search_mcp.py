"""run_memory_search_mcp — lance le serveur MCP memory_search en mode stdio.

Usage :
    uv run python scripts/run_memory_search_mcp.py

Ce script est typiquement invoqué par un client MCP (Claude Desktop,
Anthropic Workbench, Cursor, etc.) qui spawn le process en subprocess
et communique via stdin/stdout.

Configuration client exemple (Claude Desktop) :
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

import asyncio
import sys
from pathlib import Path

# IMPORTANT : pas de `sys.stdout.reconfigure(encoding="utf-8")` ici car le serveur
# MCP communique via stdio binaire JSON-RPC. Toute écriture stdout pollue le canal.
# Les logs structlog sortent sur stderr (où le client MCP les ignore).

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.mcp_servers.memory_search import serve


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
