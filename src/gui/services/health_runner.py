"""health_runner — appel direct du health_check sans subprocess (v0.5.1).

Background : subprocess.run(capture_output=True) + rich.Console + Windows =
piège. Le `sys.stdout.reconfigure()` en haut de health_check.py + le pipe
non-TTY de subprocess font que rich n'émet rien (silencieux), stdout est
None ou vide, et la page Health Streamlit affichait un warning au lieu
du résultat (cf. fix gracieux 77e383b).

Vraie solution (v0.5.1) : importer `scripts.health_check.app` (Typer app)
et l'invoquer via `typer.testing.CliRunner` qui capture la sortie via
StringIO en mémoire — pas de pipe OS, pas de problème d'encoding, plus
rapide (pas de fork subprocess), et reproductible cross-platform.

Le code de health_check.py est inchangé fonctionnellement ; seul le
guard `isatty()` autour du `sys.stdout.reconfigure()` a été ajouté pour
éviter le crash silencieux quand stdout est un StringIO.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))


@dataclass
class HealthResult:
    """Résultat d'un appel à health_check."""

    exit_code: int
    stdout: str
    duration_seconds: float


def run_health(quick: bool = True) -> HealthResult:
    """Lance le health_check via CliRunner et retourne (exit_code, stdout, duration).

    Pas de subprocess — import direct du module + invocation Typer en mémoire.
    Robuste sur Windows (cf. docstring du module).
    """
    # Import différé pour éviter de charger toute la dépendance chain
    # de health_check au top-level de la GUI (réduction du temps de boot).
    import health_check
    from typer.testing import CliRunner

    runner = CliRunner()
    args = ["--quick"] if quick else []
    started = time.perf_counter()
    result = runner.invoke(health_check.app, args, catch_exceptions=False)
    duration = time.perf_counter() - started

    # CliRunner.result.stdout contient stdout + stderr fusionnés (depuis
    # typer ≥ 0.14, le paramètre `mix_stderr` a été retiré et le fusion
    # est l'unique comportement). C'est ce qu'on veut pour la GUI :
    # tout dans un seul code block lisible.
    stdout = result.stdout or ""

    return HealthResult(
        exit_code=result.exit_code,
        stdout=stdout,
        duration_seconds=duration,
    )
