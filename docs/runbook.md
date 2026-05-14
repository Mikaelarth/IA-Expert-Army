# Runbook — IA-Expert-Army en mode autonome

> Quoi faire quand quelque chose casse, sans paniquer. Ordre des sections par
> fréquence observée et urgence opérationnelle.

**Convention** : chaque incident a une section structurée :
- **Symptômes** : ce que tu vois (logs, comportement)
- **Diagnostic rapide** : 1-2 commandes pour confirmer
- **Action** : ce que tu fais pour rétablir
- **Prévention** : comment réduire la probabilité de récidive

---

## 1. Budget journalier bloqué ($50/$50 atteint)

**Symptômes :**
- Toute nouvelle mission lève `BudgetExceeded`.
- `scripts/autonomous_run.py` s'arrête sur garde-fou #1.
- Le rapport mentionne `budget restant $X < seuil $5`.

**Diagnostic rapide :**

```powershell
just budget                       # statut courant
uv run python scripts/budget.py status
```

**Action — 3 options :**

1. **Attendre minuit UTC** : le `BudgetController` rotate automatiquement (l'ancien jour est archivé dans `history`, le nouveau jour repart à 0).

2. **Reset manuel** (si urgence légitime, p.ex. validation Phase 6 d'une journée demain) :
   ```powershell
   just budget-reset                 # ou : uv run python scripts/budget.py reset
   ```
   ⚠ Le reset perd la trace du dépassement du jour. Préfère bumper le cap.

3. **Bumper le cap** dans `.env` :
   ```
   DAILY_BUDGET_USD=100.0
   ```
   Effet immédiat au prochain lancement de `get_settings()` (singleton). Pour les services déjà chargés, redémarrer.

**Prévention :**
- Le rapport `daily_digest` indique le `% consommé` quotidien. Si on flirte avec > 80% plusieurs jours, le cap est sous-dimensionné pour l'usage réel.
- Pour les sessions de dev intensives, bump explicite à $50 puis revenir à $10 en prod stable.

---

## 2. Killswitch engagé accidentellement

**Symptômes :**
- Toute mission échoue immédiatement avec `FAILED:killswitch.engaged`.
- `data/.killswitch` existe.

**Diagnostic :**

```powershell
just killswitch                   # status — affiche 'engaged' ou 'free'
cat data/.killswitch              # voir la raison + timestamp
```

**Action :**

```powershell
just killswitch release           # supprime le fichier
```

Vérifier ensuite que les `data/budget_state.json.lock` n'ont pas été laissés orphelins (lock fichier auto-cleanup au gracieux, mais pas en SIGKILL) :

```powershell
ls data/*.lock 2>$null && rm data/*.lock
```

**Prévention :**
- Le killswitch est volontairement low-friction (un seul fichier sentinel). Si on l'engage par erreur en testant, on le release en 5 secondes.
- En autonomous_run, le killswitch est checké AVANT chaque mission — l'engager pendant un run laisse la mission courante finir, puis stop.

---

## 3. Anthropic API down / 5xx persistants

**Symptômes :**
- Logs : `HTTPStatusError 5xx` ou `APIConnectionError` répétés.
- BaseAgent retourne `success=False` avec `error="..."` sur plusieurs agents consécutifs.
- `autonomous_run` peut déclencher garde-fou #3 (error rate > 30%).

**Diagnostic rapide :**

```powershell
# Test direct sans passer par le projet :
uv run python -c "from anthropic import Anthropic; c = Anthropic(); print(c.messages.create(model='claude-haiku-4-5-20251001', max_tokens=10, messages=[{'role':'user','content':'hi'}]))"
```

**Action :**

1. **Vérifier le status Anthropic** : https://status.anthropic.com
2. **Si transient** : le SDK fait 2 retries auto (Sprint VV.1) + le `autonomous_run` arrête après 30% d'erreurs sur 5 missions — on attend, on relance.
3. **Si persistant** : engager le killswitch pour éviter de brûler du budget en retries inutiles :
   ```powershell
   just killswitch engage
   ```
4. Quand l'API est revenue : `just killswitch release` + relancer.

**Prévention :**
- Settings configurables `ANTHROPIC_MAX_RETRIES=2` et `ANTHROPIC_TIMEOUT_SECONDS=300` (cf. Sprint VV.1).
- Daily digest expose le coût quotidien — un pic anormal (10× la normale) en soirée = signe de retry storm, à investiguer.

---

## 4. Saturation persistante d'un agent (max_tokens systématiquement atteint)

**Symptômes :**
- Logs warning `agent.output.saturated` sur le même agent plusieurs missions de suite.
- Verdicts NEEDS_CHANGES répétés sur cet agent.
- `autonomous_run` peut déclencher garde-fou #4 (saturation > 20% sur 5 dernières).

**Diagnostic :**

```powershell
# Cherche les épisodes saturés du jour :
uv run python -c "
from src.memory.file_memory import FileMemory
from src.core.config import get_settings
m = FileMemory(get_settings().project_root / 'data' / 'memory')
for p in m.list_episodes():
    rec = m.read_episode(p)
    if rec.metadata.get('saturated'):
        print(p.name, rec.metadata.get('agent'), rec.metadata.get('tokens_out'), '/', rec.metadata.get('max_tokens'))
"
```

**Action :**

1. Identifier l'agent saturé (ex. `business_analyst`) et son `tokens_out` actuel (ex. 6144).
2. Bumper son `DEFAULT_MAX_TOKENS` dans son fichier d'agent (ex. `src/guilds/business/agents.py`).
3. Mettre à jour le test régression dans `tests/unit/test_<guild>_agents.py` avec un commentaire pointant l'incident.
4. Cf. **ADR-005** pour la procédure complète et la liste historique des incidents.

**Prévention :**
- ADR-005 documente les seuils par défaut + la procédure d'escalade par agent.
- Tous les reviewers/synthesizers sont à 8192 minimum.

---

## 5. Meta-mission stuck en NEEDS_CHANGES infini

**Symptômes :**
- Un sous-mission cross-guildes retourne NEEDS_CHANGES après son repair loop.
- Verdict global de la meta = NEEDS_CHANGES.

**Diagnostic — comprendre QUI demande quoi :**

```powershell
# Lire le résumé meta-mission
cat data/memory/meta_missions/<uuid>.md

# Et les sub-missions individuelles
cat data/memory/missions/<sub_uuid>.md
```

Le résumé `review_summary` du reviewer (Editor/Legal/etc.) explique en mots ce qui bloque.

**Action :**

1. **Si le verdict est légitime** (l'output a vraiment des manques structurels) : c'est attendu. Le repair loop a fait son travail. Affiner la mission utilisateur et relancer.

2. **Si le verdict est suspect** (le reviewer demande quelque chose d'absurde) : c'est un bug de prompt. Inspecter le system prompt du reviewer + les exemples (skills) injectés.

3. **Pour bypasser temporairement** : forcer la guilde manquante en mode single-guild (`run_mission.py --guild engineering`) et compiler manuellement.

**Prévention :**
- Repair loop élargi (Sprint PP/SS/WW) résout les cas où l'output amont n'évoluait pas. Si NEEDS_CHANGES persiste après ça = problème de prompt, pas de wiring.
- Les workflows ont une boucle max 1× (pas 2× ou plus) pour ne pas brûler du budget sur une mission impossible.

---

## 6. Sandbox Docker indisponible

**Symptômes :**
- `health_check` : `Docker daemon DOWN`.
- `run_mission --validate` ou `apply_mission --validate` : `Sandbox indisponible`.
- Exception `SandboxUnavailable` dans les logs.

**Diagnostic :**

```powershell
docker ps                         # doit lister les containers (vide OK)
# Si "Cannot connect to the Docker daemon" :
docker info | head -20
```

**Action :**

1. **Docker Desktop arrêté (Windows)** : ouvrir Docker Desktop, attendre l'indicateur vert.
2. **Image `iaa-sandbox` absente** :
   ```powershell
   just sandbox-build
   ```
3. **Container zombie** : `docker ps -a` puis `docker rm <id>`.

**Prévention :**
- Le sandbox est CRITIQUE pour `--validate` (Phase 8 quality loop). Sans lui, on perd la validation pytest automatique.
- `health_check` quotidien (idéalement via cron) signale tôt si Docker est down.

---

## 7. Chroma DB corrompue ou incohérente

**Symptômes :**
- Logs : `chromadb errors` au démarrage du `VectorMemory`.
- RAG ne retourne plus de précédents pertinents (count ~ 0 alors qu'on a des épisodes).
- `health_check` : nombre d'épisodes indexés ≠ nombre d'épisodes sur disque.

**Diagnostic :**

```powershell
just health                       # voir VectorMemory count vs FileMemory count
ls data/chroma                    # voir si le dossier existe et a du contenu
```

**Action — reset complet (safe car Chroma = INDEX, source = FileMemory) :**

```powershell
# 1. Sauvegarder le dossier Chroma au cas où
Move-Item data/chroma data/chroma.bak.$(Get-Date -Format yyyyMMdd)
# 2. Re-indexer tous les épisodes existants
just reindex
# (ou : uv run python scripts/reindex_episodes.py)
```

`reindex_episodes.py` parcourt tous les épisodes sur disque et re-pousse leurs embeddings dans une Chroma fraîche. La source de vérité reste les fichiers markdown — Chroma n'est qu'un cache sémantique.

**Prévention :**
- Chroma in-process (pas server) → moins de surface d'attaque, mais besoin de reindex si on corromp le dossier.
- Les épisodes markdown sont sous Git (sauf gitignore actuel — à reconsidérer si on veut du backup automatique).
- **Backup quotidien** (Sprint BBB) : `just backup` capture skills + memory + prompts. Cf. section 11 ci-dessous.

---

## 8. MCP server inaccessible depuis Claude Desktop

**Symptômes :**
- Claude Desktop n'affiche plus les 6 tools MCP (`search_episodes`, `list_recent_missions`, etc.).
- Logs Claude Desktop : `MCP server connection failed`.

**Diagnostic :**

```powershell
# Test direct du serveur MCP en stdio
uv run python scripts/run_memory_search_mcp.py
# (devrait rester en attente de stdin sans crash — Ctrl+C pour quitter)
```

**Action :**

1. **Config Claude Desktop incorrecte** : vérifier `claude_desktop_config.json` :
   ```json
   {
     "mcpServers": {
       "ia-expert-army-memory": {
         "command": "uv",
         "args": ["run", "python",
                  "D:/PROJETS/IA-Expert-Army/scripts/run_memory_search_mcp.py"]
       }
     }
   }
   ```
2. **Redémarrer Claude Desktop** (ferme complètement, pas juste minimize).
3. **Path Python ou uv incorrect** : tester `uv --version` dans un terminal — si pas trouvé, c'est un PATH issue.

**Prévention :**
- `scripts/run_memory_search_mcp.py` est testé indirectement par les unit tests du `_build_server`.
- Smoke test occasionnel : lancer le serveur manuellement et vérifier qu'il accepte des requêtes via un client MCP de test.

---

## 9. Lock orphelin BudgetController

**Symptômes :**
- `BudgetController.record(...)` lève `TimeoutError: Impossible d'acquérir le lock`.
- Un fichier `data/budget_state.json.lock` traîne sur disque sans process associé.

**Diagnostic :**

```powershell
ls data/*.lock                    # voir le fichier orphelin
Get-Item data/budget_state.json.lock | Select-Object LastWriteTime
```

**Action :**

```powershell
rm data/budget_state.json.lock
```

**Prévention :**
- Le code (`_file_lock` dans `src/core/budget.py`) détecte automatiquement les locks > 2× timeout (10s par défaut) et les force. Donc ce cas est rare.
- En cas de SIGKILL répété (Ctrl+C trop agressif), un lock peut traîner — le cleanup manuel ne devrait pas être nécessaire plus d'une fois par mois.

---

## 10. Perte totale skills/ ou data/memory/ — restoration depuis backup

**Symptômes :**
- `skills/` vide ou corrompu (suppression accidentelle, disque mort)
- `data/memory/episodes/` ou `missions/` perdu
- Le système boot mais a perdu tout son apprentissage

**Diagnostic :**

```powershell
just backup-list                  # liste les backups disponibles
# Vérifier qu'il existe au moins 1 backup récent (< 7 jours idéalement)
```

**Action — procédure de restoration :**

```powershell
# 1. ARRÊTER toute exécution (mode autonome inclus)
just killswitch engage

# 2. Sauvegarder l'état CORROMPU (au cas où on aurait besoin d'investiguer)
just backup
# (Le ZIP du dossier vide / corrompu sera utile pour comprendre le sinistre)

# 3. Restore depuis le dernier backup sain
just restore-latest               # interactive, demande confirmation
# Ou pour un backup spécifique :
just restore-from data/backups/iaa-backup-20260514T120000.zip

# 4. Si l'état actuel est partiel/incohérent, écraser avec --overwrite
uv run python scripts/restore.py --latest --overwrite

# 5. Reconstruire l'index Chroma (qui n'est PAS dans le backup)
uv run python scripts/reindex_episodes.py

# 6. Sanity check
just health

# 7. Si tout est OK, relâcher le killswitch
just killswitch release
```

**Prévention :**
- **`just backup` quotidien** via cron / Task Scheduler. Rotation auto sur 7 jours.
- Le backup exclut explicitement les `.env` (secrets) et `data/chroma/` (recalculable). Sauvegarder le `.env` séparément (password manager).
- **Tester la restoration** au moins 1× par trimestre — un backup non-testé est un backup mort. Procédure : `just backup` → restore vers `/tmp/recovery_test/` → `diff -r` avec project root.

---

## 11. Demandes d'approbation HITL en attente

**Symptômes :**
- Un script bloque sur `ApprovalRequired` (mode blocking=True)
- Une mission autonome a skippé une étape critique en pending
- Le `daily_digest` mentionne des approvals pending non décidés

**Diagnostic :**

```powershell
just approvals                        # liste les demandes pending (FIFO)
just approval-show <id>               # détail d'une demande (context, qui demande, quand)
```

**Action — décider :**

```powershell
# Approuver (raison optionnelle mais recommandée pour audit)
just approve <id> "Backup pris à 15h25, overwrite OK"

# Rejeter (raison OBLIGATOIRE)
just reject <id> "Audit sécu pas encore fait, attendre"
```

**Action — historique :**

```powershell
just approvals-history                # 20 dernières décisions, plus récente en premier
```

**Prévention :**
- Définir une politique d'auto-approve dans `data/approvals/policy.yml` pour les cas évidents (cf. ADR-014 et exemples dans la doc du module).
- En mode autonome, configurer `wait_for_decision(timeout=N)` adapté au cycle de revue humaine (par défaut 300s = 5 min).
- `data/approvals/` doit être backupé (sera intégré au backup Sprint BBB dans la prochaine itération).

---

## 12. Variables d'env shell qui shadowent `.env` (récurrent sur cette machine)

**Symptômes :**
- `health_check` : `ANTHROPIC_API_KEY absent ou invalide` alors que `.env` contient la clé.
- Les scripts CLI plantent avec `TypeError: Could not resolve authentication method`.

**Diagnostic — confirmer l'overshadowing :**

```powershell
$env:ANTHROPIC_API_KEY            # PowerShell
# ou en bash :
echo $ANTHROPIC_API_KEY
```

Si la variable existe (vide ou avec valeur ≠ `.env`), c'est elle qui prend le pas (pydantic-settings priorité env > .env).

**Action :**

```powershell
# PowerShell
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
# Bash
unset ANTHROPIC_API_KEY
```

Puis relancer le script. Pour les sessions Claude Code spécifiquement, le bash sandbox injecte parfois `ANTHROPIC_API_KEY=""` — toujours préfixer les commandes API-dépendantes par `unset ANTHROPIC_API_KEY &&`.

**Prévention :**
- Idéalement, le code devrait vérifier que la clé n'est pas vide avant d'instancier AsyncAnthropic. À ajouter dans `Settings` validators.
- Documenté dans la memory cross-session de l'utilisateur (`feedback_windows_python_setup.md`).

---

## Procédure de crise globale

Si **3 incidents simultanés** ou un comportement inexpliqué :

```powershell
# 1. ARRÊT
just killswitch engage

# 2. SNAPSHOT (avant tout changement)
$ts = Get-Date -Format yyyyMMddTHHmmss
Compress-Archive -Path data,prompts,skills,.env -DestinationPath "data/backups/crisis_$ts.zip"

# 3. DIAGNOSTIC
just health                       # voir la première chose qui casse
just budget
ls data/autonomous_runs/ | Select-Object -Last 3
```

Puis appliquer la procédure du runbook correspondant. **Toujours commencer par le killswitch** : ça ne coûte rien et ça arrête l'hémorragie de budget si une mission est partie en boucle.

---

## Index des références croisées

| Sujet | Source |
|---|---|
| Architecture 4 couches | [docs/architecture.md](architecture.md) |
| Décisions structurelles | [docs/adr/](adr/) |
| Saturation max_tokens | [ADR-005](adr/005-saturation-detection-and-prevention.md) |
| MetaWorkflow cross-guildes | [ADR-009](adr/009-meta-workflow-cross-guilds.md) |
| Validation Phase 6 (autonomous) | [ADR-010](adr/010-phase-6-autonomous-validation.md) |
| Sandbox trade-off | [ADR-008](adr/008-sandbox-readonly-tradeoff.md) |
