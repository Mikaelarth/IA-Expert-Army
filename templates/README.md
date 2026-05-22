# templates/ — Templates de missions réutilisables (v0.8.0 F3)

Templates YAML+Jinja2 instanciables d'un clic depuis la page **🚀 Mission**
de la GUI. Adresse le pain point quotidien "à chaque mission, je re-rédige
les mêmes 5-10 lignes de description".

## Structure

```
templates/
└── missions/
    ├── fastapi-crud-endpoint.md
    ├── refactor-module.md
    ├── audit-owasp-module.md
    ├── stdlib-utility-function.md
    └── landing-page-saas.md
```

Chaque template est un fichier `.md` avec frontmatter YAML (métadonnées +
liste des paramètres) et corps Jinja2 (description de mission paramétrée).

## Format

```markdown
---
id: mon-template
name: "Nom affiché dans le picker GUI"
description: "Description courte 1-line"
guild: engineering            # engineering | research | creative | business | "" (auto)
tags: [tag1, tag2]
params:
  - name: entity_name         # nom du placeholder Jinja2
    label: "Nom de l'entité"  # label affiché en GUI
    example: "Product"        # placeholder/exemple
    required: true            # optionnel, défaut true
---
Texte de mission avec placeholders {{ entity_name }} interpolés.
```

## Comment ajouter un template

1. Créer `templates/missions/<id>.md` avec le format ci-dessus.
2. Tester localement : `streamlit run scripts/run_gui.py` → page Mission → le
   nouveau template apparaît dans le picker.
3. Commiter avec un message `chore(templates): add <name>`.

Les templates malformés (YAML cassé, frontmatter manquant) sont skippés
silencieusement par `list_templates()` — pas de crash GUI.

## Pourquoi Jinja2

- Standard Python (déjà transitif via FastAPI).
- Support `{{ default }}`, conditions, `.lower()`, filtres usuels.
- `StrictUndefined` activé : un paramètre oublié crashe explicitement
  (pas de placeholder silencieux dans la description).

## Politique de maintenance

- Pas de template trop spécifique à un projet — viser des cas génériques
  utiles à plusieurs sessions.
- Un template doit être **testé** manuellement avant commit (lancer la
  mission, vérifier que les agents convergent).
- Si un template produit régulièrement des résultats NEEDS_CHANGES, le
  raffiner (préciser contraintes, ajouter exemples) plutôt que retirer.
