"""GUI Streamlit IA-Expert-Army — page d'accueil (ADR-026).

Multipages : Streamlit charge automatiquement les fichiers dans `pages/`
(ordre lexicographique sur le préfixe numérique 1_, 2_, …).

Lancement : `streamlit run scripts/run_gui.py` (port 8501, localhost).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permet d'importer `src.*` quand Streamlit est lancé depuis scripts/run_gui.py
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.gui.services.memory_browser import list_missions, list_skills, stats  # noqa: E402

st.set_page_config(
    page_title="IA-Expert-Army",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=10)
def _load_overview() -> dict:
    """Charge un résumé du projet (caché 10 s pour éviter les re-lectures)."""
    missions = list_missions()
    skills = list_skills()
    s = get_settings()
    return {
        "n_missions": len(missions),
        "n_skills": sum(len(v) for v in skills.values()),
        "n_agents_with_skills": len(skills),
        "stats": stats(missions),
        "model_strategic": s.model_strategic,
        "model_operational": s.model_operational,
        "model_bulk": s.model_bulk,
        "ollama_base_url": s.ollama_base_url,
    }


def _render_accueil() -> None:
    st.title("🤖 IA-Expert-Army")
    st.caption(
        "Armée d'agents IA spécialisés · backend Ollama local · mémoire vivante · "
        "apprentissage continu observable"
    )

    overview = _load_overview()

    cols = st.columns(4)
    cols[0].metric("Missions archivées", overview["n_missions"])
    cols[1].metric("Skills auto-extraites", overview["n_skills"])
    cols[2].metric(
        "Taux APPROVED",
        f"{overview['stats']['approval_rate']:.1f} %" if overview["n_missions"] else "—",
    )
    cols[3].metric(
        "Score moyen",
        f"{overview['stats']['avg_score']:.2f}"
        if overview["stats"]["avg_score"] is not None
        else "—",
    )

    st.divider()

    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Stack LLM (Ollama local)")
        st.markdown(
            f"- **Strategic** (architect, QG, BA…) : `{overview['model_strategic']}`\n"
            f"- **Operational** (developer, reviewer…) : `{overview['model_operational']}`\n"
            f"- **Bulk** (tech_watch) : `{overview['model_bulk']}`\n"
            f"- **Endpoint** : `{overview['ollama_base_url']}`"
        )

    with col_right:
        st.subheader("Comment utiliser")
        st.markdown(
            "1. **🚀 Mission** — lance une mission engineering/research/creative/business\n"
            "2. **📜 Historique** — consulte les missions archivées (verdict, score, durée)\n"
            "3. **🧠 Skills** — explore les skills auto-extraites par agent\n"
            "4. **🏥 Health** — vérifie l'état du système (Ollama, Docker, mémoire)\n"
            "5. **🔬 Probes** — outils de mesure (probe Reviewer, probe sandbox)"
        )

    st.divider()
    st.subheader("Statut par guilde")
    by_guild = overview["stats"]["by_guild"]
    if not by_guild:
        st.info("Aucune mission encore archivée. Va sur **🚀 Mission** pour démarrer.")
    else:
        guild_cols = st.columns(len(by_guild))
        for col, (guild, count) in zip(guild_cols, sorted(by_guild.items()), strict=False):
            col.metric(guild.title(), count)

    by_verdict = overview["stats"]["by_verdict"]
    if by_verdict:
        st.subheader("Verdicts agrégés")
        verdict_cols = st.columns(len(by_verdict))
        for col, (verdict, count) in zip(verdict_cols, sorted(by_verdict.items()), strict=False):
            col.metric(verdict, count)


def main() -> None:
    with st.sidebar:
        st.markdown("### 🤖 IA-Expert-Army")
        st.caption("v0.6.0 · Ollama local")
        st.divider()
        st.markdown(
            "**Navigation** ↑\n\n"
            "Sélectionne une page dans la barre latérale "
            "(Mission, Historique, Skills, Health, Probes)."
        )
        st.divider()
        if st.button("🔄 Refresh stats", use_container_width=True):
            _load_overview.clear()
            st.rerun()
        st.caption("Cache 10 s sur l'accueil. Bouton force le rechargement.")
        st.divider()
        st.caption(
            "Repo : [github.com/Mikaelarth/IA-Expert-Army]"
            "(https://github.com/Mikaelarth/IA-Expert-Army)"
        )

    _render_accueil()


if __name__ == "__main__":
    main()
