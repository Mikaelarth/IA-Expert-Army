"""Page Health — diagnostic live du système (Ollama, Docker, mémoire, etc.).

Lance `scripts/health_check.py --quick` en subprocess et parse la sortie
en table Streamlit. Bouton de refresh pour relancer à la demande.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Health — IA-Expert-Army", page_icon="🏥", layout="wide")
st.title("🏥 Health check")
st.caption(
    "Diagnostic en direct via `scripts/health_check.py --quick`. Vérifie Settings, "
    "FileMemory, Chroma, SkillsLibrary, PatternMiner whitelist, garde-fous, etc."
)

col1, col2 = st.columns([3, 1])
with col1:
    include_docker = st.checkbox(
        "Inclure les checks Docker + Ollama daemon (mode complet)",
        value=False,
        help="Mode `--quick` (défaut) skip Docker + Ollama. Décocher pour lancer le full check.",
    )
with col2:
    run_now = st.button("▶ Lancer health check", type="primary", use_container_width=True)


def _run_health(quick: bool) -> tuple[int, str, float]:
    """Lance health_check.py et capture stdout. Retourne (exit_code, stdout, duration_s)."""
    cmd: list[str] = [
        sys.executable,
        str(_ROOT / "scripts" / "health_check.py"),
    ]
    if quick:
        cmd.append("--quick")
    started = time.perf_counter()
    proc = subprocess.run(  # noqa: S603 — args contrôlés (sys.executable + script du repo)
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(_ROOT),
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    return proc.returncode, proc.stdout, time.perf_counter() - started


if run_now:
    quick = not include_docker
    label = (
        "Lancement health check (Docker inclus)…"
        if not quick
        else "Lancement health check (quick)…"
    )
    with st.spinner(label):
        try:
            exit_code, stdout, duration = _run_health(quick)
        except subprocess.TimeoutExpired:
            st.error(
                "Timeout (>120 s) — health check trop lent, vérifier Docker/Ollama manuellement."
            )
            st.stop()
        except Exception as exc:
            st.error(f"Crash : `{type(exc).__name__}: {exc}`")
            st.stop()

    color = "green" if exit_code == 0 else "red"
    st.markdown(f"### Exit code : :{color}[**{exit_code}**] · durée {duration:.1f} s")

    # Extrait la ligne de résumé "N OK · M WARN · K FAIL · L SKIP"
    summary_match = re.search(
        r"(\d+)\s*OK[^\d]*(\d+)\s*WARN[^\d]*(\d+)\s*FAIL[^\d]*(\d+)\s*SKIP", stdout
    )
    if summary_match:
        n_ok, n_warn, n_fail, n_skip = (int(x) for x in summary_match.groups())
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("OK", n_ok)
        mc2.metric("WARN", n_warn)
        mc3.metric(
            "FAIL", n_fail, delta=None if n_fail == 0 else f"-{n_fail}", delta_color="inverse"
        )
        mc4.metric("SKIP", n_skip)

    st.subheader("Sortie complète")
    st.code(stdout, language="text")
else:
    st.info(
        "Clique sur **▶ Lancer health check** pour démarrer. Le mode `quick` (par défaut) "
        "saute Docker + Ollama et tourne en 3-5 s. Le mode complet inclut les checks réseau "
        "et peut prendre 10-30 s."
    )
