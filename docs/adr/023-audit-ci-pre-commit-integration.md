# ADR-023 — Audit anti-patterns intégré en CI + pre-commit

**Statut :** Accepted
**Date :** 2026-05-15
**Commits associés :** Sprint QQQ
**Précédents :** ADR-022 (5 règles d'audit), ADR-019/020 (gate coverage)

## Contexte

Sprint LLL (ADR-022) a livré le module `src/core/audit.py` + le script CLI
`scripts/audit_codebase.py` avec 5 règles de détection d'anti-patterns.

**Mais** : tant que l'audit reste manuel (`just audit-strict`), il sera
oublié sous pression. Un PR mergée avec un nouvel anti-pattern = dérive
silencieuse. Pareil pour la politique coverage avant Sprint KKK : l'outillage
existait, mais sans CI gate, il dérivait.

ADR-023 ferme cette boucle en intégrant l'audit aux 2 endroits où il a le
plus d'impact :
1. **CI** (bloquant) — empêche tout merge avec findings
2. **pre-commit** (bloquant local, skippable d'urgence) — feedback dev en 1-2s

## Décision

### 1. Step CI dédié dans `.github/workflows/ci.yml`

```yaml
- name: Audit codebase (anti-patterns)
  run: uv run python scripts/audit_codebase.py --strict
```

Position : après les tests et le health check, avant le merge. Si findings
non-zéro → exit 1 → step rouge → PR bloquée si branch protection activée.

**SKIP du double-run** : la liste `SKIP=` du step "Run pre-commit" inclut
désormais `audit-codebase` pour éviter d'auditer 2× la même chose en CI
(pre-commit hooks + step dédié).

### 2. Hook pre-commit dans `.pre-commit-config.yaml`

```yaml
- id: audit-codebase
  name: Audit codebase (anti-patterns Sprint LLL)
  entry: uv run python scripts/audit_codebase.py --strict
  language: system
  pass_filenames: false
  stages: [pre-commit]
```

**Coût** : 1-2s sur le repo entier (~3000 lignes Python), acceptable pour
pre-commit (qui doit rester < 5s pour ne pas casser la flow dev).

**Bypass d'urgence** : `SKIP=audit-codebase git commit -m "..."`. Documenté
dans le hook pour que l'utilisateur sache.

### 3. Bugfix tolérance ±2 lignes (whitelist robuste)

**Bug découvert pendant Sprint QQQ** : ruff format peut déplacer un
commentaire `# audit: ignore ORPHAN_TODO` d'une ligne à une autre lors de
l'auto-formatting (ex: split de paramètres sur plusieurs lignes). Conséquence :
le tag whitelist se retrouve sur une ligne différente du finding, le
détecteur ne le voit plus, finding réapparaît.

**Fix** : `detect_orphan_todos` cherche désormais le tag whitelist sur
**±2 lignes autour du finding** (au lieu de juste la ligne du finding).
Reste robuste face aux formatters automatiques.

```python
# Sprint QQQ : whitelist tolérante ±2 lignes
window_start = max(0, line_no - 3)
window_end = min(len(all_lines), line_no + 2)
if any(_is_ignored(all_lines[i], "ORPHAN_TODO") for i in range(window_start, window_end)):
    continue
```

À étendre aux autres règles si le même problème apparaît (pour l'instant,
seul ORPHAN_TODO scanne ligne-par-ligne — les autres ont leur propre logique).

## Conséquences

**Positives** :
- **Aucun anti-pattern ne peut plus être mergé silencieusement** (CI bloque)
- Le dev voit le feedback **en local** au moment du commit (pre-commit)
- Le bypass `SKIP=audit-codebase` reste disponible pour les commits urgents
  (sans pourrir le hook)
- Tolérance ±2 lignes rend le whitelist résistant aux reformatages auto
- Validation empirique : `just audit-strict` passe à 0 findings sur le repo
  actuel après les corrections Sprint LLL

**Négatives** :
- Le hook pre-commit ajoute 1-2s à chaque commit (acceptable)
- Si quelqu'un commit avec `SKIP=audit-codebase` régulièrement, on perd
  l'effet. Mitigation : la CI bloque quand même, donc le dev sera averti
  au push au plus tard.
- Le step CI fait une suite indépendante de tests : sur PR avec beaucoup
  de checks, le runner GitHub peut être saturé. Pour l'instant pas de
  problème (10 min budget configuré).

**À surveiller** :
- Si le projet ajoute du code en bulk (ex: agent IA qui régénère plusieurs
  modules), le hook pre-commit peut se déclencher en cascade. Solution :
  commit en 1 fois, le hook ne tourne qu'une fois.
- Si une nouvelle règle d'audit est ajoutée et qu'elle a des faux positifs
  initiaux, ça bloquera tout. Mitigation : ajouter la règle en `info`
  d'abord, observer N PR, puis passer à `warning`/`error` avec gate.

## Workflow complet (post-Sprint QQQ)

```
[dev local]
  git commit
    → pre-commit hooks (incl. audit-codebase --strict)
    → si findings → exit 1 → commit bloqué

[push GitHub]
  push origin feature/foo
    → CI workflow déclenché
    → step "Audit codebase" (--strict) en parallèle des autres
    → si findings → step rouge → PR mergeable bloquée

[merge main]
  PR merged → main protected → tous les checks doivent être verts
```

Trois portes en cascade. Pour qu'un anti-pattern atterrisse en `main`, il
faut explicitement :
1. Bypasser pre-commit local (`SKIP=audit-codebase`)
2. Forcer la PR malgré le CI rouge (admin override de branch protection)
3. Ignorer la fenêtre de revue

## Alternatives considérées

1. **Pre-commit seulement, pas de step CI dédié** : refusé. Quelqu'un sans
   pre-commit installé localement (PR externe, dev nouvelle machine) pourrait
   contourner. CI est le filet de sécurité ultime.

2. **Step CI seulement, pas de pre-commit** : refusé. Feedback trop tardif
   (l'utilisateur découvre le problème après push, pas au moment du commit).

3. **Hook pre-commit qui ne lance que les règles fast** (FILE_TOO_LONG seul) :
   refusé. Le coût total est de 1-2s — pas la peine de complexifier la config
   pour gagner 0.5s.

4. **Mode `--info` non-bloquant en pre-commit** : refusé. Fait le boulot d'un
   linter ignoré → personne ne corrige. Le bloquer force la discipline.

5. **Audit incrémental sur les fichiers stagés seulement** : intéressant mais
   complexifie la config (faut passer la liste de fichiers à `audit_codebase.py`
   qui ne le supporte pas pour l'instant). Reportable si le full-scan devient
   trop lent (> 5s sur grande croissance).

## Validation empirique

```bash
$ uv run pre-commit run audit-codebase --all-files
Audit codebase (anti-patterns Sprint LLL)................................Passed

$ uv run python scripts/audit_codebase.py --strict
Audit propre — aucun anti-pattern détecté
[exit 0]
```

CI workflow validera au prochain push.

## Sources

- ADR-022 — module audit + 5 règles
- ADR-019/020 — pattern parallèle pour le coverage gate
- Bug réel découvert Sprint QQQ : ruff format déplace les whitelists d'1 ligne
- Stratégie défensive : "trois portes en cascade" (pre-commit local +
  CI step + branch protection)
