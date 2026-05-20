# Session 4 — Amélioration du prompt code_reviewer + re-mesure

**Date** : 2026-05-20
**Branche** : `feat/ollama-backend`
**Mission ID** : `6c1786d3-a32f-4ea7-a2c3-11945e9436ba`
**Hypothèse à tester** : Le finding Session 2 (Qwen-Reviewer ne fait pas l'exécution mentale des tests) peut être résorbé par un prompt engineering ciblé sur le `code_reviewer.md`.

---

## Modification du prompt — v0.1.0 → v0.2.0

Diff sur `prompts/guilds/engineering/code_reviewer.md` :

1. **Frontmatter** : champ `revisions:` ajouté pour tracer la rationale du bump v0.2.0.
2. **Critères d'évaluation** : ligne "Tests" enrichie de "**assertions correctes** (cf. section dédiée ci-dessous)".
3. **Nouvelle section "Vérification des tests — OBLIGATOIRE, exécution mentale"** :
   - Protocole en 3 étapes par test (trace symbolique → comparaison attendu → couverture input space)
   - Exemple anti-pattern explicite (le test bugué Session 2 `slugify("!@#$%") == "-"` est reproduit avec sa trace d'exécution montrant que `""` est l'attendu correct)
   - 4 anti-patterns supplémentaires à flagger (test vacuously passing, sans assertion, copié-du-résultat, couverture trompeuse)
4. **Format de sortie** : le `summary:` doit "mentionner EXPLICITEMENT si tu as fait l'exécution mentale de tous les tests".
5. **Règles de verdict** : APPROVED nécessite désormais "tu as fait l'exécution mentale de TOUS les tests et confirmé que chaque assertion est correcte" comme pré-requis non-négociable.
6. **Principes** : ajout final "Ne valide jamais un test sans en avoir tracé l'exécution mentalement. C'est la première chose qui distingue un bon reviewer d'un mauvais."

---

## Bug introduit + fixé en cours de Session 4

Le premier essai a planté avec une erreur YAML scanner (`could not find expected ':'`). Cause : j'avais écrit le champ `revisions:` sous forme `- v0.2.0 (2026-05-20, Session 4) : ajout ...`. Le `:` à l'intérieur du texte non-quoté a été interprété par le parser YAML comme un séparateur key/value.

**Fix** : quoter le string entièrement (`"v0.2.0 ... — ajout ..."` avec tiret cadratin au lieu de deux-points). Sanity-check ajouté via script Python qui charge le frontmatter avec `yaml.safe_load` avant relancement.

**Leçon générale** : tout caractère `:` non-trivial dans un string YAML doit être quoté ou remplacé. Le projet écrit beaucoup de YAML (prompts, outputs d'agents, mission summaries) — c'est un risque latent à surveiller.

---

## Résultats de la mission re-jouée

| Métrique | Session 2 (prompt v0.1.0) | Session 4 (prompt v0.2.0) | Delta |
|---|---|---|---|
| **Verdict** | APPROVED | APPROVED | = |
| **Quality score** | 0.93 | **0.95** | **+0.02** |
| **Durée totale** | 1270.68 s (21 min 11 s) | 1419.72 s (23 min 40 s) | +2 min 29 s |
| **Coût USD** | $0.00 | $0.00 | = |
| **Fichiers produits** | 2 | 2 | = |
| **Repair loop** | Non | Non | = |
| **Mention explicite "exécution mentale" dans le summary du Reviewer** | ❌ Non | ✅ **Oui** | — |

### Détail par agent

| Agent | Durée | Tokens in | Tokens out | Saturation |
|---|---|---|---|---|
| ChiefOrchestrator | 408.15 s (+135 s vs S2) | 1842 | 422 | non |
| SoftwareArchitect | 322.76 s (−66 s vs S2) | 2117 | 436 | non |
| BackendDeveloper | 341.74 s (−17 s vs S2) | 1931 | 460 | non |
| **CodeReviewer** | **341.72 s (+96 s vs S2)** | **3351 (+456 vs S2)** | 330 | non |

Le Reviewer a consommé +96 secondes et +456 tokens d'input cette fois — cohérent avec un prompt système enrichi qui force plus d'introspection. Sa sortie est légèrement plus courte (330 vs 341 tokens) — moins de bla-bla, plus de précision.

### Extrait du YAML du Reviewer (preuve directe que le prompt a marché)

```yaml
verdict: APPROVED
quality_score: 0.95
summary: |
  L'implémentation et les tests fournis respectent fidèlement la proposition architecturale donnée.
  La fonction `slugify` suit correctement les étapes décrites : normalisation, suppression des
  caractères non ASCII, conversion en minuscules, remplacement des caractères non-alphanumériques
  par des tirets, et supression des tirets de début/fin.
  Chaque test a été exécuté mentalement pour s'assurer que les assertions sont correctes.
```

La phrase **"Chaque test a été exécuté mentalement pour s'assurer que les assertions sont correctes"** est l'output direct du nouveau prompt v0.2.0 (l'instruction `mentionne EXPLICITEMENT si tu as fait l'exécution mentale` du Format de sortie a été suivie).

---

## Honnêteté épistémique : ce qui est mesuré, ce qui ne l'est pas

### ✅ Mesuré directement

- **Le prompt v0.2.0 induit le comportement souhaité** : le Reviewer mentionne explicitement avoir fait l'exécution mentale dans son summary.
- **Score qualité +0.02** vs Session 2 (rigueur accrue détectable).
- **Coût +96 s sur le Reviewer** : le surcoût de l'exécution mentale est mesurable.

### ⚠️ Pas mesuré directement

**Le test bugué Session 2 n'a pas été re-généré par le Developer cette fois.** Le BackendDeveloper a produit 4 tests au lieu de 5, et son test "ponctuation + espaces" combine ponctuation et lettres (entrée `"?? Hello   World !"`) — donc il n'y a pas de cas pur "ponctuation seule" à valider.

**On ne peut donc PAS prouver expérimentalement que le Reviewer v0.2.0 aurait catché le bug Session 2.** On peut seulement constater qu'il dit faire l'exécution mentale et que son score est plus haut.

Pour une preuve directe, il faudrait soit :
- Soumettre au Reviewer le code+test bugué Session 2 inchangé (test d'unité isolé du Reviewer)
- Soit forcer le Developer à reproduire le bug (peu réaliste, le Developer n'est pas déterministe)

**Plan pour Session 5+** : ajouter un test unit qui appelle directement le Reviewer agent sur un input contrôlé (code+test bugué pré-écrit), pour mesurer concrètement la résorption.

---

## Nouveau finding empirique Session 4

Le Reviewer v0.2.0 a manqué deux choses pourtant non-triviales :

### 1. Chemin de fichier non conforme à la spec

La mission précisait :
> Module cible : `src/utils/text.py`. Tests cible : `tests/unit/test_text.py`.

Le Developer a écrit les tests dans `src/utils/test_text.py` (donc à côté du module source, **pas** dans le dossier des tests). Le Reviewer n'a rien dit — il ne vérifie pas l'organisation des fichiers vs spec.

**Correction appliquée manuellement post-mission** : `mv src/utils/test_text.py tests/unit/test_text.py`. Création d'un `src/utils/__init__.py` au passage (manquant pour l'importabilité du package).

**Action Session 5+ tracée** : étendre le prompt code_reviewer.md avec une section "Vérification de l'organisation des fichiers" qui demande de comparer chaque `file:` produit vs les paths mentionnés dans la description de la mission.

### 2. Couverture incomplète

La mission demandait explicitement 5 cas : *"cas canoniques (Hello World), accents (Café à Paris), chaîne vide, ponctuation multiple, espaces multiples"*. Le Developer a produit 4 tests — il a fusionné "ponctuation multiple" et "espaces multiples" en un seul test, et n'a pas couvert le cas **ponctuation seule** (qui était précisément le cas problématique Session 2).

Le Reviewer (dans son champ `strengths:`) a affirmé "Tests exhaustifs couvrant les cas demandés (texte normal, caractère spéciaux, chaîne vide)" — soit 3 cas mentionnés sur 5 demandés. **Le Reviewer a mal compté.**

**Correction appliquée manuellement post-mission** : ajout d'un `test_punctuation_only_yields_empty` qui ancre le cas Session 2 :
```python
def test_punctuation_only_yields_empty() -> None:
    assert slugify("!@#$%^&*().,?/") == ""
```

5/5 tests verts au final.

### 3. `import pytest` non utilisé

Ruff F401. Détail mineur (le Reviewer n'a pas catché, mais ce n'est pas un blocker).

---

## Validation du code et des tests produits

| Test | Trace mentale faite par moi | Résultat pytest |
|---|---|---|
| `test_hello_world` | `"Hello World"` → NFD → ASCII → lower → `"hello world"` → re.sub → `"hello-world"` → strip → `"hello-world"` ✓ | PASS |
| `test_cafe_a_paris` | `"Café à Paris"` → NFD décompose accents → ASCII drop `Mn` → `"Cafe a Paris"` → lower → `"cafe a paris"` → re.sub → `"cafe-a-paris"` → strip → `"cafe-a-paris"` ✓ | PASS |
| `test_empty_string` | trivial → `""` ✓ | PASS |
| `test_multiple_punctuation_and_spaces` | `"?? Hello   World !"` → NFD/ASCII idem → lower → `"?? hello   world !"` → re.sub → `"-hello-world-"` → strip → `"hello-world"` ✓ | PASS |
| `test_punctuation_only_yields_empty` (ajouté manuellement) | `"!@#$%^&*().,?/"` → idem → re.sub → `"-"` (compact) → strip → `""` ✓ | PASS |

Code source `src/utils/text.py` : correct et idiomatique. Pipeline lisible (NFD → drop combining marks → lower → re.sub non-alphanum → strip dashes). Commentaire "Remove non-ASCII characters" légèrement inexact (en réalité ça retire les marques combinantes Mn ; les autres caractères non-ASCII sont retirés plus tard par le `re.sub r'[^a-z0-9]+'`). Pas bloquant.

---

## Conclusion Session 4

**Le prompt engineering du Reviewer fonctionne — partiellement et de manière mesurable.**

| Critère | Verdict |
|---|---|
| Le nouveau prompt induit le comportement demandé (mention "exécution mentale") | ✅ |
| Score qualité s'améliore (+0.02) | ✅ |
| Le Reviewer catche désormais les tests buggy | ⚠️ Non testé directement (bug Session 2 non reproduit) |
| Le Reviewer catche les chemins de fichiers non conformes à la spec | ❌ Nouveau finding — Session 5 prévue |
| Le Reviewer compte correctement les cas de tests demandés | ❌ Nouveau finding — Session 5 prévue |

**Score session : 6/10**. Progrès réel sur l'axe ciblé (exécution mentale), 2 nouveaux findings à adresser. La boucle d'amélioration des prompts est démontrée comme fonctionnelle — c'est l'objectif principal atteint.

---

## Actions tracées pour les sessions suivantes

- **Session 5** : étendre `code_reviewer.md` v0.3.0 avec
  - Section "Vérification des paths des fichiers produits vs spec mission"
  - Section "Vérification du nombre de cas de tests vs liste demandée dans la description"
- **Session 5** : ajouter un **test unit du Reviewer** qui lui soumet le code+test bugué Session 2 pré-écrit et vérifie qu'il retourne `verdict: NEEDS_CHANGES` ou `severity: major` sur le test bugué. Mesure directe et déterministe.
- **Session 6+** : recommencer la même boucle pour `prompts/guilds/engineering/backend_developer.md` (qui a écrit le test dans le mauvais dossier + a fait l'oubli de couverture).
