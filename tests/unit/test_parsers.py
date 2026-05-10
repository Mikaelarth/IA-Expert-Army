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
