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
