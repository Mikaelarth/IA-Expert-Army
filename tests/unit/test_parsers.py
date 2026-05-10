"""Tests pour src.orchestrator.agents._parsers."""
from __future__ import annotations

from src.orchestrator.agents._parsers import extract_files, extract_yaml


def test_extract_yaml_from_fenced_block() -> None:
    text = """Voici la décomposition :

```yaml
mission_understanding: |
  refactor X
decomposition:
  - id: T1
    title: faire Y
estimated_cost_usd: 0.05
```

Voilà.
"""
    parsed = extract_yaml(text)
    assert parsed is not None
    assert parsed["mission_understanding"].strip() == "refactor X"
    assert parsed["decomposition"][0]["id"] == "T1"
    assert parsed["estimated_cost_usd"] == 0.05


def test_extract_yaml_from_raw_yaml_text() -> None:
    text = "key: value\nnested:\n  - a\n  - b\n"
    parsed = extract_yaml(text)
    assert parsed == {"key": "value", "nested": ["a", "b"]}


def test_extract_yaml_returns_none_on_invalid() -> None:
    text = "::: not yaml :::\n*&^%"
    assert extract_yaml(text) is None


def test_extract_yaml_recovers_list_items_with_unquoted_colon() -> None:
    """Régression : un LLM qui produit un item de liste contenant ' : ' non quoté
    fait échouer le parser strict. Le pré-traitement doit auto-quoter et permettre
    le parse. Bug observé en mining tech_watch (épisode aebf2a37).
    """
    text = """```yaml
title: Skill réutilisable
key_patterns:
  - Confidence calibrée systématiquement (high = docs ; medium = signaux)
  - Conditions de validité explicites : "payant pour X / contre-productif Y" au lieu de recommandations universelles
  - Sources croisées par finding
techniques:
  - Format YAML strict
```"""
    result = extract_yaml(text)
    assert result is not None, "Le parser tolérant doit récupérer ce YAML"
    assert result["title"] == "Skill réutilisable"
    assert len(result["key_patterns"]) == 3
    # L'item problématique est préservé (en string)
    assert "Conditions de validité explicites" in result["key_patterns"][1]


def test_extract_yaml_strict_parse_still_works() -> None:
    """Le parser tolérant ne doit PAS modifier les YAML déjà valides."""
    text = """```yaml
title: x
items:
  - "déjà quoté : avec deux-points"
  - simple item sans colon
```"""
    result = extract_yaml(text)
    assert result is not None
    assert result["items"][0] == "déjà quoté : avec deux-points"
    assert result["items"][1] == "simple item sans colon"


def test_extract_yaml_unrecoverable_returns_none() -> None:
    """Si même le pré-traitement ne suffit pas, on retourne None (pas de crash)."""
    text = "```yaml\n{{{{ totally broken\n```"
    assert extract_yaml(text) is None


def test_extract_yaml_regex_fallback_for_quotes_in_middle_of_item() -> None:
    """Cas pathologique : item de liste avec un quote AU MILIEU (pas en début).
    Le pré-traitement ne le détecte pas. Le fallback regex doit le sauver.
    Vrai cas observé en mining tech_watch (épisode aebf2a37, item « LLM-judge »).
    """
    text = """```yaml
title: Skill avec items pathologiques
summary: |
  Test du fallback regex
key_patterns:
  - "LLM-judge solves all" sans section méta-évaluation
  - autre item simple
techniques:
  - Structure YAML stricte : findings_by_subquestion → SQ_id → liste de findings → {finding, confidence}
```"""
    result = extract_yaml(text)
    assert result is not None, "Le fallback regex doit récupérer ce YAML"
    assert result["title"] == "Skill avec items pathologiques"
    assert "Test du fallback" in result["summary"]
    assert len(result["key_patterns"]) == 2


def test_extract_yaml_regex_fallback_requires_title() -> None:
    """Le fallback regex ne retourne quelque chose que si title est trouvé."""
    text = """```yaml
agent: tech_watch
{{{{ broken nested
```"""
    assert extract_yaml(text) is None


def test_extract_files_picks_up_path_and_code() -> None:
    text = """## Approche

Brève.

## Fichiers produits

### `src/foo.py`

```python
def hello():
    return 'world'
```

### `tests/test_foo.py`

```python
def test_hello():
    assert True
```

## Notes

- rien
"""
    files = extract_files(text)
    assert len(files) == 2
    assert files[0]["path"] == "src/foo.py"
    assert files[0]["language"] == "python"
    assert "def hello" in files[0]["content"]
    assert files[1]["path"] == "tests/test_foo.py"


def test_extract_files_empty_when_no_blocks() -> None:
    assert extract_files("just text, no fenced files") == []


def test_extract_files_handles_empty_code_blocks() -> None:
    """Régression : __init__.py vides ne doivent pas avaler le bloc suivant."""
    text = """## Fichiers produits

### `src/__init__.py`

```python
```

### `src/api/__init__.py`

```python
```

### `src/api/health.py`

```python
def health():
    return {"status": "ok"}
```
"""
    files = extract_files(text)
    assert len(files) == 3
    assert files[0]["path"] == "src/__init__.py"
    assert files[0]["content"] == ""
    assert files[1]["path"] == "src/api/__init__.py"
    assert files[1]["content"] == ""
    assert files[2]["path"] == "src/api/health.py"
    assert "def health" in files[2]["content"]


def test_extract_files_handles_paths_with_special_chars() -> None:
    text = """### `pyproject.toml (section à fusionner)`

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```
"""
    files = extract_files(text)
    assert len(files) == 1
    assert files[0]["path"] == "pyproject.toml (section à fusionner)"
    assert files[0]["language"] == "toml"
    assert "asyncio_mode" in files[0]["content"]


def test_extract_files_skips_unclosed_fences() -> None:
    text = """### `broken.py`

```python
def foo():
    pass
"""
    assert extract_files(text) == []


def test_extract_files_preserves_internal_blank_lines() -> None:
    text = """### `module.py`

```python
def a():
    pass


def b():
    pass
```
"""
    files = extract_files(text)
    assert len(files) == 1
    assert "def a" in files[0]["content"]
    assert "def b" in files[0]["content"]
    # La ligne vide entre a et b doit être préservée
    assert "\n\n\n" in files[0]["content"]
