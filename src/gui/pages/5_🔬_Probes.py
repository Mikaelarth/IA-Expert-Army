"""Page Probes — outils de mesure (probe_reviewer + probe_sandbox).

Affiche les probes déjà archivées dans `data/probes/` et permet de
relancer un probe (subprocess) si besoin. Les probes prennent 5-10 min
pour `probe_reviewer` (appel LLM réel) et < 5 s pour `probe_sandbox`.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Probes — IA-Expert-Army", page_icon="🔬", layout="wide")
st.title("🔬 Probes")
st.caption(
    "Outils de mesure isolés du non-déterminisme LLM. `probe_reviewer` mesure si le "
    "CodeReviewer détecte un bug donné. `probe_sandbox` valide que la chaîne Docker "
    "fonctionne sur du code réel."
)


PROBES_DIR = _ROOT / "data" / "probes"


def _list_probes() -> list[Path]:
    if not PROBES_DIR.exists():
        return []
    return sorted(
        (p for p in PROBES_DIR.glob("*.md") if p.is_file()),
        reverse=True,
    )


def _run_probe(script: str, label: str, timeout: int) -> tuple[int, str, float]:
    """Lance scripts/<script> en subprocess et capture stdout."""
    cmd: list[str] = [sys.executable, str(_ROOT / "scripts" / script)]
    started = time.perf_counter()
    proc = subprocess.run(  # noqa: S603 — args contrôlés (sys.executable + script du repo)
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(_ROOT),
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    return proc.returncode, proc.stdout, time.perf_counter() - started


tab1, tab2 = st.tabs(["🧪 Probe Reviewer", "🐳 Probe Sandbox"])

with tab1:
    st.subheader("Probe Reviewer — mesure résorption bug Session 2")
    st.markdown(
        "Soumet au `CodeReviewer` (modèle = `model_operational`) le code+test bugué "
        'Session 2 inchangé (test_slugify_multiple_punctuation qui attend `"-"` '
        "alors que `.strip('-')` produit `\"\"`). Mesure si le verdict est "
        "`NEEDS_CHANGES` (= bug détecté) ou `APPROVED` (= raté). "
        "Durée 5-10 min sur Qwen2.5-Coder 32B local."
    )
    if st.button("▶ Lancer probe Reviewer", type="primary", key="run_reviewer"):
        with st.spinner("Probe Reviewer en cours (5-10 min)…"):
            try:
                exit_code, stdout, duration = _run_probe(
                    "probe_reviewer.py", "Probe Reviewer", timeout=1800
                )
            except subprocess.TimeoutExpired:
                st.error("Timeout (>30 min). Vérifier Ollama daemon.")
                st.stop()
            except Exception as exc:
                st.error(f"Crash : `{type(exc).__name__}: {exc}`")
                st.stop()

        color = "green" if exit_code == 0 else "red"
        verdict = "Bug détecté ✅" if exit_code == 0 else "Bug NON détecté ❌"
        st.markdown(f"### Exit {exit_code} — :{color}[**{verdict}**] · {duration:.1f} s")
        st.code(stdout, language="text")
        st.rerun()  # rafraîchit la liste ci-dessous

with tab2:
    st.subheader("Probe Sandbox — valide chaîne Docker isolé")
    st.markdown(
        "Lance pytest dans le container `iaa-sandbox:latest` sur le code existant "
        "(`src/utils/text.py` + `tests/unit/test_text.py`). Isolation : `network=none`, "
        "`user=nobody`, `mem 512m`, `pids 256`. Durée < 5 s."
    )
    if st.button("▶ Lancer probe Sandbox", type="primary", key="run_sandbox"):
        with st.spinner("Probe sandbox en cours…"):
            try:
                exit_code, stdout, duration = _run_probe(
                    "probe_sandbox.py", "Probe Sandbox", timeout=120
                )
            except subprocess.TimeoutExpired:
                st.error("Timeout (>2 min). Vérifier Docker daemon + image.")
                st.stop()
            except Exception as exc:
                st.error(f"Crash : `{type(exc).__name__}: {exc}`")
                st.stop()

        color = "green" if exit_code == 0 else "red"
        st.markdown(f"### Exit {exit_code} · {duration:.1f} s")
        st.code(stdout, language="text")

st.divider()
st.subheader("📦 Probes archivées")

probes = _list_probes()
if not probes:
    st.info("Aucune probe encore archivée dans `data/probes/`. Lance un probe ci-dessus.")
else:
    st.caption(f"{len(probes)} probe(s) archivée(s), plus récente d'abord.")
    for path in probes:
        ts = path.stem.split("_")[0] if "_" in path.stem else path.stem
        case = "_".join(path.stem.split("_")[1:]) if "_" in path.stem else ""
        # Format YYYYMMDDTHHMMSS → ISO lisible
        try:
            from datetime import datetime as dt_

            dt_obj = dt_.strptime(ts, "%Y%m%dT%H%M%S")
            ts_human = dt_obj.strftime("%Y-%m-%d %H:%M")
        except (ValueError, ImportError):
            ts_human = ts
        with st.expander(f"**{case or path.stem}** · {ts_human}"):
            try:
                body = path.read_text(encoding="utf-8")
                st.markdown(body)
            except OSError as exc:
                st.error(f"Lecture impossible : {exc}")
