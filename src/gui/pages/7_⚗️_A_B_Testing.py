"""Page A/B Testing — compare des variantes de prompts (v0.9.0 A2, ADR-029).

Workflow utilisateur :
1. Sélectionner un rôle (agent) qui a des variantes définies.
2. Voir le tableau de stats (n_missions, approval_rate, avg_quality_score,
   avg_cost, avg_duration) par variante.
3. Recommandation suggérée si Δ approval_rate ≥ 10pp et n ≥ 10.
4. Bouton "✅ Promouvoir comme canonique" qui archive l'ancien canonique
   et renomme la variante en `<role>.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.learning.prompt_ab import PromptAB  # noqa: E402

st.set_page_config(
    page_title="A/B Testing — IA-Expert-Army",
    page_icon="⚗️",
    layout="wide",
)
st.title("⚗️ A/B Testing des prompts (ADR-029)")
st.caption(
    "Compare les variantes de prompts via les stats mesurées sur du vrai trafic. "
    "Suggest-only : tu valides la promotion manuellement après vérification."
)

settings = get_settings()
prompts_root = settings.project_root / "prompts"
ab = PromptAB(
    prompts_root=prompts_root,
    ab_store_root=settings.project_root / "data" / "ab_tests",
)

# ============================================================================
# Découverte des rôles qui ont des variantes
# ============================================================================


def _discover_roles_with_variants() -> list[tuple[str, Path]]:
    """Retourne [(role, canonical_path), …] pour tous les .md de prompts/
    qui ont au moins UNE variante à côté (`<role>_<label>.md`)."""
    if not prompts_root.exists():
        return []
    out: list[tuple[str, Path]] = []
    for md_path in sorted(prompts_root.rglob("*.md")):
        if md_path.parent.name in ("archive", "_archive"):
            continue
        # Skip les variantes : ne garde que les chemins qui SONT canoniques
        # (= ils ont des fichiers `<stem>_*.md` à côté qui ne sont pas
        # eux-mêmes des variantes d'un autre prompt)
        variants = ab.discover_variants(md_path)
        if len(variants) >= 2:  # canonique + ≥ 1 variante
            out.append((md_path.stem, md_path))
    # Dédup (si plusieurs paths matchent un même stem on prend le premier)
    seen = set()
    unique = []
    for role, path in out:
        if role in seen:
            continue
        seen.add(role)
        unique.append((role, path))
    return unique


roles_with_variants = _discover_roles_with_variants()
ab_enabled_set = settings.ab_testing_agents_set

# ============================================================================
# Top — vue d'ensemble
# ============================================================================

st.subheader("Configuration A/B en cours")
cols = st.columns(3)
cols[0].metric("Rôles avec variantes", len(roles_with_variants))
cols[1].metric("A/B activés (.env)", len(ab_enabled_set))
cols[2].metric(
    "Trafic mesuré",
    f"{ab.ab_store_root.exists() and sum(1 for _ in ab.ab_store_root.rglob('*.json'))} runs",
)

if not roles_with_variants:
    st.info(
        "Aucun rôle avec des variantes détecté. Pour activer l'A/B sur un agent :\n\n"
        "1. Crée `prompts/<dossier>/<role>_<label>.md` à côté du `<role>.md` canonique.\n"
        "2. Dans `.env`, mets `AB_TESTING_AGENTS=<role>` (sépare par virgules pour plusieurs).\n"
        "3. Relance Streamlit pour prendre en compte le settings.\n"
        "4. Laisse tourner ≥10 missions Engineering, puis reviens ici.\n\n"
        "Cf. [`docs/adr/029-prompt-ab-testing-mvp.md`](docs/adr/029-prompt-ab-testing-mvp.md) "
        "pour le détail du protocole."
    )
    st.stop()

# ============================================================================
# Sélection d'un rôle pour analyse détaillée
# ============================================================================

st.divider()
st.subheader("Analyse par rôle")

role_options = [r for r, _ in roles_with_variants]
selected_role = st.selectbox(
    "Rôle à analyser",
    options=role_options,
    help="Liste limitée aux rôles qui ont au moins une variante définie.",
)

if selected_role:
    canonical_path = next(p for r, p in roles_with_variants if r == selected_role)
    variants = ab.discover_variants(canonical_path)
    is_active = selected_role in ab_enabled_set

    # Liste des variantes
    st.markdown(
        f"**Variantes pour `{selected_role}`** "
        f"({'🟢 actif' if is_active else '⚪ inactif — ajoute à `AB_TESTING_AGENTS` pour activer'})"
    )
    var_rows = []
    for v in variants:
        var_rows.append(
            {
                "Label": v.label or "(canonique)",
                "Path": str(v.path.relative_to(settings.project_root)),
                "Lines": (
                    len(v.path.read_text(encoding="utf-8").splitlines()) if v.path.exists() else 0
                ),
            }
        )
    st.dataframe(var_rows, use_container_width=True, hide_index=True)

    # Stats agrégées
    st.markdown("**Stats mesurées**")
    stats = ab.compute_stats(selected_role)
    if not stats:
        st.info(
            "Aucun trafic mesuré pour ce rôle. "
            f"{'Lance des missions pour collecter.' if is_active else 'Active dabord via `AB_TESTING_AGENTS`.'}"
        )
    else:
        stat_rows = [
            {
                "Variante": s.label or "(canonique)",
                "Missions": s.n_missions,
                "APPROVED": s.n_approved,
                "NEEDS_CHANGES": s.n_needs_changes,
                "REJECTED": s.n_rejected,
                "Approval rate": f"{s.approval_rate:.0%}",
                "Avg quality": f"{s.avg_quality_score:.2f}"
                if s.avg_quality_score is not None
                else "—",
                "Avg duration (s)": s.avg_duration_seconds,
                "Avg cost ($)": f"{s.avg_cost_usd:.4f}",
            }
            for s in stats
        ]
        st.dataframe(stat_rows, use_container_width=True, hide_index=True)

        # Recommandation
        comp = ab.compare(selected_role)
        if comp.is_significant and comp.recommended_label:
            st.success(f"🏆 **Recommandé : `{comp.recommended_label}`** — {comp.rationale}")
        else:
            st.info(f"ℹ️ {comp.rationale}")

    # Section promotion (toujours visible si ≥1 variante non-canonique)
    promotable = [v for v in variants if not v.is_canonical]
    if promotable:
        st.divider()
        st.markdown("**Promouvoir une variante comme canonique**")
        st.caption(
            "⚠️ Cette action archive l'ancien canonique sous "
            "`<role>_archived_YYYYMMDD_HHMM.md` et renomme la variante en `<role>.md`. "
            "Action manuelle, pas d'auto-promote (cf. ADR-029)."
        )
        promo_cols = st.columns([3, 1])
        with promo_cols[0]:
            label_to_promote = st.selectbox(
                "Variante à promouvoir",
                options=[v.label for v in promotable],
                key=f"promote_select_{selected_role}",
            )
        with promo_cols[1]:
            confirm_promote = st.button(
                "✅ Promouvoir",
                type="primary",
                use_container_width=True,
                key=f"promote_btn_{selected_role}",
            )
        if confirm_promote:
            try:
                new_canonical = ab.promote_variant(canonical_path, label_to_promote)
                st.success(
                    f"✅ `{label_to_promote}` est maintenant le canonique de "
                    f"`{selected_role}`. Ancien archivé à côté.\n\n"
                    f"Path : `{new_canonical}`"
                )
                st.balloons()
                st.caption("Rafraîchis la page pour voir l'état mis à jour.")
            except (ValueError, FileNotFoundError, OSError) as exc:
                st.error(f"Promotion échouée : {type(exc).__name__}: {exc}")
