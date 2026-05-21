# ADR-014 — HITL formalisé (Human-In-The-Loop approvals)

**Statut :** Accepted — **primitive livrée v1, wiring auto explicitement reporté (cf. amendement Session 5 ci-dessous).**
**Date :** 2026-05-14
**Commits associés :** Sprint CCC

## Amendement Session 5 (2026-05-21) — statut wiring clarifié

Les sprints DDD/EEE/FFF mentionnés en bas de cet ADR (wiring `apply_files` / `autonomous_run` / `killswitch`) n'ont jamais été exécutés. Le projet est passé en mode "outil perso" (cf. choix utilisateur Session 0 et [ADR-025](025-bascule-anthropic-to-ollama.md)) — le besoin de garde-fou HITL automatique sur chaque call site est moins critique que dans un scénario multi-utilisateur. **Décision** :

1. **La primitive `request_approval` reste livrée et testée** (24 tests dans `tests/unit/test_approvals.py`).
2. **Aucun wiring auto-déclenché dans les workflows livrés ce jour.** Le mode `--apply` écrit directement sur disque (avec whitelist + path traversal défense de `src/tools/apply_files.py`), sans pré-approbation HITL. Idem `autonomous_run.py`, `killswitch.py`.
3. **Usage actuel = manuel**, via la CLI :
   ```bash
   just approvals               # liste pending
   just approval-show <id>      # détail
   just approve <id> "raison"   # approuve
   just reject <id> "raison"    # rejette
   ```
   Un script tiers peut créer un `request_approval()` programmatiquement s'il veut imposer un point de contrôle, mais aucun script du repo ne le fait nativement.
4. **Conséquence assumée** : HITL est listé dans la doc d'architecture comme « **livré, usage manuel uniquement, garde-fou automatique non opérationnel** » — pas comme un garde-fou actif des 5 garde-fous autonomes. Le mode autonome 24/7 reste protégé par les 5 garde-fous existants (budget, killswitch, error rate, saturation, quality drift) qui sont eux opérationnels.
5. **Réactivation possible** : si un besoin concret apparaît (ex : un agent qui veut écrire dans `src/api/main.py` existant en production), wirer une instrumentation HITL dans `apply_files.py` est un sprint de ~2h. La primitive est prête.

Cette honnêteté épistémique évite la fiction d'un garde-fou actif qui ne l'est pas. Le contrat critère #3 (« aucun garde-fou neutralisé silencieusement ») est ainsi respecté par la transparence du statut.

---

## Contexte

Le mode autonome (`scripts/autonomous_run.py`) a 5 garde-fous (budget floor, killswitch, error rate, saturation rate, quality drift) qui **stoppent** le système quand un seuil est dépassé. Mais entre « tout va bien » et « tout s'arrête », il manque un état intermédiaire : **« cette action mérite une validation humaine, mais ne mérite pas un arrêt complet »**.

Cas concrets identifiés où ce niveau intermédiaire serait précieux :

| Cas | Action | Sans HITL | Avec HITL |
|---|---|---|---|
| 1 | `run_mission --apply --force` qui va écraser `src/api/main.py` (existant, non-skill) | Silence + overwrite | Approval requis, l'utilisateur voit ce qui sera écrasé |
| 2 | Meta-mission qui s'annonce > $5 (cumul des sub-missions estimé) | Silence + run | Approval requis, l'utilisateur valide la dépense |
| 3 | `just killswitch release` après engagement | Pas de trace de qui/pourquoi | Approval logué avec user + reason |
| 4 | Skill auto-extraite avec score 0.97 sur 1 seul épisode | Promotion silencieuse | Approval pour promouvoir au statut "best practice" |
| 5 | Nouvelle MCP tool exposée à un client externe | Pas de check | Approval avant activation |

Sans mécanisme HITL formalisé, on a deux choix :
- **Soft** : ne rien protéger → risque opérationnel (overwrite accidentel, dérive coûts)
- **Hard** : bloquer durablement → mauvaise UX, le système s'arrête sur des cas légitimes

Le HITL résout : on **demande**, l'humain décide, le système reprend. Avec audit trail.

## Décision

Module `src/core/approvals.py` qui implémente une primitive `request_approval()` + un store fichier YAML + une CLI de gestion.

### Modèle de données

```yaml
# data/approvals/pending/<uuid>.yml
approval_id: 4e5f...
event_type: file_overwrite
context:
  path: src/api/main.py
  size_bytes: 12345
  proposed_action: overwrite_with_force
requested_at: '2026-05-14T15:30:00+00:00'
requested_by: run_mission.py
status: PENDING
blocking: false
```

Après décision, le fichier est déplacé vers `data/approvals/decided/<uuid>.yml` avec :

```yaml
status: APPROVED  # ou REJECTED ou EXPIRED
decided_at: '2026-05-14T15:35:00+00:00'
decided_by: alice  # getpass.getuser() ou 'policy:<rule>' si auto-approve
reason: "OK car backup pris à 15:25"
```

### API publique

- `request_approval(store, event_type, context, blocking=False, policy=None)` → `ApprovalRequest`
  - Retourne l'objet ; si policy match → status=APPROVED direct ; sinon PENDING.
  - `blocking=True` : si non auto-approuvé, lève `ApprovalRequired` (caller décide).
- `decide(store, approval_id, approved, decided_by, reason)` → `ApprovalRequest | None`
- `wait_for_decision(store, approval_id, timeout_seconds)` → `ApprovalRequest`
  - Bloque jusqu'à décision OU timeout (marque EXPIRED).
- `load_policy(root)` / `find_matching_rule(...)` pour l'auto-approve.

### Politique d'auto-approve

`data/approvals/policy.yml` (optionnel) :

```yaml
auto_approve:
  - event_type: file_overwrite
    paths_regex: "^skills/"
    rationale: "Skills auto-générées, écrasement par mining = OK"
  - event_type: budget_exceed
    max_usd: 2.0
    rationale: "Tolérance auto < $2"
```

L'auto-approve est volontairement minimal en v1 — l'humain garde la main sur tout ce qui n'est pas explicitement listé.

### CLI ergonomie

```bash
just approvals                          # liste pending
just approvals-history                  # historique decided
just approval-show <id>                 # détail (context JSON)
just approve <id> "reason"              # approuve
just reject <id> "reason obligatoire"   # rejette (reason obligatoire pour traçabilité)
```

### Wiring dans les call sites — v2 (volontairement reporté)

**v1 livre uniquement le mécanisme**, sans wiring dans les producteurs (run_mission.py, autonomous_run.py, killswitch.py). Rationale :

1. Le mécanisme est testable seul (24 tests) → garantit la robustesse de la primitive avant qu'elle ne soit utilisée partout.
2. Le wiring demande une décision politique pour CHAQUE call site (que faire si l'approval est PENDING en mode autonome ? bloquer la queue ? skip cette mission ? attendre N minutes ?). Trop de décisions en parallèle = risque d'erreurs.
3. Les premiers utilisateurs (toi sur cette machine) peuvent déjà créer manuellement des `request_approval` dans des scripts custom si besoin urgent.

Sprints suivants prévus :
- **DDD** : wire dans `apply_files.py` (`--force` overwrite hors `skills/`)
- **EEE** : wire dans `autonomous_run.py` (skip + log si pending au démarrage)
- **FFF** : wire dans `killswitch.py` (release nécessite approval, engage non)

## Conséquences

**Positives :**
- Trail d'audit complet : chaque action sensible laisse une trace YAML horodatée + signée (decided_by).
- Politique d'auto-approve permet de **réduire la friction sur les cas évidents** sans sacrifier l'audit.
- Le store fichier (pas de DB) → portable, debuggable avec `cat`, backup-able automatiquement (cf. ADR-013 si on l'inclut dans `data/approvals/`).
- `wait_for_decision` avec timeout + status EXPIRED → pas de blocage infini.

**Négatives / à surveiller :**
- **Latence humaine** : si l'humain ne répond pas vite, les approvals s'accumulent. Mitigation : timeout `wait_for_decision` (défaut 300s) + status EXPIRED.
- **YAML approval files = surface d'attaque** : un attaquant qui écrirait directement dans `data/approvals/decided/<id>.yml` avec status APPROVED contournerait le mécanisme. v2 : signer les decisions avec HMAC sur une clé locale.
- **Pas de notification active** : l'humain doit lancer `just approvals` pour voir. v2 : notification Slack/email/desktop.
- **Pas de wiring v1** : la valeur n'est pas immédiate jusqu'aux sprints suivants. Acceptable car la primitive est non-régressive (n'introduit aucun appel implicite tant qu'on ne wire pas).

## Alternatives considérées

- **Base SQLite pour les approvals** : rejeté. Surcomplique. Le volume est faible (< 100 pending simultanés réalistes), un fichier YAML par approval suffit largement.
- **Politique implicite "tout APPROVED par défaut"** : rejeté. Ça revient à ne pas avoir de HITL.
- **Politique implicite "tout REJECTED par défaut"** : rejeté. Trop friction-heavy pour un MVP.
- **Mécanisme async via Redis pub/sub** : reporté. Le store fichier suffit jusqu'à ce qu'on ait du multi-process concurrent.
- **Notification active dès la v1** (Slack webhook obligatoire) : reporté. La CLI `just approvals` est suffisante pour un seul utilisateur. La notification deviendra critique en multi-tenant ou prod 24/7.
- **HMAC signature des décisions** : reporté en v2. La menace est crédible mais le risque actuel est limité (le projet n'a qu'un utilisateur sur sa machine personnelle).

## Pour la suite

- **DDD** : wire dans `apply_files.py` — `--force` hors `skills/` déclenche `request_approval(blocking=True)`.
- **EEE** : `autonomous_run.py` — au démarrage, si des `pending` matchent un event_type "critical", la queue ne démarre pas. Si pending arrive en cours de run, le tick suivant skip et notifie.
- **FFF** : `killswitch.release()` demande approval avec context = {reason, engaged_since}.
- **Notification Slack webhook** : `Settings.slack_webhook_url` + un `notify()` appelé après chaque `request_approval`.
- **HMAC signature** : ajouter `signature: <hex>` sur chaque décision, vérifié au read.
- **Inclusion `data/approvals/` dans les backups** : revoir ADR-013 pour inclure ce dossier (historique légal des décisions, utile en audit).
