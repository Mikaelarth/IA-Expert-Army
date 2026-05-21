"""Page Health — diagnostic live du système (Ollama, Docker, mémoire, etc.).

Invoque `scripts/health_check.py` directement via `typer.testing.CliRunner`
(pas subprocess) — capture en mémoire StringIO, robuste sur Windows, plus
rapide. Cf. `src/gui/services/health_runner.py` pour le rationale technique
(résolution v0.5.1 du bug Health subprocess.stdout=None observé v0.5.0).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from src.gui.services.health_runner import run_health  # noqa: E402

st.set_page_config(page_title="Health — IA-Expert-Army", page_icon="🏥", layout="wide")
st.title("🏥 Health check")
st.caption(
    "Diagnostic en direct via `scripts/health_check.py`. Vérifie Settings, "
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


if run_now:
    quick = not include_docker
    label = (
        "Lancement health check (Docker + Ollama inclus)…"
        if not quick
        else "Lancement health check (quick)…"
    )
    with st.spinner(label):
        try:
            result = run_health(quick=quick)
        except Exception as exc:
            st.error(f"Crash health_check : `{type(exc).__name__}: {exc}`")
            st.exception(exc)
            st.stop()

    color = "green" if result.exit_code == 0 else "red"
    st.markdown(
        f"### Exit code : :{color}[**{result.exit_code}**] · durée {result.duration_seconds:.1f} s"
    )

    stdout = result.stdout
    if not stdout.strip():
        st.warning(
            "Sortie vide. C'est inattendu avec le runner CliRunner — vérifier que "
            "`scripts/health_check.py` n'a pas été modifié pour rediriger vers un "
            "autre flux."
        )
        st.stop()

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
            "FAIL",
            n_fail,
            delta=None if n_fail == 0 else f"-{n_fail}",
            delta_color="inverse",
        )
        mc4.metric("SKIP", n_skip)

    st.subheader("Sortie complète")
    st.code(stdout, language="text")
else:
    st.info(
        "Clique sur **▶ Lancer health check** pour démarrer. Le mode `quick` (par défaut) "
        "saute Docker + Ollama et tourne en 2-3 s. Le mode complet inclut les checks réseau "
        "et peut prendre 5-15 s."
    )
