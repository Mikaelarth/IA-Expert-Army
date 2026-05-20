import pytest
from src.utils.text import slugify

def test_slugify_normal():
    assert slugify("Hello World") == "hello-world"

def test_slugify_accents():
    assert slugify("Café à Paris") == "cafe-a-paris"

def test_slugify_empty_string():
    assert slugify("") == ""

def test_slugify_multiple_punctuation():
    # Correction post-mission Session 2 : Qwen-Reviewer avait laissé passer
    # un test bugué qui attendait "-", mais .strip('-') produit "" sur une
    # entrée 100% non-alphanumérique. Finding documenté dans
    # docs/sessions/session-2-mission-slugify.md (limite Qwen32B-Reviewer
    # vs Claude-Sonnet : pas d'exécution mentale des tests).
    assert slugify("!@#$%^&*().,?/") == ""

def test_slugify_multiple_spaces():
    assert slugify("a     b") == "a-b"
