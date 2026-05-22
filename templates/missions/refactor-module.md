---
id: refactor-module
name: "Refactor d'un module Python"
description: "Refactoring guidé d'un module existant — séparer responsabilités, extraire helpers, garder les tests verts."
guild: engineering
tags: [refactor, python, quality]
params:
  - name: module_path
    label: "Chemin du module à refactor"
    example: "src/orchestrator/router.py"
    required: true
  - name: pain_point
    label: "Problème principal à adresser"
    example: "La méthode run() fait 200 lignes et mélange routing, exécution et logging"
    required: true
  - name: target_loc
    label: "LOC cible par fichier après refactor (suggestion)"
    example: "200"
    required: false
---
Refactor le module **`{{ module_path }}`** pour adresser le problème suivant :

> {{ pain_point }}

## Méthodologie attendue

1. **Diagnostic** — l'Architect commence par lister :
   - Les responsabilités actuelles du module (1-N par fonction/classe).
   - Les couplages cachés (variables globales, side effects, état partagé).
   - Les blocs > 50 lignes ou cyclomatic complexity élevée.

2. **Proposition d'architecture** — décompose en 2-4 fichiers cohérents,
   avec un diagramme d'imports (qui dépend de qui). Si la cible LOC par
   fichier est précisée : viser ~{{ target_loc | default("200") }} lignes max.

3. **Implémentation** — le Developer applique le refactor en respectant :
   - **Les tests existants doivent rester verts SANS modification**.
   - Aucune régression de coverage (vérifier post-refactor).
   - Imports publics préservés via re-export si déplacement (rétrocompat).
   - Pas de feature added — pure réorganisation.

4. **Validation Reviewer** :
   - Vérifier que le refactor répond à `pain_point` (pas juste cosmétique).
   - Confirmer que la séparation des responsabilités est plus claire.
   - Refuser si du code mort a été créé (helpers extraits non appelés).

## Contraintes

- **Aucun changement de comportement externe** — le module exporte la même
  API. Si une signature doit changer, créer une PR séparée d'API.
- **Pas de feature** — refactor strict. Si une opportunité d'amélioration
  apparaît, la noter en TODO dans le commit message, pas dans le code.
- Tests pytest + ruff + mypy doivent tous rester verts.
