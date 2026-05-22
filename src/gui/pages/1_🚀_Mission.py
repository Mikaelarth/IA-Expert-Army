"""Page Mission — formulaire + lancement + résultat (ADR-026).

Pattern : formulaire avec st.form pour batcher l'input (pas de re-run par
caractère tapé) + appel synchrone `run_mission_sync` avec `st.spinner`
pendant les 20-40 min de génération Qwen 32B local.

Le caller voit : spinner → verdict → score → fichiers écrits → résultat
sandbox. L'archive markdown est disponible dans Historique.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from src.gui.services.memory_browser import fmt_duration  # noqa: E402
from src.gui.services.mission_runner import (  # noqa: E402
    MissionRunOutcome,
    MissionRunRequest,
    available_guilds,
    run_mission_streaming,
)
from src.gui.services.templates_browser import (  # noqa: E402
    list_templates,
    render_template,
)
from src.orchestrator.progress import ProgressEvent  # noqa: E402
from src.tools.apply_files import ApplyAction  # noqa: E402

# v0.8.0 F2 — formatte un ProgressEvent pour st.status (streaming live)
_EVENT_ICONS = {
    "mission_started": "🚀",
    "mission_routed": "🧭",
    "agent_started": "🤖",
    "agent_resumed": "♻️",
    "agent_completed": "✅",
    "agent_failed": "❌",
    "repair_loop_started": "🔧",
    "mission_completed": "🏁",
}


def _render_progress_event(event: ProgressEvent) -> None:
    """Affiche un event dans le st.status courant. Pas de retour ; on écrit
    directement dans le scope st.status grâce au context manager actif."""
    icon = _EVENT_ICONS.get(event.event_type, "•")
    data = event.data or {}

    # Format adapté selon le type — on garde court pour ne pas saturer l'UI
    if event.event_type == "agent_completed":
        agent = data.get("agent_name", "?")
        tokens = data.get("tokens_out", 0)
        cost = data.get("cost_usd", 0.0)
        duration = data.get("duration_seconds", 0.0)
        sat = " ⚠️ saturé" if data.get("saturated") else ""
        st.write(
            f"{icon} **{agent}** terminé en `{duration:.1f}s` ({tokens} tokens, ${cost:.4f}){sat}"
        )
    elif event.event_type == "agent_resumed":
        agent = data.get("agent_name", "?")
        st.write(f"{icon} **{agent}** restauré depuis checkpoint (skip LLM)")
    elif event.event_type == "agent_started":
        agent = data.get("agent_name", "?")
        st.write(f"{icon} **{agent}** démarre…")
    elif event.event_type == "agent_failed":
        agent = data.get("agent_name", "?")
        st.write(f"{icon} **{agent}** a échoué : `{data.get('error', '?')}`")
    elif event.event_type == "mission_completed":
        verdict = data.get("verdict", "?")
        score = data.get("quality_score")
        score_str = f"{score:.2f}" if isinstance(score, (int, float)) else "—"
        st.write(f"{icon} Verdict **{verdict}** (score {score_str})")
    else:
        st.write(f"{icon} {event.message}")


st.set_page_config(page_title="Mission — IA-Expert-Army", page_icon="🚀", layout="wide")
st.title("🚀 Lancer une mission")
st.caption(
    "Compose une mission. Le `MissionRouter` route automatiquement vers la bonne guilde "
    "(ou force avec `force_guild`). Latence typique : 20-40 min sur Qwen2.5 32B local."
)

# ============================================================================
# v0.8.0 F3 — Picker de templates (au-dessus du formulaire, optionnel)
# ============================================================================

with st.expander("📋 Démarrer depuis un template (optionnel)", expanded=False):
    available = list_templates()
    if not available:
        st.info(
            "Aucun template dans `templates/missions/`. Cf. `templates/README.md` pour le format."
        )
    else:
        tpl_options = ["(aucun — composition manuelle ci-dessous)"] + [
            f"{t.name} — {t.description}" for t in available
        ]
        tpl_choice = st.selectbox(
            "Template",
            options=tpl_options,
            key="_template_choice",
            help="Choisir un template pré-paramétré pour démarrer plus vite.",
        )

        if tpl_choice != tpl_options[0]:
            idx = tpl_options.index(tpl_choice) - 1
            tpl = available[idx]
            st.caption(
                f"**{tpl.name}** · Guilde suggérée : `{tpl.guild or 'auto'}` · "
                f"Tags : {', '.join(tpl.tags) if tpl.tags else '—'}"
            )

            with st.form(f"template_params_{tpl.id}", clear_on_submit=False):
                st.markdown("**Paramètres du template** :")
                param_values: dict[str, str] = {}
                for p in tpl.params:
                    val = st.text_input(
                        p.label + (" *" if p.required else ""),
                        value=p.example,
                        key=f"_tpl_{tpl.id}_{p.name}",
                        help=f"Variable Jinja : `{{{{ {p.name} }}}}`",
                    )
                    param_values[p.name] = val

                generate = st.form_submit_button(
                    "✨ Générer la description depuis ce template",
                    type="primary",
                    use_container_width=True,
                )

            if generate:
                missing = [
                    p.label
                    for p in tpl.params
                    if p.required and not param_values.get(p.name, "").strip()
                ]
                if missing:
                    st.error(f"Paramètres requis manquants : {', '.join(missing)}")
                else:
                    try:
                        rendered = render_template(tpl, param_values)
                        # Pré-remplir le formulaire principal via session_state
                        st.session_state["_mission_title_from_tpl"] = tpl.name
                        st.session_state["_mission_desc_from_tpl"] = rendered
                        st.session_state["_mission_guild_from_tpl"] = tpl.guild or ""
                        st.success(
                            f"✅ Description générée ({len(rendered)} chars). "
                            "Elle est pré-remplie ci-dessous — ajuste si nécessaire puis lance."
                        )
                    except ValueError as exc:
                        st.error(f"Erreur de rendu Jinja : {exc}")


# Récupération des valeurs pré-remplies par le template (si applicable)
_prefilled_title = st.session_state.get("_mission_title_from_tpl", "")
_prefilled_desc = st.session_state.get("_mission_desc_from_tpl", "")
_prefilled_guild = st.session_state.get("_mission_guild_from_tpl", "")


with st.form("mission_form", clear_on_submit=False):
    title = st.text_input(
        "Titre court",
        value=_prefilled_title,
        placeholder="Ex : Crée un calculateur de scoring SEO",
        help="Une ligne descriptive. Utilisée par le router pour classifier la guilde.",
    )
    description = st.text_area(
        "Description détaillée",
        value=_prefilled_desc,
        placeholder=(
            "Décris précisément le livrable, les contraintes (stdlib only, "
            "max_tokens, etc.), les fichiers cibles et les tests attendus. "
            "Plus c'est précis, mieux les agents convergent."
        ),
        height=300 if _prefilled_desc else 200,
    )

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        guild_options = ["(auto — détection mots-clés)", *available_guilds()]
        default_guild_idx = (
            guild_options.index(_prefilled_guild) if _prefilled_guild in guild_options else 0
        )
        force_guild = st.selectbox(
            "Guilde (forcée)",
            options=guild_options,
            index=default_guild_idx,
            help="Auto laisse le HeuristicGuildClassifier décider. Force pour bypasser.",
        )
    with col2:
        apply_files_on_success = st.checkbox(
            "--apply",
            value=False,
            help="Si APPROVED, écrit les fichiers sur disque (whitelist src/ tests/ docs/…)",
        )
    with col3:
        validate_sandbox = st.checkbox(
            "--validate",
            value=False,
            help="Après apply, lance pytest dans le sandbox Docker isolé (image iaa-sandbox:latest).",
        )

    force_overwrite = st.checkbox(
        "--force (overwrite des fichiers existants)",
        value=False,
        help="Sans --force, apply skip les fichiers déjà présents. Avec --force, écrase. À utiliser prudemment.",
    )

    submitted = st.form_submit_button(
        "▶ Lancer la mission", type="primary", use_container_width=True
    )

if submitted:
    if not title.strip() or not description.strip():
        st.error("Titre ET description sont obligatoires.")
        st.stop()

    if validate_sandbox and not apply_files_on_success:
        st.warning(
            "⚠️ `--validate` sans `--apply` n'a pas d'effet (rien à valider). "
            "Coche aussi `--apply` ou décoche `--validate`."
        )

    forced = force_guild if force_guild != "(auto — détection mots-clés)" else None

    req = MissionRunRequest(
        title=title.strip(),
        description=description.strip(),
        force_guild=forced,
        apply_files_on_success=apply_files_on_success,
        force_overwrite=force_overwrite,
        validate_sandbox=validate_sandbox,
    )

    # v0.8.0 F2 — Streaming live des events de mission via st.status.
    # Plus de spinner aveugle : on voit chaque agent démarrer/terminer en direct.
    with st.status(
        "🚀 Mission démarrée — 20-40 min sur Qwen 32B local",
        expanded=True,
        state="running",
    ) as status:
        outcome: MissionRunOutcome | None = None
        try:
            for item in run_mission_streaming(req):
                if isinstance(item, ProgressEvent):
                    _render_progress_event(item)
                else:
                    outcome = item  # MissionRunOutcome final
        except Exception as exc:
            status.update(label=f"❌ Crash : {type(exc).__name__}", state="error")
            st.error(f"Mission a planté : `{type(exc).__name__}: {exc}`")
            st.exception(exc)
            st.stop()

        if outcome is None:
            status.update(label="❌ Aucun résultat reçu", state="error")
            st.error("Le streaming a terminé sans MissionRunOutcome — état inattendu.")
            st.stop()

        verdict = outcome.result.final_verdict
        final_label = f"✅ {verdict}" if verdict == "APPROVED" else f"⚠ {verdict}"
        final_state = "complete" if verdict == "APPROVED" else "error"
        status.update(label=final_label, state=final_state)

    result = outcome.result

    verdict_color = {
        "APPROVED": "green",
        "NEEDS_CHANGES": "orange",
        "REJECTED": "red",
    }.get(result.final_verdict, "gray")
    st.markdown(f"### Résultat : :{verdict_color}[**{result.final_verdict}**]")

    metrics = st.columns(5)
    metrics[0].metric("Guilde", result.guild)
    metrics[1].metric(
        "Score qualité",
        f"{result.quality_score:.2f}" if result.quality_score is not None else "—",
    )
    metrics[2].metric("Durée", fmt_duration(result.total_duration_seconds))
    metrics[3].metric("Coût USD", f"${result.total_cost_usd:.4f}")
    metrics[4].metric("Mission ID", result.mission_id[:8])

    if result.summary:
        st.subheader("📋 Résumé du Reviewer")
        st.markdown(result.summary)

    if outcome.apply_results:
        st.subheader("📂 Fichiers appliqués")
        for ar in outcome.apply_results:
            icon = {
                ApplyAction.WRITTEN: "✅",
                ApplyAction.SKIPPED_EXISTS: "⏭",
                ApplyAction.REJECTED_PATH: "❌",
                ApplyAction.REJECTED_NAME: "❌",
                ApplyAction.REJECTED_OUTSIDE: "❌",
                ApplyAction.REJECTED_DIR: "❌",
            }.get(ar.action, "❓")
            st.markdown(
                f"- {icon} `{ar.path}` — **{ar.action.value}** · {ar.reason or f'{ar.bytes_written} octets'}"
            )

    if outcome.sandbox_skipped_reason:
        st.info(f"Sandbox : {outcome.sandbox_skipped_reason}")
    elif outcome.sandbox_exit_code is not None:
        st.subheader("🐳 Validation sandbox")
        sandbox_ok = outcome.sandbox_exit_code == 0
        st.markdown(
            f"**pytest exit_code = {outcome.sandbox_exit_code}** "
            f"({'✅ tests verts' if sandbox_ok else '❌ tests rouges'}) · "
            f"{outcome.sandbox_duration_s:.2f} s"
        )
        with st.expander("stdout pytest", expanded=not sandbox_ok):
            st.code(outcome.sandbox_stdout or "(vide)", language="text")
        if outcome.sandbox_stderr.strip():
            with st.expander("stderr pytest"):
                st.code(outcome.sandbox_stderr, language="text")

    with st.expander("⚙️ Raw result (JSON complet)"):
        st.json(result.model_dump(mode="json"))

    st.success(
        f"Mission archivée dans `data/memory/missions/{result.mission_id}.md` — "
        f"consultable depuis 📜 Historique."
    )
