# ADR-021 — Smoke tests E2E avec FakeAsyncAnthropic (sans coût API)

**Statut :** Accepted
**Date :** 2026-05-15
**Commits associés :** Sprint OOO

## Contexte

Avant Sprint OOO, le projet avait :
- **Tests unitaires par agent** (`test_base_agent.py`, `test_research_agents.py`, etc.) — vérifient qu'un agent isolé tourne avec un client mocké.
- **Tests unitaires par workflow** (`test_workflow_repair.py`, `test_workflow_guardrails.py`) — vérifient les invariants logiques des workflows.

**Mais aucun test ne validait que la chaîne COMPLÈTE tourne sans crash** :
```
Router → décision routing → Workflow → 4 agents enchaînés → archivage → digest
```

Conséquence : une régression silencieuse au niveau du Router (mauvais routing), du Workflow (cassure entre 2 étapes), ou de l'archivage (mission jamais persistée) ne se voyait qu'au moment de **lancer une vraie mission** — donc en payant l'API Anthropic.

Pour le mode autonome 24/7 sur VPS, c'est inacceptable : un bug introduit par une PR pouvait tuer une queue de missions et coûter $5-20 avant qu'on s'en aperçoive.

## Décision

### `tests/integration/test_smoke_autonomous.py`

11 tests E2E qui exécutent **la chaîne complète** sur des missions canon :

1. **`test_engineering_workflow_smoke_e2e`** — mission "Crée slugify utilitaire"
   - Vérifie : 4 agents tournent, verdict APPROVED, 2 fichiers extraits, code contient `def slugify`, 4 épisodes archivés, mission persistée dans `data/memory/missions/`
2. **`test_research_workflow_smoke_e2e`** — mission "Pydantic v1 vs v2"
   - Vérifie : ResearchLead → TechWatch → DocumentSynthesizer → ResearchReviewer, verdict APPROVED, synthesis_markdown contient les sections attendues
3. **`test_router_dispatches_engineering_correctly`** — mission "Endpoint FastAPI /ping"
   - Vérifie : routage automatique heuristique → guilde Engineering, mission complète APPROVED
4. **`test_router_force_guild_overrides_classifier`** — mission "Pydantic v2"
   - Vérifie : `force_guild='research'` gagne sur le classifier
5. **6 tests `test_detect_agent_name`** (parametrize) — garantit que la détection d'agent par H1 est stable (notamment face aux cross-références dans les prompts).

### `FakeAsyncAnthropic` (drop-in replacement)

Implémente l'interface minimum `messages.create(model, max_tokens, system, messages) -> Response` :
- Détecte l'agent appelant via le **H1 du system prompt** (`# Code Reviewer — System Prompt`)
- Renvoie une réponse canon depuis `CANON_RESPONSES` dict
- Format compatible : `.content[i].text`, `.usage.input_tokens/output_tokens`, `.stop_reason`

### Réponses canon

Stockées en constants module-level (`_CHIEF_ORCHESTRATOR_YAML`, `_BACKEND_DEVELOPER_MD`, etc.). Format réaliste **copié-collé du pattern observé** sur de vraies missions APPROVED dans `data/memory/missions/`. Pas inventées — réplication de YAML / markdown qui passent les parsers tolérants existants.

### Patching technique

```python
monkeypatch.setattr(
    "src.orchestrator.base_agent.AsyncAnthropic",
    FakeAsyncAnthropic,
)
```

`base_agent.py` est le **seul endroit** qui instancie un client par défaut quand `client=None`. Patcher là couvre tous les agents (architect, developer, reviewer, etc.) sans toucher à leurs constructeurs.

### Détection robuste de l'agent (par H1, pas par mots-clés)

**Bug initial découvert pendant Sprint OOO** : la première implémentation cherchait des mots-clés en lowercase ("backend developer" in system_prompt). Mais le prompt CodeReviewer contient "Backend Developer" en référence au rôle amont → fausse détection → réponse canon du Developer envoyée au CodeReviewer → verdict cassé.

**Fix** : matcher sur le H1 standard `# <Display Name> — System Prompt` (pattern utilisé partout dans `prompts/**/*.md`). Cette regex isole l'identité du prompt et ignore les cross-références dans le corps.

```python
_H1_RE = re.compile(r"^#\s+([^\n—-]+?)\s+[—-]\s+System Prompt", re.MULTILINE)
```

Test paramétré garantit que cette détection reste stable :
```python
@pytest.mark.parametrize("system,expected", [
    # ...
    ("# Code Reviewer — System Prompt\n\nTu juges le code "
     "produit par le Backend Developer.", "code_reviewer"),  # cas piège
])
def test_detect_agent_name(system, expected): ...
```

## Conséquences

**Positives** :
- **CI peut désormais tester la chaîne E2E à chaque PR sans dépenser un cent** (5s pour 11 tests)
- Une régression Router/Workflow/Archivage est détectée immédiatement (pas en prod)
- Les réponses canon servent de **documentation vivante** du format attendu par chaque parser
- Les missions de smoke documentent les "happy paths" connus (slugify, FastAPI /ping, etc.)
- Le harness `FakeAsyncAnthropic` est réutilisable pour de futurs tests E2E (ex: meta_workflow cross-guildes)

**Négatives** :
- Si on **change un system prompt** (renomme un agent, modifie le H1), le test peut casser. Mitigation : test paramétré explicite + détection robuste.
- Les réponses canon **simulent** des sorties Anthropic — elles ne reflètent pas les variations réelles du LLM. Un prompt qui change subtilement et fait diverger Sonnet ne sera pas détecté.
- Coverage gain marginal (+0.13 pts) car les workflows étaient déjà couverts par tests unitaires. **Le vrai gain est qualitatif** : on couvre désormais les *interactions* entre composants, pas juste leurs unités.

**À surveiller** :
- Quand on ajoute un nouvel agent (nouveau prompt), il faut MAJ `_DISPLAY_NAME_TO_AGENT` + `CANON_RESPONSES`. Sinon le smoke échoue avec "unknown agent". C'est un bon signal — force à documenter le nouveau format.
- Si `extract_yaml` ou `extract_files` change leur tolérance (ex: nouveau pattern accepté), revérifier que les réponses canon restent réalistes.

## Workflow d'évolution des canon

**Ajouter un nouvel agent** :
1. Créer son prompt dans `prompts/.../` avec H1 standard
2. Ajouter l'entrée dans `_DISPLAY_NAME_TO_AGENT`
3. Créer une constante `_<AGENT_NAME>_RESPONSE = """..."""` avec un format réaliste
4. Ajouter dans `CANON_RESPONSES`
5. Ajouter un test E2E qui exerce le workflow incluant ce nouvel agent

**Modifier un format de réponse attendu** (ex: ajouter un champ requis dans le YAML reviewer) :
1. MAJ le parser (`_parsers.py`)
2. MAJ la canon correspondante dans `test_smoke_autonomous.py`
3. Vérifier que les tests E2E passent toujours

## Alternatives considérées

1. **VCR.py / pytest-recording** : enregistrer de vraies réponses Anthropic la 1ère fois puis rejouer. Refusé : crée une dépendance à du contenu opaque, bytes-pour-bytes, et ne permet pas d'éditer facilement les réponses canon. Notre approche manuelle est plus didactique.

2. **Mock complet via `unittest.mock.patch` au lieu d'une classe** : refusé. Une classe `FakeAsyncAnthropic` est plus lisible et permet d'ajouter de la logique (détection d'agent, payloads dynamiques) sans transformer chaque test en setup verbeux.

3. **Tests E2E avec un vrai client Anthropic mais limit budget$0.01** : refusé. Coût toujours présent, dépendance réseau au CI, résultats variables entre runs.

4. **Snapshot testing pour les sorties** : pertinent mais ajoute une dépendance (`syrupy`) et complique la lecture des canons. Reporté tant qu'on a < 10 tests E2E.

## Sources

- ADR-019 (politique coverage) — Sprint OOO comble un trou de couverture **qualitative** (interactions) que l'audit JJJ ne mesurait pas
- ADR-020 (CI gate) — les smoke E2E tournent désormais dans le CI à chaque PR
- Pattern observé sur missions APPROVED réelles : `data/memory/missions/*.md` (50+ missions production, formats canoniques stables)
