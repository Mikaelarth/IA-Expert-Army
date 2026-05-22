"""Tests v0.8.0 F3 — templates_browser service.

Valide :
- list_templates() charge tous les .md valides du dossier templates/missions/.
- get_template(id) retourne le bon template par id.
- render_template(tpl, params) interpole correctement Jinja2.
- StrictUndefined lève une ValueError si un paramètre est manquant.
- Templates malformés (YAML cassé, frontmatter absent) sont skippés
  silencieusement.
- Les 5 templates pré-livrés se chargent tous correctement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.gui.services import templates_browser as tb


@pytest.fixture
def tmp_templates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige `_templates_dir()` vers tmp_path (test isolé du repo réel)."""
    target = tmp_path / "templates" / "missions"
    target.mkdir(parents=True)
    monkeypatch.setattr(tb, "_templates_dir", lambda: target)
    return target


# ----------------------------------------------------------------------------
# list / get
# ----------------------------------------------------------------------------


def test_list_templates_empty_when_dir_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Si le dossier n'existe pas, list_templates() retourne []."""
    monkeypatch.setattr(tb, "_templates_dir", lambda: tmp_path / "absent")
    assert tb.list_templates() == []


def test_list_templates_loads_valid_md(tmp_templates: Path) -> None:
    (tmp_templates / "alpha.md").write_text(
        "---\nid: alpha\nname: Template Alpha\ndescription: Test\n---\nBody alpha {{ x }}",
        encoding="utf-8",
    )
    (tmp_templates / "beta.md").write_text(
        "---\nid: beta\nname: Template Beta\n---\nBody beta\n",
        encoding="utf-8",
    )

    templates = tb.list_templates()
    assert len(templates) == 2
    # Tri par name
    assert templates[0].name == "Template Alpha"
    assert templates[1].name == "Template Beta"


def test_list_templates_skips_malformed_files(tmp_templates: Path) -> None:
    """Un YAML cassé, un fichier sans frontmatter, et un fichier sans id/name
    doivent être skippés sans crash."""
    (tmp_templates / "ok.md").write_text("---\nid: ok\nname: OK\n---\nbody\n", encoding="utf-8")
    (tmp_templates / "no_frontmatter.md").write_text("Pas de frontmatter\n", encoding="utf-8")
    (tmp_templates / "missing_id.md").write_text("---\nname: NoId\n---\nbody\n", encoding="utf-8")
    (tmp_templates / "broken_yaml.md").write_text(
        "---\nid: x\nname: : : invalid\n---\nbody\n", encoding="utf-8"
    )

    templates = tb.list_templates()
    assert len(templates) == 1
    assert templates[0].id == "ok"


def test_get_template_returns_match(tmp_templates: Path) -> None:
    (tmp_templates / "x.md").write_text(
        "---\nid: target\nname: Target\n---\nbody\n", encoding="utf-8"
    )
    tpl = tb.get_template("target")
    assert tpl is not None
    assert tpl.id == "target"


def test_get_template_returns_none_when_absent(tmp_templates: Path) -> None:
    assert tb.get_template("nonexistent") is None


# ----------------------------------------------------------------------------
# render
# ----------------------------------------------------------------------------


def test_render_template_substitutes_placeholders(tmp_templates: Path) -> None:
    (tmp_templates / "tpl.md").write_text(
        "---\n"
        "id: tpl\n"
        "name: T\n"
        "params:\n"
        "  - name: entity\n"
        "    label: Entity\n"
        "---\n"
        "Hello {{ entity }} world",
        encoding="utf-8",
    )
    tpl = tb.get_template("tpl")
    assert tpl is not None
    out = tb.render_template(tpl, {"entity": "Product"})
    assert out == "Hello Product world"


def test_render_template_raises_on_missing_param(tmp_templates: Path) -> None:
    """StrictUndefined : un paramètre attendu mais non fourni doit lever
    ValueError avec un message clair (mieux qu'un placeholder vide silencieux)."""
    (tmp_templates / "tpl.md").write_text(
        "---\nid: tpl\nname: T\n---\nHello {{ missing }} world",
        encoding="utf-8",
    )
    tpl = tb.get_template("tpl")
    assert tpl is not None
    with pytest.raises(ValueError, match="missing"):
        tb.render_template(tpl, {})


def test_render_template_supports_default_filter(tmp_templates: Path) -> None:
    """Le filtre Jinja `default` permet des valeurs optionnelles."""
    (tmp_templates / "tpl.md").write_text(
        "---\nid: tpl\nname: T\n---\nHello {{ name | default('Anonymous') }}",
        encoding="utf-8",
    )
    tpl = tb.get_template("tpl")
    assert tpl is not None
    assert tb.render_template(tpl, {}).endswith("Anonymous")
    assert tb.render_template(tpl, {"name": "Alice"}).endswith("Alice")


def test_render_template_supports_lower_filter(tmp_templates: Path) -> None:
    (tmp_templates / "tpl.md").write_text(
        "---\nid: tpl\nname: T\n---\n{{ entity_name.lower() }}s",
        encoding="utf-8",
    )
    tpl = tb.get_template("tpl")
    assert tpl is not None
    assert tb.render_template(tpl, {"entity_name": "Product"}) == "products"


# ----------------------------------------------------------------------------
# Templates pré-livrés v0.8.0
# ----------------------------------------------------------------------------


def test_all_prebundled_templates_load_correctly() -> None:
    """Vérifie que les 5 templates livrés avec v0.8.0 se chargent sans erreur
    et exposent tous les champs attendus (id, name, params, body)."""
    templates = tb.list_templates()
    ids = {t.id for t in templates}
    expected = {
        "fastapi-crud-endpoint",
        "refactor-module",
        "audit-owasp-module",
        "stdlib-utility-function",
        "landing-page-saas",
    }
    assert expected.issubset(ids), f"Templates manquants : {expected - ids}"

    for tpl in templates:
        if tpl.id not in expected:
            continue
        assert tpl.name, f"Template {tpl.id} sans name"
        assert tpl.guild in {"engineering", "research", "creative", "business", ""}
        assert tpl.body_jinja.strip(), f"Template {tpl.id} avec body vide"
        for p in tpl.params:
            assert p.name and p.label, f"Param mal formé dans {tpl.id}: {p}"


def test_fastapi_crud_template_renders_with_sample_params() -> None:
    """Smoke test E2E : le template FastAPI CRUD doit pouvoir être rendu
    avec des paramètres canon sans erreur."""
    tpl = tb.get_template("fastapi-crud-endpoint")
    assert tpl is not None
    rendered = tb.render_template(
        tpl,
        {
            "entity_name": "Product",
            "fields": "name:str, price:float",
            "file_target": "api/products.py",
        },
    )
    assert "Product" in rendered
    assert "name:str, price:float" in rendered
    assert "api/products.py" in rendered
    # Le filtre .lower() doit avoir produit "products"
    assert "products" in rendered
