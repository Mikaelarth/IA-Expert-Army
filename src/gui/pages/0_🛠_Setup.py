"""Page Setup — wizard d'installation/config click-to-go (ADR-027).

Objectif : un nouveau venu (ou l'auteur sur une nouvelle machine) doit pouvoir
lancer la GUI et voir d'un coup d'œil ce qui manque + agir d'un clic sans
toucher au terminal.

10 composants détectés (cf. `setup_runner.detect_all`) :
    1. Python ≥ 3.12          (toujours OK, affiché pour confort)
    2. uv (package manager)
    3. Ollama installé
    4. Ollama daemon démarré
    5-7. 3 modèles configurés (strategic / operational / bulk)
    8. Docker daemon (optionnel si ENABLE_SANDBOX=false)
    9. Image sandbox iaa-sandbox:latest (optionnel idem)
    10. Fichier .env

Actions disponibles selon le statut :
    - MISSING / STOPPED → bouton "Démarrer", "Pull", "Build", "Créer", ou
      "Télécharger" qui ouvre l'URL officielle quand l'install requiert UAC.
    - OK / SKIPPED      → pas d'action proposée.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from src.gui.services.setup_runner import (  # noqa: E402
    ComponentStatus,
    Status,
    build_sandbox_image,
    create_env_from_example,
    detect_all,
    pull_model,
    read_env_content,
    start_docker_desktop,
    start_ollama_daemon,
    write_env_content,
)

st.set_page_config(page_title="Setup — IA-Expert-Army", page_icon="🛠", layout="wide")
st.title("🛠 Setup — installation & configuration")
st.caption(
    "Vérifie en un coup d'œil ce qui manque sur ta machine et agis d'un clic. "
    "Pour les composants qui exigent un installeur système (Ollama, Docker Desktop), "
    "un bouton ouvre la page de téléchargement officielle."
)


_STATUS_BADGES = {
    Status.OK: "🟢 **OK**",
    Status.MISSING: "🔴 **MISSING**",
    Status.STOPPED: "🟡 **STOPPED**",
    Status.SKIPPED: "⚪ **SKIPPED**",
    Status.UNKNOWN: "❓ **UNKNOWN**",
}


def _render_status_row(comp: ComponentStatus) -> None:
    """Affiche une ligne : badge / label / détail / action."""
    cols = st.columns([1, 3, 5, 3])
    cols[0].markdown(_STATUS_BADGES.get(comp.status, comp.status.value))
    cols[1].markdown(f"**{comp.label}**")
    cols[2].caption(comp.detail)

    # Colonne action — choix selon fix_action / install_url / status
    with cols[3]:
        _render_action(comp)


def _render_action(comp: ComponentStatus) -> None:
    """Affiche le ou les boutons appropriés pour un composant."""
    if comp.status == Status.OK or comp.status == Status.SKIPPED:
        return

    # Action interne (start daemon, pull, build…) — dispatch sur fix_action
    if comp.fix_action == "start_ollama":
        if st.button("▶ Démarrer le daemon", key=f"btn_{comp.key}", use_container_width=True):
            with st.spinner("Lancement de `ollama serve`…"):
                result = start_ollama_daemon()
            if result.success:
                st.success(result.message)
                st.rerun()
            else:
                st.error(result.message)
        return

    if comp.fix_action and comp.fix_action.startswith("pull_model:"):
        model_name = comp.fix_action.split(":", 1)[1]
        if st.button(
            f"⬇ Pull `{model_name}`",
            key=f"btn_{comp.key}",
            use_container_width=True,
            help="Le téléchargement peut prendre plusieurs heures pour un 32B (~20 Go).",
        ):
            st.session_state[f"_pulling_{comp.key}"] = model_name
            st.rerun()
        return

    if comp.fix_action == "build_sandbox":
        if st.button(
            "🐳 Build l'image",
            key=f"btn_{comp.key}",
            use_container_width=True,
            help="Construit `iaa-sandbox:latest` (~2 min).",
        ):
            st.session_state["_building_sandbox"] = True
            st.rerun()
        return

    if comp.fix_action == "create_env":
        if st.button("📄 Créer `.env`", key=f"btn_{comp.key}", use_container_width=True):
            result = create_env_from_example()
            if result.success:
                st.success(result.message)
                st.rerun()
            else:
                st.error(result.message)
        return

    if comp.fix_action == "start_docker":
        if st.button("▶ Démarrer Docker Desktop", key=f"btn_{comp.key}", use_container_width=True):
            result = start_docker_desktop()
            if result.success:
                st.success(result.message)
            else:
                st.error(result.message)
        return

    # Si pas d'action interne mais URL d'installation : bouton link_button
    if comp.install_url is not None:
        st.link_button(
            "🌐 Télécharger",
            comp.install_url,
            use_container_width=True,
            help=f"Ouvre {comp.install_url} dans ton navigateur.",
        )


# ------------------------------------------------------------------
# 1. Bouton refresh + barre de résumé en haut
# ------------------------------------------------------------------

top_cols = st.columns([6, 2])
with top_cols[1]:
    if st.button("🔄 Re-détecter", use_container_width=True):
        # Pas de cache à invalider — detect_all() est exécuté à chaque rerun.
        st.rerun()

with st.spinner("Détection en cours…"):
    components = detect_all()

n_ok = sum(1 for c in components if c.status == Status.OK)
n_missing = sum(1 for c in components if c.status == Status.MISSING)
n_stopped = sum(1 for c in components if c.status == Status.STOPPED)
n_skipped = sum(1 for c in components if c.status == Status.SKIPPED)
n_required_missing = sum(
    1 for c in components if c.is_required and c.status in (Status.MISSING, Status.STOPPED)
)

m_cols = st.columns(5)
m_cols[0].metric("🟢 OK", n_ok)
m_cols[1].metric("🔴 MISSING", n_missing)
m_cols[2].metric("🟡 STOPPED", n_stopped)
m_cols[3].metric("⚪ SKIPPED", n_skipped)
m_cols[4].metric(
    "Bloquant",
    n_required_missing,
    delta=None if n_required_missing == 0 else f"-{n_required_missing}",
    delta_color="inverse",
)

if n_required_missing == 0:
    st.success(
        "✅ Tous les composants requis sont OK. Tu peux lancer une mission depuis "
        "la page **🚀 Mission**."
    )
else:
    st.warning(
        f"⚠ {n_required_missing} composant(s) requis manquant(s). Corrige ci-dessous "
        "avant de lancer une mission, sinon le router/sandbox vont échouer."
    )

st.divider()

# ------------------------------------------------------------------
# 2. Long-running action : pull modèle (sortie streaming)
# ------------------------------------------------------------------
# Pattern Streamlit : on stocke "en cours" dans session_state et on déroule
# la barre dans un slot dédié. Quand fini, on clear et rerun pour
# rafraîchir la détection.

for key in list(st.session_state.keys()):
    if isinstance(key, str) and key.startswith("_pulling_"):
        model_name = st.session_state[key]
        st.subheader(f"⬇ Téléchargement de `{model_name}` en cours")
        st.caption(
            "Ne ferme pas l'onglet. La fermeture **n'interrompt pas** le pull côté "
            "daemon Ollama (il continue en arrière-plan). Pour annuler proprement, "
            "exécute `ollama stop` dans un terminal."
        )
        progress_bar = st.progress(0.0, text="Initialisation…")
        status_text = st.empty()
        try:
            last_status = ""
            for ev in pull_model(model_name):
                pct = ev.percent
                if ev.status != last_status:
                    status_text.text(f"[{ev.status}] {ev.detail}".strip())
                    last_status = ev.status
                if pct is not None:
                    progress_bar.progress(
                        min(pct / 100.0, 1.0),
                        text=(
                            f"{ev.status} · "
                            f"{ev.completed / 1e9:.2f} / {ev.total / 1e9:.2f} Go "
                            f"({pct:.1f} %)"
                        ),
                    )
            progress_bar.progress(1.0, text="Terminé.")
            st.success(f"✅ `{model_name}` pullé.")
        except RuntimeError as exc:
            st.error(str(exc))
        finally:
            del st.session_state[key]
        if st.button("Continuer", type="primary"):
            st.rerun()
        st.stop()

# ------------------------------------------------------------------
# 3. Long-running action : build sandbox (log live)
# ------------------------------------------------------------------

if st.session_state.get("_building_sandbox"):
    st.subheader("🐳 Build de l'image sandbox en cours")
    log_box = st.empty()
    lines: list[str] = []
    try:
        for line in build_sandbox_image():
            lines.append(line)
            # Affiche les 200 dernières lignes pour éviter le freeze sur très long log
            log_box.code("\n".join(lines[-200:]), language="text")
    except Exception as exc:
        st.error(f"Crash build : {type(exc).__name__}: {exc}")
    st.session_state["_building_sandbox"] = False
    if st.button("Continuer", type="primary"):
        st.rerun()
    st.stop()

# ------------------------------------------------------------------
# 4. Table principale des composants
# ------------------------------------------------------------------

st.subheader("État des composants")
for comp in components:
    _render_status_row(comp)
    st.divider()

# ------------------------------------------------------------------
# 5. Éditeur .env inline (pour ajuster modèles / endpoints sans toucher au terminal)
# ------------------------------------------------------------------

st.subheader("Éditeur `.env`")
st.caption(
    "Ajuste les variables sans quitter la GUI. Les changements prennent effet au "
    "prochain démarrage du process (relance Streamlit pour `get_settings()` rechargé)."
)

env_content = read_env_content()
if not env_content:
    st.info(
        "Aucun `.env` détecté. Crée-le via le bouton 'Créer' du composant **Fichier `.env`** "
        "ci-dessus pour pré-remplir depuis `.env.example`."
    )
else:
    edited = st.text_area(
        ".env",
        value=env_content,
        height=350,
        label_visibility="collapsed",
        help="Lignes `KEY=value`. Voir `.env.example` pour la liste des variables.",
    )
    save_col, info_col = st.columns([1, 5])
    with save_col:
        if st.button("💾 Sauvegarder", type="primary", use_container_width=True):
            result = write_env_content(edited)
            if result.success:
                st.success(result.message + " — relance Streamlit pour appliquer.")
            else:
                st.error(result.message)
    with info_col:
        st.caption(
            "ℹ Streamlit ne re-charge pas `get_settings()` automatiquement après save "
            "(le `lru_cache` retient la première instance). Quitte et relance "
            "`streamlit run scripts/run_gui.py` pour appliquer les changements."
        )
