"""Page Skills — explorateur des skills auto-extraites par agent."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from src.gui.services.memory_browser import (  # noqa: E402
    fmt_datetime,
    list_skills,
    read_skill_body,
)

st.set_page_config(page_title="Skills — IA-Expert-Army", page_icon="🧠", layout="wide")
st.title("🧠 Skills auto-extraites")
st.caption(
    "Skills synthétisées par le `PatternMiner` à partir des meilleurs épisodes APPROVED. "
    "Injectées automatiquement dans le prompt de chaque agent à la mission suivante "
    "(boucle d'apprentissage continu, cf. ADR-004 + ADR-006)."
)


@st.cache_data(ttl=15)
def _load_skills() -> dict:
    return list_skills()


skills_by_agent = _load_skills()

if not skills_by_agent:
    st.info(
        "Aucune skill auto-extraite. Lance `uv run python scripts/nightly_learning.py` "
        "après avoir archivé au moins 2 missions APPROVED par agent."
    )
    st.stop()

total = sum(len(v) for v in skills_by_agent.values())
col1, col2, col3 = st.columns(3)
col1.metric("Total skills", total)
col2.metric("Agents avec skills", len(skills_by_agent))
col3.metric(
    "Skills/agent moyen",
    f"{total / len(skills_by_agent):.1f}" if skills_by_agent else "—",
)

st.divider()

agents = sorted(skills_by_agent.keys())
selected_agent = st.selectbox("Agent", agents)

skills = skills_by_agent[selected_agent]
st.caption(f"{len(skills)} skill(s) pour `{selected_agent}` (plus récente d'abord).")

for skill in skills:
    score_label = (
        f" · sources score moyen {skill.sources_avg_score:.2f}"
        if skill.sources_avg_score > 0
        else ""
    )
    header = (
        f"**{skill.title}** · "
        f"{skill.sources_count} source(s){score_label} · "
        f"{fmt_datetime(skill.created_at)}"
    )
    with st.expander(header):
        if skill.summary:
            st.markdown(f"*{skill.summary}*")
            st.divider()
        body = read_skill_body(skill.path)
        if body:
            st.markdown(body)
        else:
            st.warning("Corps de skill introuvable.")
