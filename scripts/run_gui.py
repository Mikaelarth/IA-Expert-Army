"""run_gui — entry point Streamlit pour l'interface GUI (ADR-026).

Usage :
    uv run python scripts/run_gui.py
    just gui

Configuration par défaut :
  - Port 8501
  - Bind localhost only (--server.address=127.0.0.1) pour usage perso sécurisé
  - Pas d'auth (Phase 2 si déploiement multi-utilisateur)

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


def main() -> int:
    if not APP_ENTRY.exists():
        print(f"App entry not found: {APP_ENTRY}", file=sys.stderr)
        return 2

    cmd: list[str] = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP_ENTRY),
        "--server.address",
        "127.0.0.1",
        "--server.port",
        "8501",
        "--browser.gatherUsageStats",
        "false",
    ]
    # Forwarde l'env et exécute Streamlit jusqu'à Ctrl+C
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.call(cmd, cwd=str(_ROOT), env=env)  # noqa: S603 — args contrôlés


if __name__ == "__main__":
    raise SystemExit(main())
