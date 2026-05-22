---
id: stdlib-utility-function
name: "Fonction utilitaire stdlib"
description: "Fonction Python utilitaire pure (stdlib only) avec tests pytest exhaustifs — type slugify, parser, normaliser."
guild: engineering
tags: [stdlib, utility, pytest, pure-function]
params:
  - name: function_name
    label: "Nom de la fonction (snake_case)"
    example: "slugify"
    required: true
  - name: signature
    label: "Signature Python"
    example: "slugify(text: str) -> str"
    required: true
  - name: behavior
    label: "Comportement attendu en 1-2 phrases"
    example: "Convertit un texte arbitraire en slug url-safe : lowercase, accents retirés, non-alphanum → '-', dashes compactés."
    required: true
  - name: file_target
    label: "Module cible (chemin depuis src/)"
    example: "utils/text.py"
    required: true
---
Implémente la fonction utilitaire **`{{ function_name }}`** avec signature :

```python
{{ signature }}
```

## Comportement

{{ behavior }}

## Livrables attendus

1. **Implémentation** dans `src/{{ file_target }}` :
   - Stdlib uniquement (pas de dépendance externe).
   - Type hints stricts + docstring détaillée avec exemples.
   - Cas limites traités explicitement (string vide, None si applicable, unicode).

2. **Tests pytest** dans `tests/unit/test_{{ function_name }}.py` :
   - Cas canoniques (3-5 exemples typiques).
   - Edge cases (chaîne vide, caractères spéciaux, très long input).
   - Property-based tests si pertinent (hypothesis n'est PAS dispo, donc
     paramétrisation manuelle via `@pytest.mark.parametrize`).
   - Au moins 8-10 cas de test au total.

## Contraintes

- Pure function : pas d'I/O, pas de side effects, pas de state.
- Idempotente : `f(f(x)) == f(x)` pour la majorité des inputs.
- Performance : O(n) sur la taille de l'input pour les strings.
- Pas de import lourd : `re`, `unicodedata`, `string` OK ; éviter `regex`,
  `unidecode`, etc.

## Critères de succès

- Tous les tests pytest passent (run propre).
- Coverage du nouveau module = 100 %.
- Mypy strict clean.
- Audit codebase 0 finding sur le nouveau fichier.
