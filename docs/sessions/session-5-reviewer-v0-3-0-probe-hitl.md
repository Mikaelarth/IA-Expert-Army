# Session 5 — Reviewer v0.3.0 + probe déterministe + clarification HITL

**Date** : 2026-05-21
**Branche** : `feat/ollama-backend`
**Objectif** : 3 lots conjoints
1. Étendre `code_reviewer.md` v0.2.0 → **v0.3.0** pour les findings Session 4 (paths fichiers, couverture cas demandés).
2. Construire un **script de probe déterministe** qui mesure si le Reviewer détecte le bug Session 2 sur input contrôlé — résout l'ambiguïté Session 4 où le Developer n'avait pas re-produit le bug.
3. **Clarifier le statut HITL** (primitive livrée vs garde-fou actif) pour respecter le contrat critère #3 ("aucun garde-fou neutralisé silencieusement").

---

## Lot 1 — Prompt code_reviewer v0.3.0

Diff sur `prompts/guilds/engineering/code_reviewer.md` :

1. **Frontmatter** : version `0.2.0 → 0.3.0`, entrée `revisions:` complétée.
2. **Tableau des critères** : nouvelle catégorie **"Conformité spec"** ajoutée en tête à 15% (transferts 5% depuis Correctness, 5% depuis Architecture-fit, 5% depuis Lisibilité).
3. **Nouvelle section "Conformité à la spec — OBLIGATOIRE avant de noter quoi que ce soit"** :
   - Sous-section "1. Paths des fichiers" : compare chaque fichier produit au path demandé dans la mission → finding `severity: major` si décalage.
   - Sous-section "2. Couverture des cas de tests demandés" : compte les cas demandés vs produits → finding `severity: major` si manque.
   - Anti-pattern "fusion de cas pour économiser des lignes" décrit explicitement (référence au comportement Session 4 où Developer a fusionné `ponctuation_multiple` + `espaces_multiples`).
4. **Règles de verdict APPROVED** : les pré-requis non-négociables passent à **2 items** (1: exécution mentale tests, 2: conformité spec vérifiée). Un path non conforme = major = pas APPROVED.

### Bug introduit + fixé Session 4 (rappel)

La leçon « ne jamais mettre de `:` non-quoté dans un string YAML de frontmatter » a été appliquée d'entrée — v0.3.0 utilise des tirets cadratin (`—`) pour le séparateur de description. Validation `yaml.safe_load` lancée avant tout commit (préventif depuis Session 4).

---

## Lot 2 — Probe déterministe : preuve directe que le nouveau prompt résout le bug Session 2

### Le script

`scripts/probe_reviewer.py` lance le `CodeReviewer` (`qwen2.5-coder:32b`) sur :
- **Input contrôlé** : le code+test bugué Session 2 *inchangé* (test `test_slugify_multiple_punctuation` qui attend `"-"`).
- **Pas de RAG ni de skills injectées** (isolation maximale — on teste UNIQUEMENT le pouvoir du system prompt v0.3.0 face à l'input).
- Architecture proposition reproduit fidèlement le format que le SoftwareArchitect aurait passé.
- Description de la mission injectée en `context._probe_mission_description` pour permettre la vérification de spec.

Le script imprime le verdict, le score, l'analyse "bug détecté oui/non" via heuristique (`_bug_was_detected`), et écrit la trace YAML complète dans `data/probes/<timestamp>_<case>.md`. Exit code 0 si bug détecté, 2 sinon → utilisable en CI manuel ou en regression test sur prompt.

### Le résultat — comparaison directe Session 2 (v0.1.0) ↔ Session 5 (v0.3.0)

| Métrique | Session 2 — Reviewer v0.1.0 | Session 5 — Reviewer v0.3.0 (probe) | Delta |
|---|---|---|---|
| **Verdict sur le code+test bugué** | `APPROVED` ❌ | `NEEDS_CHANGES` ✅ | **inversion** |
| **Quality score** | 0.93 | 0.75 | -0.18 (rigueur accrue) |
| **Bug `test_slugify_multiple_punctuation` détecté** | ❌ Non | ✅ Oui, finding explicite | preuve directe |
| **Required_action générée pour fixer le test** | ❌ Aucune | ✅ Oui | preuve directe |
| **Mention "exécution mentale" dans summary** | ❌ Non | ✅ Oui | preuve directe |
| **Durée Reviewer** | 245 s | 449 s | × 1.83 (introspection accrue) |

### Citation du Reviewer Qwen v0.3.0, mot pour mot

> *"Le test `test_slugify_multiple_punctuation` ne vérifie pas correctement le comportement attendu. **L'assertion doit refléter une chaîne vide au lieu de `"-"`.**"*
>
> `required_actions:`
> *"Modifier le test `test_slugify_multiple_punctuation` pour vérifier qu'il retourne une chaîne vide (`""`) et non `"-"`."*
>
> `summary:`
> *"Le code implémente la fonction `slugify` selon les spécifications et couvre les cas demandés, mais il y a des problèmes de conception qui nécessitent des corrections. **Une exécution mentale de tous les tests a été faite pour vérifier leurs exactitudes.**"*

**C'est la preuve empirique directe que le prompt v0.2.0+ résout le finding Session 2** — exactement le test que je m'étais engagé à mettre en place à la fin de Session 4 ("Action Session 5+ tracée : ajouter un test du Reviewer sur input contrôlé pour mesure directe et déterministe").

### Effet de bord observé : un faux positif

Le Reviewer v0.3.0 a aussi émis un finding `severity: major` sur la normalisation Unicode :

> *"L'étape de normalisation Unicode doit être effectuée avant la suppression des caractères combinants. Actuellement, les diacritiques ne sont pas correctement supprimés."*

**C'est faux.** Le code Session 2 fait bien `lower() → NFKD → drop combining → re.sub → strip`. NFKD EST appelé avant le filtre des combining marks. Le Reviewer a probablement confondu l'ordre en lisant le pipeline.

**Conclusion honnête** : le Reviewer v0.3.0 est plus rigoureux **et** plus zélé. Il catche les vrais bugs (test bugué) mais peut aussi inventer des problèmes qui n'existent pas. Trade-off attendu — c'est mieux qu'un Reviewer qui laisse tout passer, mais ça veut dire qu'un workflow `--apply` qui dépend du Reviewer pourrait déclencher des repair loops inutiles. **Action tracée Session 6+** : si on observe un taux élevé de faux positifs sur missions réelles, calibrer le prompt v0.3.0 → v0.4.0 avec un exemple de faux positif à éviter.

### Pourquoi pas un test pytest ?

Le probe prend 7-10 min sur `qwen2.5-coder:32b` sans GPU haut de gamme. Trop lent pour la suite pytest standard (qui doit rester sous 1 min). Le script reste donc à lancer manuellement (`uv run python scripts/probe_reviewer.py`) — la traçabilité est assurée par les fichiers horodatés dans `data/probes/`.

---

## Lot 3 — Clarification du statut HITL approvals

### Le problème

[ADR-014](../adr/014-hitl-approvals.md) avait livré la primitive `request_approval()` + son CLI dans le Sprint CCC (mai 2026), avec une promesse explicite de wiring dans les sprints DDD/EEE/FFF (apply_files, autonomous_run, killswitch). **Ces sprints n'ont jamais été exécutés.** La doc d'architecture présentait HITL comme "Livré mais non wiré aux workflows" — formulation ambiguë qui pouvait faire croire que c'était un wiring temporairement absent en attente d'un sprint imminent.

Le contrat 7 critères dit *"aucun garde-fou neutralisé silencieusement"*. HITL en l'état est neutralisé : la primitive existe mais aucun call site du repo ne l'appelle. Pour respecter le contrat, **il faut soit le wirer, soit clarifier explicitement que ce n'est plus un garde-fou auto**.

### La décision

Vague 1 du projet est "outil perso", pas SaaS multi-tenant. Le besoin HITL automatique sur chaque call site (qui aurait justifié les sprints DDD/EEE/FFF) est moins critique. **Décision Session 5 (cf. amendement ajouté à ADR-014)** :

1. La primitive `request_approval` **reste livrée et testée** (24 tests dans `tests/unit/test_approvals.py`).
2. **Aucun wiring auto-déclenché dans les workflows.** `--apply`, `autonomous_run`, `killswitch` ne lèvent jamais d'`ApprovalRequired` automatiquement.
3. **Usage actuel = manuel** : un humain (ou un script tiers) peut appeler `request_approval()` programmatiquement, et le suivi se fait via CLI (`just approvals`).
4. **Conséquence assumée** : HITL est désormais documenté dans `architecture.md` comme « **✅ Livré pour usage manuel · ⛔ PAS un garde-fou auto** » — pas comme l'un des 5 garde-fous autonomes opérationnels.
5. **Réactivation possible** : wirer une instrumentation HITL dans `apply_files.py` reste un sprint de ~2h. La primitive est prête.

### Modifications appliquées

- `docs/adr/014-hitl-approvals.md` : section **"Amendement Session 5 (2026-05-21)"** ajoutée en tête avec les 5 points ci-dessus.
- `docs/architecture.md` table des garde-fous : la ligne HITL passe de
  > ⚠️ Livré mais non wiré aux workflows
  à
  > ✅ Livré pour usage manuel · ⛔ **PAS un garde-fou auto**

C'est l'honnêteté épistémique qu'exige le contrat. Mieux vaut une promesse plus modeste mais vraie qu'une promesse ambiguë.

---

## Bilan Session 5

| Lot | Statut | Preuve |
|---|---|---|
| Prompt v0.3.0 (conformité spec) | ✅ Livré | Frontmatter YAML validé, sections ajoutées |
| Probe déterministe | ✅ Livré + ✅ Mesure positive | `data/probes/20260521T075027_bug-session-2.md` : verdict NEEDS_CHANGES, bug détecté |
| Clarification HITL | ✅ Livré | ADR-014 amendé, architecture.md cohérent |

### Score session : 9/10

**Premier ratio "promesse → mesure → preuve" complet du projet** :
- Session 2 a observé empiriquement un défaut (test bugué non détecté)
- Session 4 a tenté un fix par prompt engineering, mais n'a pas pu **mesurer directement** la résorption (le Developer n'a pas re-produit le bug)
- Session 5 a construit l'outil de mesure déterministe, exécuté, **et la mesure confirme la résorption**

C'est précisément ce que le projet promet (boucle d'amélioration observable) — et c'est désormais reproductible : si je remplace le prompt v0.3.0 par v0.1.0 et que je relance `scripts/probe_reviewer.py`, je dois obtenir APPROVED (régression mesurable).

Le -1 du 10/10 = le faux positif sur la normalisation Unicode (le Reviewer est devenu plus rigoureux mais aussi un peu trop zélé). Trade-off acceptable, à surveiller Session 6+.

---

## Actions tracées pour Session 6+

- Lancer 1 mission engineering réelle complète (pas un probe isolé) avec le prompt v0.3.0 pour mesurer si on a un taux de faux positifs problématique en conditions réelles.
- Mesurer aussi sur une mission **plus complexe** que slugify (e.g. endpoint FastAPI) — la zone de confort projet est 50-500 lignes, on n'a testé que les 50-100 lignes.
- Si faux positifs > 1 par mission : calibrer v0.3.0 → v0.4.0 avec exemple de faux positif à éviter.
- Critère contrat #6 ("Observable sans deviner") : décider du sort de Langfuse v3 (stabiliser self-hosted OU basculer sur cloud OU écrire un tracer JSON minimal). Le système marche aujourd'hui avec structlog, c'est suffisant pour usage perso, mais à clarifier dans la doc.
- Critère contrat #7 ("Recoverable en <10 min") : exercice de restore bout en bout (créer un backup, simuler une corruption, restorer, vérifier).
