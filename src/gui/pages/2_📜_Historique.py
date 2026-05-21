"""Page Historique — liste filtrable des missions archivées + détail au clic."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from src.gui.services.memory_browser import (  # noqa: E402
    fmt_datetime,
    fmt_duration,
    list_missions,
    read_mission_body,
    stats,
)

st.set_page_config(page_title="Historique — IA-Expert-Army", page_icon="📜", layout="wide")
st.title("📜 Historique des missions")


@st.cache_data(ttl=10)
def _load_missions() -> list:
    return list_missions()


missions = _load_missions()
agg = stats(missions)

# Bandeau métriques
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total", agg["total"])
col2.metric("APPROVED", agg["approved"])
col3.metric("Taux APPROVED", f"{agg['approval_rate']:.1f} %" if agg["total"] else "—")
col4.metric(
    "Durée moyenne",
    fmt_duration(agg["avg_duration_s"]) if agg["avg_duration_s"] is not None else "—",
)

if not missions:
    st.info("Aucune mission encore archivée. Lance une mission depuis **🚀 Mission**.")
    st.stop()

# Filtres
st.divider()
filter_col1, filter_col2, filter_col3 = st.columns([2, 2, 1])
with filter_col1:
    guild_options = ["Toutes", *sorted({m.guild for m in missions})]
    guild_filter = st.selectbox("Guilde", guild_options)
with filter_col2:
    verdict_options = ["Tous", *sorted({m.final_verdict for m in missions})]
    verdict_filter = st.selectbox("Verdict", verdict_options)
with filter_col3:
    if st.button("🔄 Refresh", use_container_width=True):
        _load_missions.clear()
        st.rerun()

filtered = [
    m
    for m in missions
    if (guild_filter == "Toutes" or m.guild == guild_filter)
    and (verdict_filter == "Tous" or m.final_verdict == verdict_filter)
]

st.caption(f"{len(filtered)} mission(s) affichée(s) sur {len(missions)} archivée(s).")

# Liste
verdict_color = {
    "APPROVED": "green",
    "NEEDS_CHANGES": "orange",
    "REJECTED": "red",
}

for m in filtered:
    color = verdict_color.get(m.final_verdict, "gray")
    label_score = f" · score **{m.quality_score:.2f}**" if m.quality_score is not None else ""
    header = (
        f":{color}[**{m.final_verdict}**] · "
        f"**{m.title}**{label_score} · "
        f"{m.guild} · {fmt_duration(m.total_duration_seconds)} · "
        f"{fmt_datetime(m.started_at)}"
    )
    with st.expander(header):
        col1, col2, col3 = st.columns(3)
        col1.markdown(f"**Mission ID** : `{m.mission_id}`")
        col2.markdown(f"**Fichiers produits** : {m.files_produced_count}")
        col3.markdown(f"**Coût** : ${m.total_cost_usd:.4f}")

        body = read_mission_body(m.mission_id)
        if body:
            st.markdown(body)
        else:
            st.warning("Corps de mission introuvable.")
