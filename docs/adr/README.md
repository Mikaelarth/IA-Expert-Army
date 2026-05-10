# Architecture Decision Records

Chaque ADR documente **une décision structurante** prise pour IA-Expert-Army.

Format minimal :

```markdown
# ADR-NNNN — Titre

**Statut :** Proposed | Accepted | Superseded by ADR-XXX | Deprecated
**Date :** YYYY-MM-DD

## Contexte
<problème/contrainte/forces qui ont mené à la décision>

## Décision
<la décision prise, en termes affirmatifs>

## Conséquences
<positives + négatives + à surveiller>

## Alternatives considérées
<options écartées et pourquoi>
```

## Index

- [ADR-001 — Architecture en 4 couches](001-four-layer-architecture.md)
- [ADR-002 — Stack technique : Python + Claude Agent SDK + Chroma + Docker](002-tech-stack.md)
- [ADR-003 — Mode opérationnel : autonome avec garde-fous obligatoires](003-autonomy-with-guardrails.md)
- [ADR-004 — Stratégie d'apprentissage : RAG + skills synthétisées, pas de fine-tuning](004-learning-strategy.md)
- [ADR-005 — Détection et prévention de la saturation max_tokens](005-saturation-detection-and-prevention.md)
- [ADR-006 — Stratégie de mining et critères d'éligibilité des épisodes](006-mining-strategy-and-eligibility.md)
- [ADR-007 — Stratégie d'A/B testing automatique des prompts versionnés](007-prompt-ab-testing-strategy.md) (Proposed)
- [ADR-008 — Sandbox : trade-off `read_only=False` accepté](008-sandbox-readonly-tradeoff.md)
