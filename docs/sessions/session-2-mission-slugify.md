# Session 2 — Première mission réelle Ollama 32B (slugify)

**Date** : 2026-05-20
**Branche** : `feat/ollama-backend`
**Mission ID** : `b9ac9449-7c1e-48e8-b1e6-aa1f138c723e`
**Stack** : Ollama local, mapping ADR-025 par défaut

| Tier | Modèle |
|---|---|
| `model_strategic` | `qwen2.5:32b` (19 GB) |
| `model_operational` | `qwen2.5-coder:32b` (19 GB) |
| `model_bulk` | `qwen2.5:14b` (9 GB) |

---

## Objectif

Première validation empirique de la chaîne complète post-bascule Anthropic →
Ollama (ADR-025). Mission engineering simple choisie pour disposer d'une
**baseline Claude/Sonnet directement comparable** : le `slugify` est la
mission canon du smoke E2E (`tests/integration/test_smoke_autonomous.py`),
exécutée à de multiples reprises sur Claude avec verdict APPROVED ~0.94.

## Mission

```yaml
title: Crée la fonction slugify utilitaire
description: |
  Implémente une fonction Python slugify(text: str) -> str qui produit un
  slug url-safe à partir d'un texte arbitraire. Pas de dépendance externe
  (stdlib uniquement). Lowercase, accents retirés, non-alphanum → '-',
  dashes compactés, dashes de bord retirés. Tests pytest cas canoniques +
  edge cases.
guild: engineering (auto-routé)
cible: src/utils/text.py + tests/unit/test_text.py
```

## Résultats globaux

| Métrique | Qwen2.5 32B (Ollama local) | Baseline Claude/Sonnet | Delta |
|---|---|---|---|
| **Verdict** | APPROVED | APPROVED | = |
| **Quality score** | **0.93** | 0.94 (canon smoke) | -0.01 |
| **Durée totale** | **1270.68 s (21 min 11 s)** | ~12 min (ADR-015 estimation Sprint DDD) | **× 1.8** |
| **Coût USD** | **$0.00** | ~$0.50 | **-100 %** |
| **Fichiers produits** | 2 (src/utils/text.py, tests/unit/test_text.py) | 2 (idem) | = |
| **Repair loop déclenché** | Non (APPROVED 1ʳᵉ passe) | Non | = |

## Détail par agent (chaîne séquentielle Engineering)

| Agent | Modèle | Durée | Tokens in | Tokens out | stop_reason | Saturé |
|---|---|---|---|---|---|---|
| ChiefOrchestrator | `qwen2.5:32b` | 272.77 s | 1 849 | 393 | stop | non |
| SoftwareArchitect | `qwen2.5:32b` | 389.01 s | 2 227 | 571 | stop | non |
| BackendDeveloper | `qwen2.5-coder:32b` | 358.80 s | 2 205 | 515 | stop | non |
| CodeReviewer | `qwen2.5-coder:32b` | 245.21 s | 2 895 | 341 | stop | non |
| **Total** | — | **1 265.79 s** (workflow= 1 270.68 s) | 9 176 | 1 820 | — | 0 saturation |

**Throughput observé** : ~1.4 token/s en moyenne sur les modèles 32B (CPU sans
GPU dédié). Variable selon agent : Developer plus rapide (~1.4 tok/s sur code),
Architect plus lent (~1.5 tok/s mais plus de raisonnement).

## RAG + skills correctement appliqués

À chaque appel, le `BaseAgent` a bien :
- Injecté **2 précédents pertinents** depuis VectorMemory (238 épisodes
  indexés au démarrage)
- Injecté **1 skill auto-extraite** depuis SkillsLibrary (16 skills disponibles)

Exemple pour `chief_orchestrator` : skill `Décomposition YAML missions endpoint FastAPI` injectée. Pour `backend_developer` : skill `FastAPI router with isolated testing via ASGITransport` injectée — bien que la mission slugify n'utilise pas FastAPI, les précédents/skills disponibles étaient FastAPI-centric (legacy Claude). C'est attendu et OK : la boucle RAG fonctionne correctement, le contenu des skills est juste le reflet de l'historique pré-bascule.

## Qualité du code produit

### `src/utils/text.py` (537 octets, 19 lignes)

```python
import re
import unicodedata

def slugify(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r'[^a-z0-9]', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')
```

**Évaluation** : code idiomatique, correct, minimal. Pipeline propre.
**Manque** vs baseline Claude :
- Pas de docstring (Claude en met systématiquement)
- Pas de `from __future__ import annotations`
- Pas de doctests embedded

Pas bloquant — code fonctionnel.

### `tests/unit/test_text.py` (437 octets, 18 lignes)

5 tests générés. **4 passent, 1 bugué** :

```python
def test_slugify_multiple_punctuation():
    assert slugify("!@#$%^&*().,?/") == "-"   # ❌ devrait être ""
```

**Analyse** :
- Le code `slugify` fait `.strip('-')` en dernier → une entrée 100% non-alphanumérique produit `""`, pas `"-"`
- Qwen-Reviewer (qwen2.5-coder:32b) a donné APPROVED 0.93 **sans détecter ce bug** — il n'a pas fait l'exécution mentale du test
- C'est le finding empirique principal de Session 2

**Correctif appliqué** : `assert ... == ""` (commentaire référence ce rapport).

## Finding empirique : Qwen-Reviewer < Claude-Reviewer sur l'exécution mentale

Le `code_reviewer` sur **claude-sonnet-4-6** (baseline historique) catche ce
type de bug dans ~90 % des cas observés. Le même rôle sur **qwen2.5-coder:32b**
l'a laissé passer en première passe avec un score 0.93. Hypothèses :

1. Le prompt du `code_reviewer` (`prompts/guilds/engineering/code_reviewer.md`)
   demande implicitement la vérification — mais qwen2.5-coder:32b ne fait pas
   spontanément l'exécution mentale.
2. La skill injectée (`Revue structurée FastAPI avec verdict gradué`) est
   focalisée sur la structure et le scoring, pas sur la trace symbolique.

**Action Vague 2** (à tracer) : améliorer `prompts/guilds/engineering/code_reviewer.md`
avec une instruction explicite *"Pour chaque assertion d'un test, exécute mentalement
la fonction sur l'input et compare avec l'output attendu"*. Re-tester sur slugify
pour valider le gain.

## Vs estimations ADR-025

| Prédiction ADR-025 | Réalité Session 2 |
|---|---|
| "Mission étalon attendue à 25-40 min" | **21 min** — meilleur que prédit |
| "Qualité dégradée sur QG/BA" | QG/BA non sollicités sur cette mission (single-guild simple) — à valider Session 3+ |
| "Code Developer : bon, jugement subtil dégradé" | Code idiomatique ✓, jugement reviewer manqué un test bugué ✓ |
| "Saturation possible sur prompts complexes" | 0 saturation sur cette mission (tokens out 341-571, max 8192-16384) |
| "Coût $0" | $0 confirmé |

## Garde-fous vérifiés

- ✅ **BudgetController** correctement no-op quand `daily_budget_usd=0` (après fix bug introduit Session 1)
- ✅ **Killswitch** : non engagé, mission passe
- ✅ **apply_files** : 2 fichiers écrits sans rejet (chemins whitelist OK, pas de path traversal)
- ✅ **Saturation detection** : 0 saturation, tous `stop_reason="stop"` (correctement mappé depuis OpenAI vs Anthropic `end_turn`)
- ❌ **Validation sandbox** : non testée cette session (Docker tournait mais on n'a pas lancé `--validate` pour rester court). À couvrir Session 3.

## Conclusion Session 2

**La bascule Anthropic → Ollama (ADR-025) est fonctionnellement validée.**

| Critère | Verdict |
|---|---|
| La chaîne d'agents tourne end-to-end | ✅ |
| Verdict APPROVED atteint en 1 passe | ✅ |
| Score qualité proche baseline (0.93 vs 0.94) | ✅ |
| Fichiers écrits correctement | ✅ |
| RAG + skills auto-injectées | ✅ |
| Pas de saturation | ✅ |
| Coût $0 | ✅ |
| Code généré correct | ✅ |
| Tests générés tous corrects | ❌ (1/5 bugué) |
| Reviewer catche le bug du test | ❌ |

**Score session : 8/10**. Le projet est utilisable pour des missions simples en
production perso. Restent 2 défauts identifiés (Reviewer plus laxiste, tests
parfois buggy) — adressables Vague 2 via prompt engineering.

## Prochaines étapes

- **Session 3** : nettoyer `docs/architecture.md` des 8 agents fictifs + 4 MCP fictifs (Vague 1 du contrat 7 critères, critère 1)
- **Session 4** : amélioration prompt `code_reviewer.md` (instruction exécution mentale) puis re-test slugify pour vérifier le gain
- **Session 5** : validation sandbox `--validate` sur une mission engineering
- **Session 6** : 2-3 missions supplémentaires (Research, Creative, Business) pour échantillonner les 4 guildes sur Ollama
