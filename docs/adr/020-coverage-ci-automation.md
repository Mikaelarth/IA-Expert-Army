# ADR-020 — Automatisation du gate coverage en CI

**Statut :** Accepted
**Date :** 2026-05-15
**Commits associés :** Sprint KKK
**Précédents :** ADR-019 (politique manuelle de couverture)

## Contexte

L'ADR-019 (Sprint JJJ) a établi une politique manuelle :
- Mesurer avant d'annoncer (badge mesuré, pas estimé)
- Seuils minimaux par catégorie de module (≥85-90%)
- Régression > 2 pts sur un module → PR refusée

**Problème** : tant que c'est manuel, ça va dériver. Un dev (humain ou agent IA) qui ajoute du code sans tests **ne sait pas** qu'il fait baisser la couverture, et personne ne le voit en revue PR car personne ne lance `pytest --cov` à chaque fois.

## Décision

### 1. `fail_under = 90` dans `pyproject.toml`

```toml
[tool.coverage.report]
fail_under = 90
precision = 1
show_missing = true
sort = "Cover"
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    'if __name__ == "__main__":',
    "async with stdio_server",
    "raise SandboxUnavailable",
]
```

`pytest --cov` lit ces settings et **renvoie un exit code non-zero** si la couverture descend sous le seuil. C'est un kill-switch automatique.

### 2. Step CI dédié dans `.github/workflows/ci.yml`

```yaml
- name: Coverage gate (90% global, fail on regression)
  run: >
    uv run pytest tests/unit/ tests/integration/
    --cov=src
    --cov-report=term
    --cov-report=xml:coverage.xml
    -q --tb=no

- name: Upload coverage artifact
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: coverage-report
    path: coverage.xml
    retention-days: 30
```

Effets :
- **Toute PR qui régresse < 90% est bloquée au merge** (le CI rouge empêche le merge si la branche protection est activée)
- L'artefact `coverage.xml` est upload pour les 30 derniers jours, permettant analyse posthume
- `-q --tb=no` garde la sortie compacte (les détails sont dans le step "Run unit + integration test suite" précédent)

### 3. Recipes `justfile` (workflow local)

```bash
just coverage          # Rapport terminal détaillé (development)
just coverage-strict   # Bloque si < 90% (mêmes règles que le CI)
just coverage-html     # Rapport HTML browsable dans htmlcov/
```

**Workflow recommandé avant chaque PR** :
```bash
just coverage-strict   # doit retourner exit 0
```

Si rouge → soit tu ajoutes les tests manquants, soit tu modifies `fail_under` dans `pyproject.toml` (avec ADR justifiant la baisse).

### 4. `.gitignore` déjà à jour

`htmlcov/`, `coverage.xml`, `coverage.json`, `.coverage` étaient déjà gitignored (Sprint préalable) — aucune modification nécessaire.

## Conséquences

**Positives** :
- **Plus aucune régression silencieuse possible** sur le coverage global
- Le CI affiche en clair le nouveau % à chaque PR (visible dans les checks GitHub)
- Workflow local `just coverage-strict` permet à un dev de valider AVANT de pousser
- L'artefact CI `coverage.xml` permet d'intégrer plus tard avec Codecov / Coveralls si besoin
- Le seuil étant dans `pyproject.toml`, modifier le seuil exige une modif explicite + commit (traçable)

**Négatives** :
- Le `fail_under = 90` est un seuil **global** — un module qui passe de 95% à 75% peut ne pas être détecté si le reste compense. Pour un seuil **per-module**, il faudrait un outil tiers (ex: `coverage-thresholder`) ou un script custom. Reporté à un Sprint futur si nécessaire.
- Le `precision = 1` (1 chiffre après la virgule) peut faire monter et descendre artificiellement (90.0 ↔ 89.95) sur de petits changements. Mitigation : on garde 1 chiffre car ce n'est qu'informationnel ; le `fail_under = 90` arrondit naturellement.
- Le workflow local `coverage-strict` ajoute 60s à chaque vérif pré-PR. Acceptable.

**À surveiller** :
- Que le CI ne devienne pas trop strict si on rajoute des intégrations lourdes — le run intégration migrate_vps fait déjà ~50s à lui seul
- Que le seuil `fail_under = 90` ne devienne pas une excuse pour s'arrêter à 90.1% au lieu de viser 95%+ sur les modules critiques (la culture de "minimum acceptable" est un piège)

## Workflow d'évolution du seuil

**Pour MONTER le seuil** (ex: 90 → 92 après ajout de gros tests) :
1. Vérifier `just coverage-strict` passe
2. Bumper `fail_under` dans `pyproject.toml`
3. MAJ badge README
4. Commit + note dans CHANGELOG : `chore(coverage): bump seuil 90→92 (justification)`

**Pour BAISSER le seuil** (extrême — ex: 90 → 85 après suppression de modules très testés) :
1. **Nouveau ADR obligatoire** justifiant la baisse
2. Modif `pyproject.toml`
3. MAJ badge README
4. Commit avec référence à l'ADR

## Alternatives considérées

1. **Per-module thresholds dans pyproject** : pas supporté nativement par pytest-cov. Nécessiterait un outil externe (`coverage-thresholder`) ou un script custom. Reporté — la politique manuelle d'ADR-019 le couvre déjà via revue PR.

2. **Codecov / Coveralls integration** : utile pour visualiser dans la PR, mais ajoute une dépendance externe (et compte SaaS). Pour un projet solo, le step CI + l'artefact suffisent. Si l'équipe grandit, on intégrera.

3. **Branch coverage (`--cov-branch`)** : plus strict mais ajoute du bruit (des branches `if x is None` non triggered comptent comme manquantes). Reporté tant que le statement coverage n'est pas stable à 95%+.

4. **Bloquer aussi sur précision (par exemple, refuser tout module < 85%)** : implémentable via un script post-pytest qui parse le XML. Sur-design pour un projet solo. À considérer si on a > 50 contributeurs.

5. **Pre-commit hook qui lance pytest --cov** : refusé. pytest --cov complet prend 60s — trop lent pour pre-commit qui doit rester < 10s. Le CI est le bon endroit.

## Validation empirique

```
$ just coverage-strict
...
TOTAL                                          2938    204  93.1%
Required test coverage of 90% reached. Total coverage: 93.06%
======================= 517 passed in 64.73s ========================
```

Test du fail (sanity check) :
```
$ uv run pytest --cov-fail-under=99
TOTAL                                          2938    204  93.1%
FAIL Required test coverage of 99% not reached. Total coverage: 93.06%
```

Les 2 mécaniques fonctionnent.

## Sources

- ADR-019 — politique manuelle dont KKK automatise le gate
- pytest-cov docs — `fail_under` et `--cov-fail-under`
- coverage.py docs — `[tool.coverage.report]` exclude_lines patterns
- GitHub Actions docs — `actions/upload-artifact@v4`
