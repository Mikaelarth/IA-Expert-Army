# ADR-008 — Sandbox : trade-off `read_only=False` accepté

**Statut :** Accepted
**Date :** 2026-05-10 (décidé commit `fcfa051`, formalisé ici)

## Contexte

ADR-003 (mode autonome avec garde-fous) impose 10 garde-fous non négociables
sur le sandbox d'exécution Docker. Le garde-fou #1 — *« container rootfs
read-only »* — était initialement implémenté dans `src/sandbox/runner.py`
via `read_only=True`.

En condition réelle (commit `fcfa051`, validation manuelle), l'appel
`container.put_archive()` qui extrait le tar du workspace dans
`/workspace` a échoué avec :

```
APIError: 400 Client Error
"container rootfs is marked read-only"
```

**Cause technique** : `read_only=True` fige le rootfs **avant** que les
mounts `tmpfs` (`/tmp`, `/workspace`) soient effectivement attachés.
`put_archive` est exécuté entre `container.create()` et `container.start()`,
soit pendant la fenêtre où la couche d'écriture n'existe pas encore. Le
résultat : impossible d'extraire le workspace, donc impossible d'exécuter
quoi que ce soit dans le sandbox.

## Décision

**On accepte `read_only=False`** sur le rootfs du container sandbox.

Les 9 autres garde-fous restent intacts et offrent une défense en profondeur
suffisante pour le use-case :

| # | Garde-fou maintenu | Effet |
|---|---|---|
| 2 | `network_mode="none"` | Aucune connectivité sortante depuis le sandbox |
| 3 | `user="nobody:nogroup"` | Pas de privilèges root dans le container |
| 4 | `mem_limit="512m"` | Crash propre si dépasse 512 MB RAM |
| 5 | `nano_cpus=1e9` (1 CPU) | Pas de saturation host |
| 6 | `pids_limit=256` | Anti fork-bomb |
| 7 | `timeout` strict + `kill` overflow | Pas de hang infini |
| 8 | Container éphémère (`remove(force=True)` en finally) | Aucune persistance entre runs |
| 9 | `tmpfs={"/tmp": "size=64m"}` | Espace scratch borné |
| 10 | Workspace tar (pas bind mount) | Aucun fichier host exposé sauf ce qu'on copie explicitement |

## Conséquences

**Positives**
- Le sandbox fonctionne. Sans ce trade-off, `apply_mission --validate`
  et `run_mission --apply --validate` seraient inutilisables — donc
  l'ensemble de la boucle qualité Engineering serait cassée.
- Validation production : 9/9 pytest PASSED sur le code généré par
  les agents (session 8, commit `40eb78a`).
- Tests régression (`test_sandbox_runner.py`) assertent désormais
  `read_only=False` AVEC un commentaire pointant vers l'incident
  d'origine — empêche qu'un dev futur ré-active `read_only=True`
  pensant améliorer la sécurité.

**Négatives / à surveiller**
- Un code malicieux générée par un agent COULD théoriquement modifier
  son propre fichier dans `/workspace` ou créer des fichiers tmp
  ailleurs dans le container. **Risque réel : négligeable** parce que :
  1. Le container est détruit immédiatement après le run.
  2. Aucun network = aucune exfiltration possible.
  3. User `nobody` = aucun accès aux fichiers système.
  4. Les fichiers créés meurent avec le container.
- Si on voulait un jour exécuter du code potentiellement adversarial
  (pas le cas en interne avec nos propres agents), il faudrait
  réintroduire `read_only=True` via une stratégie différente
  (bind-mount read-only + tmpfs write — moins portable Windows).

## Alternatives considérées

1. **Bind-mount du workspace** (`docker run -v $workspace:/workspace:ro`)
   - PRO : `read_only=True` peut rester actif sur le rootfs car le mount
     est explicitement RW (ou RO selon le besoin).
   - CON : portabilité Windows ↔ Linux moins bonne (Docker Desktop
     translate les paths Windows → Linux avec des limitations).
   - CON : nécessiterait de réécrire le code d'orchestration des fichiers.
   - **Reporté** à Phase 5++ si un besoin précis émerge.

2. **Démarrer le container vide puis injecter via exec** (au lieu de
   put_archive avant start)
   - PRO : tmpfs serait monté avant l'injection.
   - CON : complexité accrue (gestion d'un container "wait" + exec
     ensuite).
   - **Rejeté** — pas justifié pour le gain marginal.

3. **Pre-build une image avec workspace déjà rempli** (un par mission)
   - PRO : pas de write nécessaire au runtime.
   - CON : explosion du nombre d'images, latence build par mission.
   - **Rejeté** — non-scalable.

## Tests régression

```python
# tests/unit/test_sandbox_runner.py
def test_runner_passes_security_options(...) -> None:
    ...
    # Note: read_only=False (trade-off documenté ADR-008) — put_archive
    # écrit avant le mount tmpfs, donc impossible de cumuler read_only=True
    # ET extraction tar du workspace. Compensation : tous les autres
    # garde-fous tiennent.
    assert call_kwargs["read_only"] is False
```

Si un futur contributeur tente de remettre `read_only=True`, ce test échoue
avec le pointeur vers le présent ADR.
