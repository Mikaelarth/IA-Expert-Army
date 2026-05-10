"""Tests pour src.core.pricing."""
from __future__ import annotations

from src.core.pricing import estimate_cost, lookup_pricing


def test_lookup_pricing_for_opus() -> None:
    p = lookup_pricing("claude-opus-4-7")
    assert p.input_per_mtok == 15.00
    assert p.output_per_mtok == 75.00


def test_lookup_pricing_for_sonnet() -> None:
    p = lookup_pricing("claude-sonnet-4-6")
    assert p.input_per_mtok == 3.00


def test_lookup_pricing_for_haiku() -> None:
    p = lookup_pricing("claude-haiku-4-5-20251001")
    assert p.input_per_mtok == 0.80


def test_lookup_pricing_falls_back_for_unknown() -> None:
    p = lookup_pricing("some-unknown-model")
    assert p.name_prefix == "unknown"


def test_estimate_cost_for_opus_one_million_tokens() -> None:
    cost = estimate_cost("claude-opus-4-7", 1_000_000, 1_000_000)
    assert cost == 15.00 + 75.00


def test_estimate_cost_zero_tokens() -> None:
    assert estimate_cost("claude-opus-4-7", 0, 0) == 0.0
