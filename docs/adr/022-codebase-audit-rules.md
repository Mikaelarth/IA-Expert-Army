# ADR-022 — Audit codebase : 5 règles d'anti-patterns détectées automatiquement

**Statut :** Accepted
**Date :** 2026-05-15
**Commits associés :** Sprint LLL

## Contexte

Le projet est passé de 415 à 539 tests verts en 7 sprints (EEE → OOO), avec
20+ ADRs. Cette croissance rapide expose à des dérives architecturales subtiles :

- Des fichiers qui grossissent silencieusement (>500 lignes)
- Des tests créés à la hâte sans assertion réelle
- Des `# TODO` qui s'accumulent sans owner / deadline / référence
- Des agents Opus ajoutés sans documenter la justification (politique ADR-016)
- Des prompts hardcodés en string Python (au lieu de `prompts/**/*.md`)

Avec un agent IA qui peut écrire du code dans le projet, ces dérives peuvent
être introduites **sans intention malveillante**, simplement parce que l'agent
ne connaît pas les conventions du repo.

ADR-019/020 ont posé le garde-fou **coverage** (tests verts, % global gardé).
ADR-022 pose le garde-fou **architecture** (anti-patterns détectés).

## Décision

### Module `src/core/audit.py`

Cinq détecteurs d'anti-patterns ciblés, basés sur le fonctionnement réel du
projet :

| Règle | Sévérité | Approche |
|---|---|---|
| `FILE_TOO_LONG` | warning | Comptage lignes. Seuil 500 par défaut. |
| `TEST_NO_ASSERT` | warning | AST walk : cherche `assert`, `pytest.raises`, `mock.assert_*`, `pytest.fail/skip` |
| `ORPHAN_TODO` | info | Regex `# TODO\|FIXME\|XXX\|HACK` sans référence (#issue, Sprint XXX, ADR-NNN, @user, date YYYY-MM-DD) |
| `OPUS_WITHOUT_JUSTIFICATION` | warning | `model=...model_strategic` sans commentaire `# Opus :` à ±3 lignes |
| `HARDCODED_PROMPT` | warning | AST walk : `Assign` avec str literal > 300 chars + indicateurs `Tu es` / `You are` / etc. |

Chaque détecteur :
- Renvoie une liste de `Finding(rule, severity, path, line, snippet, message)`
- Est testable indépendamment via unit tests (34 tests dans `test_audit.py`)
- Est whitelistable via commentaire `# audit: ignore <RULE>` à la ligne du finding

### Pourquoi AST plutôt que regex pour TEST_NO_ASSERT et HARDCODED_PROMPT

**Bug critique trouvé pendant Sprint LLL** : la première implémentation de
`TEST_NO_ASSERT` utilisait des regex pour détecter les fonctions test_* puis
extraire leur body. Résultat : 466 faux positifs sur 539 tests réels (la logique
d'extraction du body était cassée — coupait avant le premier `assert`).

**Fix** : passage à `ast.parse()` qui donne un arbre syntaxique Python
canonique. `ast.walk(func_node)` traverse correctement le body, gère
async/sync, decorators, nested functions, with-statements. Robuste, déterministe.

**Pareil pour `HARDCODED_PROMPT`** : la regex `"""...."""` matchait les
**docstrings de modules/fonctions** (faux positifs sur tous les fichiers
documentés). Fix AST : on ne cherche que les `Assign` avec str literal en
value — exclut naturellement les docstrings.

### Script CLI `scripts/audit_codebase.py`

```bash
uv run python scripts/audit_codebase.py                     # rapport complet
uv run python scripts/audit_codebase.py --rule FILE_TOO_LONG  # filtre
uv run python scripts/audit_codebase.py --strict             # exit 1 si findings
uv run python scripts/audit_codebase.py --json               # output CI/tooling
uv run python scripts/audit_codebase.py --verbose            # messages complets
```

### Recipes `justfile`

```bash
just audit          # rapport rapide
just audit-strict   # bloque si findings (= ce qui tournerait en CI)
just audit-verbose  # détails par finding
just audit-rule TEST_NO_ASSERT  # filtre par règle
```

### Whitelisting

Mécanisme : commentaire `# audit: ignore <RULE>` à la ligne du finding.

Exemples concrets dans le repo après Sprint LLL :
```python
# tests/unit/test_audit.py — fixture qui contient INTENTIONNELLEMENT un TODO :
"# TODO refactor"  # audit: ignore ORPHAN_TODO

# src/mcp_servers/memory_search.py — fichier 509 lignes accepté :
"""# audit: ignore FILE_TOO_LONG -- 509 lignes acceptées : 6 handlers MCP +
définition complète des inputSchemas inline. Split prévu si > 700 lignes."""
```

**Discipline** : chaque whitelist doit avoir une **justification courte** dans
le commentaire (sinon c'est juste un opt-out paresseux).

## Validation empirique (Sprint LLL)

Lancement initial sur le codebase actuel :

| État | Findings | Détail |
|---|---|---|
| Initial (regex naïf) | **487** | dont 466 faux positifs TEST_NO_ASSERT |
| Après refactor AST | **13** | vrais positifs gérables |
| Après corrections + whitelists | **0** | codebase propre |

Corrections appliquées (vrais positifs) :
- 5 `OPUS_WITHOUT_JUSTIFICATION` → ajout commentaire `# Opus : ...` justifiant
  (Architect, ChiefOrchestrator, ResearchLead, ContentStrategist, hello_agent)
- 1 `TEST_NO_ASSERT` → ajout `assert out is None` dans
  `test_print_sandbox_result_uses_default_console_when_none`
- 5 `FILE_TOO_LONG` → whitelists documentées avec rationale (memory_search,
  4 fichiers de tests longs mais cohérents)

## Conséquences

**Positives** :
- Le codebase est maintenant **vérifiablement propre** vis-à-vis de 5 anti-patterns identifiés
- Toute future PR peut être validée via `just audit-strict` en < 1s
- Les whitelists existantes documentent **pourquoi** une exception est faite (auto-documentation)
- Le bug AST découvert fortifie le module : les détecteurs futurs auront un meilleur foundation
- Habitude installée : un agent IA qui touche au code doit MAJ les commentaires de justification (politique ADR-016 désormais auto-vérifiée)

**Négatives** :
- Les 5 règles sont **opinionées** (TODO sans référence, Opus à documenter, etc.). Elles peuvent ne pas convenir à tous les projets — mais elles sont calibrées sur les besoins de IA-Expert-Army.
- Le seuil 500 lignes pour `FILE_TOO_LONG` est arbitraire. Justifié par l'observation que tous les modules > 500 lignes du projet ont effectivement bénéficié d'un split (ou d'une justification explicite).
- L'audit ne tourne PAS en pre-commit (volontaire — trop lent pour un hook qui doit rester < 5s). Il tourne en local via `just audit-strict` et **devrait** tourner en CI.

**À surveiller** :
- Si un projet humain ajoute > 5 whitelists dans un sprint, c'est un signal que la règle est mal calibrée (à revoir)
- Évolution naturelle : chaque nouvelle règle d'anti-pattern identifiée mérite un test unitaire + un commit dédié

## Workflow d'évolution

**Pour ajouter une nouvelle règle** :
1. Identifier l'anti-pattern (idéalement à partir d'un vrai bug observé en prod)
2. Implémenter le détecteur dans `src/core/audit.py` (préférer AST si parsing Python)
3. Ajouter au `AuditConfig.rules_enabled`
4. Ajouter ≥ 5 tests unitaires (positif, négatif, whitelist, edge cases)
5. Lancer l'audit sur le codebase actuel — corriger ou whitelister
6. ADR mineur ou note dans CHANGELOG

**Pour désactiver temporairement une règle** :
```python
config = AuditConfig(rules_enabled={"ORPHAN_TODO": False})
findings = run_audit(root, config)
```

**Pour bumper un seuil** (ex: max_file_lines 500 → 600) : juste passer
`AuditConfig(max_file_lines=600)`. À documenter en CHANGELOG si change durable.

## Alternatives considérées

1. **Utiliser uniquement ruff/mypy custom rules** : refusé. Ruff est excellent
   pour les règles génériques mais ne supporte pas les anti-patterns
   project-specific (ex: "agent Opus sans `# Opus :` à proximité"). Custom
   rules ruff sont possibles mais demandent du Rust + déploiement séparé.

2. **Pylint plugin** : refusé. Pylint est lourd et plus lent que notre AST
   walker minimaliste (~200ms sur tout le repo).

3. **Tests pytest qui font les vérifications** : refusé. Couplerait les
   anti-patterns aux tests métier — à terme on confond "code casse les tests"
   et "code casse les conventions". Audit séparé = clarté.

4. **Détection à la volée dans le base_agent** : refusé. L'audit doit pouvoir
   tourner SANS exécuter le code (statique pur). Sinon impossible en CI sans
   environnement complet.

5. **Pre-commit hook bloquant** : refusé pour l'instant. L'audit prend 1-2s
   sur le codebase actuel — trop lent pour un hook qui doit rester < 5s.
   Solution : `just audit-strict` à lancer manuellement avant PR + step CI.

## Sources

- ADR-016 (tier mixing) — la règle `OPUS_WITHOUT_JUSTIFICATION` matérialise sa politique
- ADR-019/020 (coverage) — pattern similaire de garde-fou auto-vérifié
- AST Python docs : https://docs.python.org/3/library/ast.html
- Bug réel découvert pendant Sprint LLL : 466 faux positifs résolus par switch regex → AST
