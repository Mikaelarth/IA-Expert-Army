"""Smoke tests GUI Streamlit — chaque page render sans exception (ADR-026).

Utilise `streamlit.testing.AppTest` qui exécute l'app en mode test (sans
serveur HTTP) et expose les exceptions levées pendant le render.

Ces tests sont volontairement SIMPLES : ils valident que chaque page se
charge, lit sa data depuis le disque sans crash, et expose au moins un
widget. Ils ne testent pas l'interactivité (form submission → lancement
mission), parce que ça déclencherait un vrai appel Ollama de 20-40 min.

Skip si streamlit n'est pas installé (groupe optional `gui`, cf. ADR-026).
"""

from __future__ import annotations

from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip(
    "streamlit.testing.v1",
    reason="streamlit non installé — exécuter `uv sync --group gui` pour tester la GUI",
)


_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _ensure_minimal_data_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pré-crée la structure data/memory minimale pour que les pages chargent.

    Ne touche PAS aux vraies données du repo — on monkeypatche get_settings
    pour pointer sur tmp_path (chaque test isolé).

    On laisse get_settings tel quel par défaut : les pages chargent depuis
    le vrai data/ qui peut contenir les artefacts des sessions précédentes.
    C'est OK : on veut justement vérifier que les vraies données rendent
    sans crash. Le fixture est conservé en placeholder pour si un test
    futur veut isoler.
    """


def test_page_explainability_renders() -> None:
    """La page Explainability (v0.9.0 C1) se charge avec ses 3 onglets."""
    page = _ROOT / "src" / "gui" / "pages" / "6_🔍_Explainability.py"
    at = streamlit_testing.AppTest.from_file(str(page))
    at.run(timeout=20)
    assert not at.exception, f"Page Explainability a planté : {at.exception}"
    # 3 tabs présents
    assert len(at.tabs) >= 3, f"Attendu ≥3 tabs, trouvé {len(at.tabs)}"


def test_page_setup_renders() -> None:
    """La page Setup (ADR-027) se charge même sans Ollama/Docker.

    detect_all() est wrappé par _safe() côté setup_runner : il ne doit JAMAIS
    lever, donc la page render même sur une machine vierge.
    """
    page = _ROOT / "src" / "gui" / "pages" / "0_🛠_Setup.py"
    at = streamlit_testing.AppTest.from_file(str(page))
    at.run(timeout=20)
    assert not at.exception, f"Page Setup a planté : {at.exception}"
    # 5 metrics dans le header (OK / MISSING / STOPPED / SKIPPED / Bloquant)
    assert len(at.metric) >= 5, f"Attendu ≥5 metrics, trouvé {len(at.metric)}"
    metric_labels = [m.label for m in at.metric]
    assert any("OK" in lbl for lbl in metric_labels)
    assert any("MISSING" in lbl for lbl in metric_labels)
    assert any("Bloquant" in lbl for lbl in metric_labels)


def test_app_home_renders() -> None:
    """La page d'accueil se charge sans exception."""
    at = streamlit_testing.AppTest.from_file(str(_ROOT / "src" / "gui" / "app.py"))
    at.run(timeout=20)
    assert not at.exception, f"App home a planté : {at.exception}"
    # Présence de la metric "Missions archivées" (composant central de l'accueil)
    titles = [m.label for m in at.metric]
    assert any("Missions archivées" in t for t in titles), (
        f"Metric 'Missions archivées' manquante. Metrics présentes : {titles}"
    )


def test_page_mission_renders() -> None:
    """La page Mission (formulaire) se charge sans exception."""
    page = _ROOT / "src" / "gui" / "pages" / "1_🚀_Mission.py"
    at = streamlit_testing.AppTest.from_file(str(page))
    at.run(timeout=20)
    assert not at.exception, f"Page Mission a planté : {at.exception}"
    # Le formulaire contient au moins un text_input et un text_area
    assert len(at.text_input) >= 1, "Pas de text_input sur la page Mission"
    assert len(at.text_area) >= 1, "Pas de text_area sur la page Mission"
    # Au moins un bouton (le submit du form est listé dans at.button en Streamlit v1)
    assert len(at.button) >= 1, "Pas de bouton sur la page Mission"
    # 3 checkboxes attendues : --apply, --validate, --force
    assert len(at.checkbox) >= 3, f"Attendu ≥3 checkboxes, trouvé {len(at.checkbox)}"
    # 1 selectbox pour la guilde
    assert len(at.selectbox) >= 1, "Pas de selectbox guilde"


def test_page_historique_renders() -> None:
    """La page Historique se charge même si zéro mission archivée."""
    page = _ROOT / "src" / "gui" / "pages" / "2_📜_Historique.py"
    at = streamlit_testing.AppTest.from_file(str(page))
    at.run(timeout=20)
    assert not at.exception, f"Page Historique a planté : {at.exception}"
    # Au moins une metric (Total) doit être présente
    assert len(at.metric) >= 1, "Pas de metric sur la page Historique"


def test_page_skills_renders() -> None:
    """La page Skills se charge même si zéro skill."""
    page = _ROOT / "src" / "gui" / "pages" / "3_🧠_Skills.py"
    at = streamlit_testing.AppTest.from_file(str(page))
    at.run(timeout=20)
    assert not at.exception, f"Page Skills a planté : {at.exception}"


def test_page_health_renders() -> None:
    """La page Health se charge sans lancer le check (juste l'UI)."""
    page = _ROOT / "src" / "gui" / "pages" / "4_🏥_Health.py"
    at = streamlit_testing.AppTest.from_file(str(page))
    at.run(timeout=20)
    assert not at.exception, f"Page Health a planté : {at.exception}"
    # Bouton "Lancer health check" présent mais on ne le clique pas
    button_labels = [b.label for b in at.button]
    assert any("Lancer health check" in lbl for lbl in button_labels), (
        f"Bouton 'Lancer health check' manquant. Buttons : {button_labels}"
    )


def test_page_probes_renders() -> None:
    """La page Probes se charge avec ses 2 tabs (Reviewer + Sandbox)."""
    page = _ROOT / "src" / "gui" / "pages" / "5_🔬_Probes.py"
    at = streamlit_testing.AppTest.from_file(str(page))
    at.run(timeout=20)
    assert not at.exception, f"Page Probes a planté : {at.exception}"
    # 2 boutons primaires (lancer reviewer + lancer sandbox)
    assert len(at.button) >= 2, f"Attendu ≥2 boutons (Reviewer + Sandbox), trouvé {len(at.button)}"


def test_memory_browser_list_missions_returns_iterable() -> None:
    """Sanity check du service partagé : list_missions ne crash pas sur le repo réel."""
    from src.gui.services.memory_browser import list_missions, stats

    missions = list_missions()
    assert isinstance(missions, list)
    # Si missions existent, agg stats doit aussi marcher
    agg = stats(missions)
    assert "total" in agg
    assert agg["total"] == len(missions)


def test_memory_browser_list_skills_returns_dict() -> None:
    """Sanity check : list_skills retourne dict[agent → list[SkillSummary]]."""
    from src.gui.services.memory_browser import list_skills

    skills = list_skills()
    assert isinstance(skills, dict)
    # Si présent, chaque valeur doit être une liste
    for agent, items in skills.items():
        assert isinstance(agent, str)
        assert isinstance(items, list)


def test_health_runner_captures_output_via_clirunner() -> None:
    """Sanity check du service health_runner (v0.5.1) : run_health(quick=True)
    doit retourner exit_code=0 et stdout non-vide.

    Régression : avant le fix v0.5.1, subprocess capture_output sur Windows
    retournait stdout='' silencieusement (rich.Console + sys.stdout.reconfigure()
    sur pipe non-TTY). La version CliRunner capture via StringIO en mémoire,
    ce qui élimine ce problème — ce test confirme que la sortie est bien
    récupérée (peu importe le contenu, on veut juste len > 0).
    """
    from src.gui.services.health_runner import run_health

    result = run_health(quick=True)
    assert result.exit_code == 0, (
        f"health_check --quick devrait retourner exit 0, got {result.exit_code}. "
        f"Stdout : {result.stdout[:500]}"
    )
    assert len(result.stdout) > 100, (
        f"Sortie capturée trop courte ({len(result.stdout)} chars) — "
        f"la régression Windows subprocess est revenue ? Stdout : {result.stdout!r}"
    )
    # Le tableau health check contient typiquement "Python" + "Settings" + "OK"
    assert "OK" in result.stdout or "FAIL" in result.stdout or "WARN" in result.stdout, (
        f"Sortie ne contient aucun marqueur OK/FAIL/WARN : {result.stdout[:200]}"
    )
    assert result.duration_seconds > 0
