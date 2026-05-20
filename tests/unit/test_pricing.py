"""Tests pour src.core.pricing (bascule Ollama, ADR-025).

Le backend tourne en local : tous les coûts sont structurellement 0.
La signature `estimate_cost(model, tokens_in, tokens_out)` est conservée
pour compatibilité avec BaseAgent + BudgetController.
"""

from __future__ import annotations

from src.core.pricing import estimate_cost, lookup_pricing


def test_lookup_pricing_returns_zero_tariff() -> None:
    """Le fallback Ollama-local renvoie un tarif 0/0 quel que soit le modèle."""
    p = lookup_pricing("qwen2.5:32b")
    assert p.input_per_mtok == 0.0
    assert p.output_per_mtok == 0.0
    assert p.name_prefix == "ollama-local"


def test_lookup_pricing_handles_unknown_models() -> None:
    """Un modèle exotique tombe sur le même fallback (pas de crash)."""
    p = lookup_pricing("some-random-model")
    assert p.input_per_mtok == 0.0
    assert p.output_per_mtok == 0.0


def test_estimate_cost_is_always_zero() -> None:
    """Quel que soit le volume de tokens, le coût est 0 en backend local."""
    assert estimate_cost("qwen2.5:32b", 1_000_000, 1_000_000) == 0.0
    assert estimate_cost("qwen2.5-coder:32b", 50_000, 25_000) == 0.0
    assert estimate_cost("llama3.3:70b", 1, 1) == 0.0


def test_estimate_cost_zero_tokens() -> None:
    assert estimate_cost("qwen2.5:32b", 0, 0) == 0.0
