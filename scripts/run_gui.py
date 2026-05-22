"""run_gui — entry point Streamlit pour l'interface GUI (ADR-026).

Usage :
    uv run python scripts/run_gui.py                              # bind 127.0.0.1
    STREAMLIT_BIND_HOST=0.0.0.0 uv run python scripts/run_gui.py  # bind LAN
    STREAMLIT_BIND_PORT=8080 uv run python scripts/run_gui.py     # port custom
    just gui              # par défaut localhost
    just gui-lan          # 0.0.0.0 (LAN exposé) — cf. docs/deploy-lan.md

Configuration par défaut :
  - Port 8501 (override via `STREAMLIT_BIND_PORT`)
  - Bind 127.0.0.1 par défaut (override via `STREAMLIT_BIND_HOST`)
    * 127.0.0.1 : usage perso solo (sûr, non accessible LAN)
    * 0.0.0.0   : accessible depuis tout le LAN (ATTENTION : pas d'auth native,
                  ne JAMAIS exposer à internet sans reverse proxy + auth)
  - Pas d'auth (cf. ADR-026 — Phase 2 si déploiement multi-utilisateur)

Implémentation : invoque `streamlit run src/gui/app.py` en subprocess. Le
script entry-point DOIT être `src/gui/app.py` (et non ce wrapper) pour que
Streamlit trouve automatiquement les pages dans `src/gui/pages/` adjacent.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
APP_ENTRY = _ROOT / "src" / "gui" / "app.py"

# Valeurs par défaut : usage perso sûr (localhost only).
# Override via env vars pour exposition LAN / port custom / déploiement.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "8501"


def main() -> int:
    if not APP_ENTRY.exists():
        print(f"App entry not found: {APP_ENTRY}", file=sys.stderr)
        return 2

    bind_host = os.environ.get("STREAMLIT_BIND_HOST", DEFAULT_HOST)
    bind_port = os.environ.get("STREAMLIT_BIND_PORT", DEFAULT_PORT)

    # Avertissement explicite quand on bind sur 0.0.0.0 (rappel sécurité)
    if bind_host == "0.0.0.0":  # noqa: S104 — détection intentionnelle, pas binding hardcodé
        print(
            "⚠ STREAMLIT_BIND_HOST=0.0.0.0 — GUI exposée à tout le LAN.\n"
            "  Cf. docs/deploy-lan.md §Sécurité avant exposition réseau.\n",
            file=sys.stderr,
        )

    cmd: list[str] = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP_ENTRY),
        "--server.address",
        bind_host,
        "--server.port",
        bind_port,
        "--browser.gatherUsageStats",
        "false",
    ]
    # Forwarde l'env et exécute Streamlit jusqu'à Ctrl+C
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.call(cmd, cwd=str(_ROOT), env=env)  # noqa: S603 — args contrôlés


if __name__ == "__main__":
    raise SystemExit(main())
