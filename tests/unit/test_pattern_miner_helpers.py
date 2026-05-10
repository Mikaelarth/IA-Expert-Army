"""Tests pour les helpers statiques de PatternMiner (pas d'I/O Claude)."""
from __future__ import annotations

from src.learning.pattern_miner import PatternMiner


def test_strip_outer_fence_removes_yaml_wrapper() -> None:
    text = "```yaml\ntitle: foo\nkey: value\n```"
    assert PatternMiner._strip_outer_fence(text) == "title: foo\nkey: value"


def test_strip_outer_fence_removes_plain_wrapper() -> None:
    text = "```\nplain content\n```"
    assert PatternMiner._strip_outer_fence(text) == "plain content"


def test_strip_outer_fence_passthrough_when_no_fence() -> None:
    text = "title: foo\nkey: value"
    assert PatternMiner._strip_outer_fence(text) == "title: foo\nkey: value"


def test_strip_outer_fence_handles_trailing_whitespace() -> None:
    text = "  \n```yaml\nfoo: bar\n```\n  "
    assert PatternMiner._strip_outer_fence(text) == "foo: bar"


def test_strip_outer_fence_does_not_break_unbalanced() -> None:
    text = "```yaml\nfoo: bar"  # pas de fence fermante
    assert PatternMiner._strip_outer_fence(text) == text.strip()
