# Getting Started — IA Expert Army en 5 minutes

> De zéro à ta première mission live (~$0.50). Si tu veux juste regarder ce que ça fait sans dépenser un cent, va à **[Étape 4 — Smoke test](#étape-4--smoke-test-sans-coût-api)**.

---

## Prérequis

- **Windows / macOS / Linux** (testé Windows 11, Ubuntu 22.04+, macOS 14)
- **Python 3.12+** (sera installé par `uv` si absent)
- **Git**
- **Docker Desktop** *(optionnel, requis seulement pour `--validate` qui lance pytest dans un sandbox Docker)*
- **Une clé API Anthropic** ([console.anthropic.com](https://console.anthropic.com))

---

## Étape 1 — Installation (2 min)

```bash
# 1. Clone le repo
git clone https://github.com/MikaelArth/IA-Expert-Army.git
cd IA-Expert-Army

# 2. Installe uv (le package manager Python ultra-rapide)
# Linux/macOS :
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows PowerShell :
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 3. Installe les dépendances Python
uv sync
```

`uv sync` télécharge ~80 packages en 30-60 secondes.

---

## Étape 2 — Configurer la clé API (1 min)

```bash
# Linux/macOS
cp .env.example .env

# Windows
copy .env.example .env
```

Ouvre `.env` et remplis **uniquement** :

```bash
ANTHROPIC_API_KEY=sk-ant-api03-...   # https://console.anthropic.com
```

Tout le reste a des valeurs par défaut sensées. Tu pourras revenir éditer plus tard.

---

## Étape 3 — Vérifier l'installation (30 s)

```bash
uv run python scripts/health_check.py --quick
```

Tu dois voir un tableau avec **tous les checks verts ou skip** (les SKIP sont normaux : Docker / Langfuse non démarrés). Si quelque chose est rouge, le message d'erreur t'oriente.

```
┌────────────────┬──────────────────────────────┬──────────┐
│ Setup          │ Python 3.12+                 │    OK    │ 3.14.4
│ Setup          │ Settings + clé API           │    OK    │ Opus / Sonnet / Haiku
│ Couche 2       │ 4 workflows importables      │    OK    │ Engineering + Research + Creative + Business
│ Couche 3       │ FileMemory                   │    OK    │ 0 missions · 0 épisodes
│ ...
│ Notification   │ Notifier config              │   SKIP   │ NOTIFY_WEBHOOK_URL absent (notifier en NO-OP)
│ Documentation  │ ADRs index cohérent          │    OK    │ 23 ADRs indexés
└────────────────┴──────────────────────────────┴──────────┘
```

---

## Étape 4 — Smoke test (sans coût API)

Pour voir ce que fait le système **sans dépenser un cent**, lance la suite de tests intégration qui simule des missions complètes avec un faux client Anthropic :

```bash
uv run pytest tests/integration/test_smoke_autonomous.py -v
```

En 5 secondes tu verras passer :
- Une mission Engineering complète (Orchestrator → Architect → Developer → Reviewer → APPROVED)
- Une mission Research (Lead → TechWatch → Synthesizer → Reviewer)
- Le routage automatique vers la bonne guilde

C'est l'équivalent d'une vraie mission qui aurait coûté ~$0.50, mais en **0 cent et 5 secondes**.

> **Pourquoi ça marche** : `tests/integration/test_smoke_autonomous.py` utilise `FakeAsyncAnthropic` qui détecte l'agent appelant via le H1 de son system prompt et renvoie une réponse canon réaliste. Cf. [ADR-021](adr/021-smoke-e2e-tests.md).

---

## Étape 5 — Premier vrai agent (~$0.03)

Le Chief Orchestrator se présente — coût : un café (1 cent) :

```bash
uv run python scripts/hello_agent.py
```

Tu vois la réponse de Claude Opus 4.7 dans le terminal. C'est ton premier agent activé.

---

## Étape 6 — Première vraie mission (~$0.50)

Voici la mission canonique qui prouve que tout marche :

```bash
# Optionnel mais recommandé : build l'image sandbox (3 min, une seule fois)
uv run python scripts/check_sandbox.py --build

# La mission
uv run python scripts/run_mission.py \
  --title "Endpoint /uptime" \
  --description "Crée un endpoint FastAPI GET /uptime qui retourne {seconds: float} via time.monotonic. Inclus tests pytest." \
  --apply --validate
```

Attendu (après ~2 min) :
- ✅ `mission APPROVED 0.93`
- ✅ `2 fichiers écrits` dans le repo
- ✅ `3/3 pytest dans sandbox PASSED`
- ✅ `Boucle qualité fermée : mission APPROVED + apply OK + sandbox pytest OK`

**Une commande. Code généré, écrit sur disque, validé en sandbox isolé.**

---

## Et après ?

| Tu veux… | Va voir |
|---|---|
| Lancer en autonome 24/7 sur un VPS | [docs/operations.md](operations.md) |
| Comprendre l'architecture en 4 couches | [docs/architecture.md](architecture.md) |
| Quoi faire quand quelque chose casse | [docs/runbook.md](runbook.md) |
| Décisions techniques structurantes | [docs/adr/](adr/) (23 ADRs) |
| Réduire le coût Anthropic | [ADR-016 — Tier mixing](adr/016-tier-mixing-strategy.md) |
| Notifications mobiles (Discord/Telegram) | [ADR-018 — Notifications mobiles](adr/018-mobile-notifications.md) |

---

## Troubleshooting démarrage

| Problème | Cause probable | Fix |
|---|---|---|
| `uv: command not found` | uv pas dans le PATH | Relancer le terminal après l'install ; ou `source ~/.bashrc` |
| `health_check.py` → Settings + clé API : FAIL | `ANTHROPIC_API_KEY` absent ou invalide | Vérifier `.env`, format `sk-ant-api03-...` |
| Smoke test échoue avec "ModuleNotFoundError" | `uv sync` n'a pas tourné | Relancer `uv sync` |
| `--validate` skippé silencieusement | Docker pas installé / pas démarré | Démarrer Docker Desktop OU `ENABLE_SANDBOX=false` dans `.env` |
| Mission échoue sur "BudgetExceeded" | Plafond `DAILY_BUDGET_USD` atteint | Augmenter dans `.env` (défaut 50€) ou attendre minuit UTC |
| Tests intégration `test_migrate_vps.py` skippés | bash absent (Windows pur sans Git Bash) | Comportement attendu — Git Bash livré avec Git suffit |

Pour les incidents en production / mode autonome, voir [docs/runbook.md](runbook.md).

---

## Aller plus loin avec le système

Une fois familier avec les bases :

```bash
# Daily digest des missions du jour (gratuit, intégré)
uv run python scripts/daily_digest.py

# Lance une mission cross-guildes (water-tracker style)
uv run python scripts/run_mission.py --meta \
  --title "MVP water-tracker app" \
  --description "Crée une mini app de suivi d'hydratation avec landing page, code, et plan business. ..."

# Mining nightly : extrait des skills depuis les épisodes APPROVED
uv run python scripts/nightly_learning.py

# Audit anti-pattern (5 règles, ~1s sur tout le repo)
uv run python scripts/audit_codebase.py
```

Toutes les commandes ont un `--help`. Le [README.md](../README.md) liste les outils CLI principaux.
