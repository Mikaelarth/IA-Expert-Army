"""Page Explainability — 3 onglets pour ouvrir la boîte noire (v0.9.0 C1).

1. **Pourquoi cette guilde ?** — re-joue le scoring héuristique du
   `MissionRouter` sur un titre + description saisis, montre le score par
   guilde avec les mots-clés matchés.

2. **Métriques agents** — agrège depuis FileMemory les stats par agent
   (latence, score moyen, taux d'échec, saturation). Permet d'identifier
   les dérives qualité.

3. **Pourquoi ce verdict ?** — pour un mission_id donné, recharge le
   summary + l'épisode du Reviewer et affiche le raisonnement détaillé.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.gui.services.explainability import (  # noqa: E402
    compute_agent_metrics,
    explain_guild_classification,
    explain_mission_verdict,
)
from src.memory.file_memory import FileMemory  # noqa: E402

st.set_page_config(
    page_title="Explainability — IA-Expert-Army",
    page_icon="🔍",
    layout="wide",
)
st.title("🔍 Explainability — ouvrir la boîte noire")
st.caption(
    "3 outils pour comprendre les décisions du système : routage de guilde, "
    "performance par agent, raisonnement du Reviewer sur une mission."
)


@st.cache_data(ttl=30)
def _load_metrics() -> list:
    """Cache 30 s pour ne pas re-parser tous les épisodes à chaque interaction."""
    s = get_settings()
    memory = FileMemory(s.project_root / "data" / "memory")
    return compute_agent_metrics(memory)


tab_guild, tab_agents, tab_verdict = st.tabs(
    ["🧭 Pourquoi cette guilde ?", "📊 Métriques agents", "⚖️ Pourquoi ce verdict ?"]
)


# ============================================================================
# Tab 1 — Pourquoi cette guilde ?
# ============================================================================

with tab_guild:
    st.markdown(
        "Saisis un titre + description (comme pour une vraie mission). On affiche "
        "le score héuristique par guilde et les mots-clés détectés, pour comprendre "
        "le verdict du `HeuristicGuildClassifier`."
    )

    with st.form("explain_guild_form"):
        title = st.text_input(
            "Titre court",
            placeholder="Ex: Crée un endpoint FastAPI /health",
        )
        description = st.text_area(
            "Description détaillée",
            placeholder="Décris la mission comme tu le ferais sur la page Mission…",
            height=150,
        )
        submitted = st.form_submit_button("🔍 Expliquer", type="primary")

    if submitted and (title.strip() or description.strip()):
        expl = explain_guild_classification(title.strip(), description.strip())

        winner_label = f"**Guilde retenue : `{expl.winner}`**"
        if expl.is_tie:
            winner_label += " · ⚖️ tie-break appliqué (égalité de scores)"
        st.success(winner_label)

        # Tableau de scores
        st.subheader("Score par guilde")
        score_cols = st.columns(len(expl.scores))
        for i, gs in enumerate(expl.scores):
            badge = "🏆" if gs.guild == expl.winner else ""
            score_cols[i].metric(f"{badge} {gs.guild}", gs.total_score)

        # Détail des mots-clés par guilde (expander)
        st.subheader("Mots-clés détectés (détail)")
        for gs in expl.scores:
            with st.expander(
                f"{gs.guild} · score {gs.total_score} · {len(gs.matches)} match(s)",
                expanded=(gs.guild == expl.winner and gs.matches),
            ):
                if not gs.matches:
                    st.caption("Aucun mot-clé matché pour cette guilde.")
                    continue
                for m in gs.matches:
                    location = "🎯 titre" if m.in_title else "📄 description"
                    strong = " · ⚡ strong verb (+2 bonus)" if m.is_strong_verb else ""
                    st.markdown(f"- `{m.keyword}` — **{m.weight} points** ({location}{strong})")

        if expl.is_tie:
            st.info(
                f"En cas d'égalité de score max, l'ordre de tie-break est : "
                f"{' → '.join(f'`{g}`' for g in expl.tie_break_order)} "
                "(par maturité historique des guildes, cf. ADR-001)."
            )

# ============================================================================
# Tab 2 — Métriques agents
# ============================================================================

with tab_agents:
    st.markdown(
        "Statistiques agrégées par agent depuis `data/memory/episodes/`. "
        "Permet de repérer les agents qui dérivent (qualité en baisse, "
        "latence en hausse, saturation chronique)."
    )

    col_refresh, col_info = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 Recalculer", use_container_width=True):
            _load_metrics.clear()
            st.rerun()
    with col_info:
        st.caption("Cache 30 s — clique pour invalider et re-parser tous les épisodes.")

    with st.spinner("Agrégation des épisodes…"):
        metrics = _load_metrics()

    if not metrics:
        st.info(
            "Aucun épisode archivé dans `data/memory/episodes/`. "
            "Lance des missions pour alimenter les métriques."
        )
    else:
        # Vue d'ensemble : tableau compact triable
        rows = [
            {
                "Agent": m.agent_name,
                "Episodes": m.n_episodes,
                "Success rate": f"{m.success_rate:.0%}",
                "Avg quality": f"{m.avg_quality_score:.2f}"
                if m.avg_quality_score is not None
                else "—",
                "Avg duration (s)": m.avg_duration_seconds,
                "Avg tokens out": int(m.avg_tokens_out),
                "Saturation rate": f"{m.saturation_rate:.0%}",
                "Total cost ($)": f"{m.total_cost_usd:.4f}",
            }
            for m in metrics
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

        # Alertes drift potentiel
        st.subheader("Alertes potentielles")
        alerts = []
        for m in metrics:
            if m.n_episodes >= 5 and m.success_rate < 0.7:
                alerts.append(
                    f"⚠️ **{m.agent_name}** — taux de succès {m.success_rate:.0%} "
                    f"sur {m.n_episodes} épisodes (sous le seuil 70%)"
                )
            if m.n_episodes >= 5 and m.saturation_rate > 0.2:
                alerts.append(
                    f"⚠️ **{m.agent_name}** — taux de saturation "
                    f"{m.saturation_rate:.0%} (sortie tronquée fréquente, "
                    "augmenter max_tokens ?)"
                )
            if m.avg_quality_score is not None and m.n_episodes >= 5 and m.avg_quality_score < 0.80:
                alerts.append(
                    f"⚠️ **{m.agent_name}** — score qualité moyen "
                    f"{m.avg_quality_score:.2f} sous le seuil 0.80"
                )
        if alerts:
            for a in alerts:
                st.warning(a)
        else:
            st.success("✅ Aucune dérive détectée sur les agents avec ≥5 épisodes.")


# ============================================================================
# Tab 3 — Pourquoi ce verdict ?
# ============================================================================

with tab_verdict:
    st.markdown(
        "Pour une mission donnée, on recharge le summary + l'épisode du `code_reviewer` "
        "et on affiche le raisonnement complet. Aide à comprendre pourquoi un score "
        "0.87 et pas 0.95."
    )

    mission_id_input = st.text_input(
        "Mission ID (UUID)",
        placeholder="ex: b9ac9449-7c1e-48e8-b1e6-aa1f138c723e",
        help="Récupère le mission_id depuis la page 📜 Historique ou les logs.",
    )

    if mission_id_input.strip():
        memory = FileMemory(get_settings().project_root / "data" / "memory")
        expl = explain_mission_verdict(memory, mission_id_input.strip())

        if expl is None:
            st.error(
                f"Aucune mission trouvée pour `{mission_id_input.strip()}`. "
                "Vérifie l'UUID — cherche dans `data/memory/missions/`."
            )
        else:
            # Header avec verdict + score
            verdict_color = {
                "APPROVED": "green",
                "NEEDS_CHANGES": "orange",
                "REJECTED": "red",
            }.get(expl.final_verdict, "gray")
            st.markdown(
                f"### {expl.title}\n\n"
                f"Verdict : :{verdict_color}[**{expl.final_verdict}**] · "
                f"Score qualité : "
                f"**{expl.quality_score if expl.quality_score is not None else '—'}**"
            )

            if expl.qg_verdict:
                qg_color = "green" if expl.qg_verdict == "ACCEPT" else "orange"
                st.markdown(f"**Quality Guardian** : :{qg_color}[`{expl.qg_verdict}`]")
                if expl.qg_rationale:
                    st.caption(expl.qg_rationale)

            st.subheader("📋 Résumé du Reviewer")
            st.markdown(expl.review_summary or "_(pas de résumé enregistré)_")

            if expl.review_raw_yaml:
                with st.expander("🔬 YAML brut de l'épisode Reviewer", expanded=False):
                    st.caption(f"Source : `{expl.reviewer_episode_path}`")
                    st.code(expl.review_raw_yaml, language="yaml")
            else:
                st.info(
                    "L'épisode du Reviewer pour cette mission n'a pas été retrouvé "
                    "(peut être une mission ancienne ou un échec en amont)."
                )
