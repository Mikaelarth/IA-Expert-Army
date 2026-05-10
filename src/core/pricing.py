"""Pricing — calcul du coût d'un appel Claude.

Tarifs par million de tokens (USD). À actualiser depuis https://www.anthropic.com/pricing.
Dernière mise à jour : 2026-05-10 (estimations).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    name_prefix: str
    input_per_mtok: float
    output_per_mtok: float


_PRICING: tuple[ModelPricing, ...] = (
    ModelPricing("claude-opus-4", 15.00, 75.00),
    ModelPricing("claude-sonnet-4", 3.00, 15.00),
    ModelPricing("claude-haiku-4", 0.80, 4.00),
)
_FALLBACK = ModelPricing("unknown", 5.00, 25.00)


def lookup_pricing(model: str) -> ModelPricing:
    for p in _PRICING:
        if model.startswith(p.name_prefix):
            return p
    return _FALLBACK


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    p = lookup_pricing(model)
    return (tokens_in / 1_000_000) * p.input_per_mtok + (tokens_out / 1_000_000) * p.output_per_mtok
