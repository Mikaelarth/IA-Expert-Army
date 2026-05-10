# ADR-007 — Stratégie d'A/B testing automatique des prompts versionnés

**Statut :** Proposed
**Date :** 2026-05-10

## Contexte

ADR-004 a posé que l'apprentissage de l'équipe se fait par 3 mécanismes :
RAG sur épisodes, skills auto-générées, et **prompts versionnés Git avec A/B
testing**. Les deux premiers sont opérationnels et démontrés en condition
réelle (boucle de citation prouvée sur les 4 guildes). Le 3ᵉ — refinement
automatique des system prompts — n'est PAS encore implémenté. Cet ADR
définit comment l'aborder en Phase 5+.

Le besoin réel : à mesure que les missions s'accumulent (>50, >100, >500),
des patterns d'échec spécifiques émergent. Plutôt que d'attendre qu'un
humain les détecte et corrige le prompt manuellement, on veut :

1. Détecter automatiquement les patterns (ex. « le code_reviewer manque
   systématiquement les bugs de concurrence »).
2. Générer une variante de prompt qui corrige (en injectant un nouveau
   principe ou un exemple négatif).
3. Comparer rigoureusement la variante au prompt courant sur N missions
   représentatives.
4. Promouvoir la variante gagnante en prompt courant, en archivant
   l'ancien dans `prompts/<role>/archive/<date>_<reason>.md`.

## Décision

Architecture en 4 couches, chacune indépendamment testable et déployable.

### Couche 1 — Représentation des variantes

```python
# src/learning/prompt_variant.py
@dataclass
class PromptVariant:
    name: str                    # ex. "code_reviewer__add_concurrency_check"
    role: str                    # ex. "code_reviewer"
    prompt_path: Path            # ex. prompts/.../code_reviewer__variants/concurrency.md
    base_version: str            # le hash git du prompt courant à partir duquel on dérive
    rationale: str               # pourquoi cette variante existe (1-3 phrases)
```

Les variantes vivent dans des sous-dossiers `<role>__variants/` à côté du
prompt courant. Le frontmatter de chaque variante référence sa `base_version`
et son `rationale`.

### Couche 2 — Routage par variant

`BaseAgent.__init__` accepte un nouveau paramètre optionnel `prompt_path`
qui override la valeur par défaut. Un nouveau registry
`ActivePromptRegistry` mappe `(role, variant_name) → prompt_path`. Au
moment d'instancier un agent, le registry décide quel prompt charger
selon une politique (epsilon-greedy, Thompson sampling, ou rotation
simple selon la phase d'expérience).

Pour la Phase 5+ MVP : **rotation déterministe**. Chaque mission reçoit un
`experiment_run_id` (hash de mission_id). Pour les rôles en
expérimentation, le registry choisit `variant_a` si `hash % 2 == 0`,
`variant_b` sinon. Simple, reproductible, équitable sur 50+ missions.

### Couche 3 — Analyse comparative

`src/learning/ab_analyzer.py` :

```python
def compare_variants(
    role: str,
    variant_a_episodes: list[Path],
    variant_b_episodes: list[Path],
) -> ABTestReport:
    """
    Charge les épisodes des deux variantes (taggés via metadata
    'prompt_variant' ajouté par BaseAgent au record_episode), agrège les
    quality_score / coût / latence / saturation_rate, et calcule :
      - moyennes + médianes + écart-types
      - Welch's t-test sur les quality_scores
      - décision : keep_a / switch_to_b / inconclusive
    """
```

Critère de décision (Phase 5 MVP) :
- N >= 20 missions par variante minimum (sinon `inconclusive`)
- Si `mean(b) - mean(a) >= 0.02` ET `welch_t_test_p < 0.05` → `switch_to_b`
- Si `mean(a) - mean(b) >= 0.02` ET `welch_t_test_p < 0.05` → `keep_a`
- Sinon `inconclusive`

### Couche 4 — Promotion

Un script `scripts/promote_variant.py` qui :
1. Lit le rapport `ab_analyzer`.
2. Si `switch_to_b` : `git mv prompts/<role>/<role>.md
   prompts/<role>/archive/<date>_replaced_by_<variant>.md`, puis `git mv`
   la variante en prompt principal.
3. Crée un commit avec le rapport AB en commit message.
4. Désactive l'expérimentation pour ce rôle (le registry retire l'entrée).

## Conséquences

**Positives :**
- Refinement de prompts mesurable et réversible (Git histoire complète).
- Pas de dépendance à un service ML externe — tout reste dans le projet.
- Compatibilité totale avec la SkillsLibrary (les skills s'injectent dans
  le prompt courant, peu importe quelle variante est active).

**Négatives / à surveiller :**
- 20 missions par variant = ~$10 à ~$30 d'API par expérience selon la
  guilde. À budgéter.
- Risque de "p-hacking" si on multiplie les expériences sans
  pré-enregistrer les hypothèses. **Mitigation :** tout `PromptVariant`
  doit déclarer son `rationale` AVANT le run, vérifié au commit.
- Si deux rôles sont simultanément en expérimentation, les effets peuvent
  se confondre (l'amélioration vient-elle du nouveau prompt code_reviewer
  ou du nouveau prompt architect ?). **Mitigation :** un seul rôle en
  expérimentation à la fois en Phase 5+.

## Phasage

| Étape | Effort | Trigger |
|---|---|---|
| Couche 1 (PromptVariant + registry stub) | 0.5 jour | Quand on a ≥ 50 missions APPROVED par rôle |
| Couche 2 (routage déterministe + frontmatter `prompt_variant`) | 1 jour | Après couche 1 OK + 10 missions de smoke test |
| Couche 3 (ab_analyzer + tests stat) | 1 jour | Indépendant des autres |
| Couche 4 (script promote) | 0.5 jour | Après 1 expérience complète manuelle |

## Alternatives considérées

- **Bandit contextuel (Thompson sampling) :** plus puissant statistiquement
  mais demande beaucoup plus de données pour converger. Reporté à Phase 5++.
- **Outil tiers (Statsig, Optimizely) :** rejeté → over-engineering pour
  un projet 1-utilisateur, dépendance externe, données envoyées en cloud.
- **Refinement par humain seul (status quo) :** rejeté → ne tient pas la
  promesse "s'auto-entraîner" d'ADR-004 sur le long terme.

## Pré-requis avant implémentation

- ≥ 50 missions APPROVED accumulées par rôle (à ce jour : ~14 max sur
  research_lead — donc PAS encore le moment).
- Au moins un cas concret de pattern d'échec récurrent identifié
  manuellement (à ce jour : aucun observé sur les 14 missions).
- Budget dédié à l'expérience (~$30 pour 20×2 missions sur le rôle visé).

**Ne pas implémenter avant que ces 3 conditions soient remplies.** Sinon
on ajouterait de la complexité sans données pour la valider.
