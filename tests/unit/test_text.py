"""Tests pour src.utils.text.slugify (généré Session 4 + corrections manuelles).

Corrections post-mission Session 4 (cf. docs/sessions/session-4-prompt-improvement.md) :
- Fichier déplacé de src/utils/test_text.py vers tests/unit/test_text.py
  (spec mission précisait tests/unit/, Reviewer n'a pas catché).
- `import pytest` retiré (jamais utilisé, ruff F401).
- Ajout du test ponctuation-seule pour ancrer le cas Session 2 (qui avait
  révélé le finding empirique sur la review).
"""

from src.utils.text import slugify


def test_hello_world() -> None:
    assert slugify("Hello World") == "hello-world"


def test_cafe_a_paris() -> None:
    assert slugify("Café à Paris") == "cafe-a-paris"


def test_empty_string() -> None:
    assert slugify("") == ""


def test_multiple_punctuation_and_spaces() -> None:
    assert slugify("?? Hello   World !") == "hello-world"


def test_punctuation_only_yields_empty() -> None:
    """Cas Session 2 : `.strip('-')` produit "" sur entrée 100 % non-alphanum.
    Test ajouté manuellement pour ancrer le comportement vérifié à la main."""
    assert slugify("!@#$%^&*().,?/") == ""
