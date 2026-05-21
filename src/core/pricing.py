"""Pricing — calcul du coût d'un appel LLM.

Bascule v0.4.0 (ADR-025) : le backend tourne sur Ollama local, donc le
coût USD par appel est structurellement 0. On garde la fonction
`estimate_cost(model, tokens_in, tokens_out)` pour compatibilité avec
l'interface BaseAgent (signature inchangée) et pour autoriser un retour
à un backend payant sans toucher au wiring.

Si tu veux re-câbler un cap budgétaire (ex. proxy d'un cap GPU
temps/tokens, ou bascule cloud), édite `lookup_pricing` pour mapper
les modèles vers un tarif effectif.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    name_prefix: str
    input_per_mtok: float
    output_per_mtok: float


# Tarifs explicitement à 0 : Ollama tourne en local, pas de facturation
# par token. Garder la structure permet de re-réactiver un pricing par
# modèle (ex. mix local + cloud) sans toucher au reste du code.
_PRICING: tuple[ModelPricing, ...] = ()
_FALLBACK = ModelPricing("ollama-local", 0.0, 0.0)


def lookup_pricing(model: str) -> ModelPricing:
    for p in _PRICING:
        if model.startswith(p.name_prefix):
            return p
    return _FALLBACK


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    p = lookup_pricing(model)
    return (tokens_in / 1_000_000) * p.input_per_mtok + (tokens_out / 1_000_000) * p.output_per_mtok
