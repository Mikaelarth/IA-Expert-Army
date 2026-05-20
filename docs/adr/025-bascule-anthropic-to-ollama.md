# ADR-025 — Bascule du backend LLM d'Anthropic vers Ollama local

**Date :** 2026-05-20
**Statut :** Accepted
**Supersedes :** partiellement [ADR-016](016-tier-mixing-strategy.md) (mapping de modèles obsolète)

---

## Contexte

Jusqu'à v0.3.0-alpha, tous les agents (~18 rôles répartis sur 4 guildes +
direction) appelaient l'API Claude via le SDK `anthropic` (`AsyncAnthropic`).
Stratégie de tier mixing (ADR-016) : Opus pour les rôles à jugement
(Architect, QG, BA…), Sonnet pour l'opérationnel (Developer, Reviewer…),
Haiku pour le bulk (TechWatch). Coût observé : ~$19 sur 16 missions APPROVED
en dev, mission étalon FastAPI APPROVED 0.93 en 12 min pour $1.74.

Cette dépendance pose 3 problèmes :

1. **Coût récurrent** : chaque mission consomme du crédit API, ce qui
   contraint la cadence de développement et bloque les usages haut volume
   (queue autonome 24/7, batch de N missions).
2. **Dépendance externe** : connectivité réseau requise, latence variable,
   risque de changement tarifaire/policy côté fournisseur.
3. **Souveraineté des données** : prompts + outputs transitent par un tiers,
   y compris pour des projets privés où le code/contenu est sensible.

## Décision

**Bascule complète vers Ollama local** (https://ollama.com) via son endpoint
OpenAI-compatible (`http://localhost:11434/v1`). Le SDK officiel `openai`
sert de client générique — pas de dépendance au SDK `ollama-python` natif,
ce qui ouvre la porte à OpenRouter / LM Studio / vLLM plus tard sans rework.

**Mapping des 3 tiers** (par défaut, `.env` configurable) :

| Tier | Modèle Ollama | Rôles |
|------|---------------|-------|
| `model_strategic` | `qwen2.5:32b` | Architect, ChiefOrchestrator, QualityGuardian, BusinessAnalyst, ResearchLead, ContentStrategist |
| `model_operational` | `qwen2.5-coder:32b` | BackendDeveloper, CodeReviewer, SecurityAuditor, Copywriter, Editor, DocumentSynthesizer, ResearchReviewer, LegalReviewer, ProjectManager, SkillExtractor, MetaDecomposer |
| `model_bulk` | `qwen2.5:14b` | TechWatch |

**Choix Qwen2.5** : meilleur compromis qualité/taille pour le français + YAML
structuré à ces tailles (alternatives évaluées : Llama 3.3 70B trop lourd,
Mistral Small moins bon en français).

## Conséquences

### Code

- `pyproject.toml` : dep `anthropic>=0.40.0` → `openai>=1.50.0` (version 0.4.0)
- `src/core/config.py` : `anthropic_api_key/max_retries/timeout` → `ollama_base_url/api_key/max_retries/timeout`. Champs `model_strategic/operational/bulk` conservés avec nouveaux défauts. `daily_budget_usd` défaut 0.0 (Ollama gratuit).
- `src/orchestrator/base_agent.py` : `AsyncAnthropic` → `AsyncOpenAI(base_url=ollama_base_url, api_key="ollama")`. Adaptation du shape :
  - `client.messages.create(model, max_tokens, system, messages)` → `client.chat.completions.create(model, max_tokens, messages=[{role:"system",...}, {role:"user",...}])`
  - `response.content[0].text` → `response.choices[0].message.content`
  - `response.usage.input_tokens/output_tokens` → `response.usage.prompt_tokens/completion_tokens`
  - `response.stop_reason == "max_tokens"` → `response.choices[0].finish_reason == "length"` (la détection de saturation porte désormais sur `"length"`)
- 9 agents qui acceptent un client en paramètre : signature `client: AsyncAnthropic | None` → `client: AsyncOpenAI | None`
- `src/core/pricing.py` : `estimate_cost()` retourne `0.0` (pas de pricing par token en local). Structure conservée pour permettre un retour à un backend payant sans rework.
- `src/core/audit.py` : règle `OPUS_WITHOUT_JUSTIFICATION` désactivée par défaut (plus de tier payant à protéger). Réactivable explicitement si remplacement par un backend cloud.
- `.env.example` : variables `OLLAMA_BASE_URL/API_KEY/TIMEOUT_SECONDS`, nouveaux défauts modèles Qwen.

### Tests

- `tests/integration/test_smoke_autonomous.py` : `FakeAsyncAnthropic` → `FakeAsyncOpenAI` qui expose `client.chat.completions.create` et lit le system prompt depuis `messages[0]` (au lieu du param `system`). Le pattern de détection d'agent par H1 reste inchangé.
- `tests/unit/test_base_agent.py` : réécriture complète des mocks (shape OpenAI) + tests saturation sur `finish_reason="length"` + tests retry/timeout pointent sur `ollama_*`.
- `tests/unit/test_config.py` : réécriture — défauts `ollama_*` + plus de validation `sk-ant-*`.
- Autres tests : les `monkeypatch.setenv("ANTHROPIC_API_KEY", ...)` historiques restent inoffensifs (`extra="ignore"` dans SettingsConfigDict les absorbe silencieusement). Nettoyage cosmétique possible plus tard.

### Scripts

- `scripts/hello_agent.py` : réécrit pour AsyncOpenAI/Ollama
- `scripts/check_setup.py` : check du SDK `openai` (au lieu de `anthropic`)
- `scripts/health_check.py` : nouveau check `check_ollama_daemon` qui ping `/api/tags` et vérifie que les 3 modèles configurés sont pullés
- CI (`.github/workflows/ci.yml`) : variable `ANTHROPIC_API_KEY` retirée

### Documentation

- `README.md`, `docs/getting-started.md`, `docs/deploy.md`, `docs/operations.md`, `docs/runbook.md` : références API Anthropic → Ollama local. Install : `https://ollama.com` + `ollama pull qwen2.5:32b qwen2.5-coder:32b qwen2.5:14b`.
- `CHANGELOG.md` : entrée v0.4.0 "Breaking change — bascule Ollama".

### Trade-offs assumés

| Aspect | Avant (Anthropic) | Après (Ollama Qwen) |
|---|---|---|
| Coût par mission | $0.50-$1.74 | $0 |
| Latence par appel | 5-30s | 30-300s selon hardware/modèle |
| Qualité jugement (QG/BA) | Excellent (Opus) | Dégradé (qwen2.5:32b ≈ Sonnet) |
| Qualité code (Developer) | Excellent (Sonnet) | Bon (qwen2.5-coder:32b) |
| Souveraineté données | Tiers | 100% local |
| Setup | Clé API | Daemon Ollama + ~40 Go modèles |

La mission étalon FastAPI (12 min sur Sonnet) devrait passer à 25-40 min sur
Qwen 32B local sans GPU haut de gamme. Le QG/BA seront bruités vs Opus — à
valider sur 3-5 missions réelles. Les prompts (`prompts/**/*.md`) sont
conservés tels quels en v1 : le parser `extract_yaml` est tolérant aux
divergences de format. Adaptation si saturations/échecs observés.

## Alternatives considérées

- **Hybride configurable** (`BACKEND=anthropic|ollama` via `.env`) : rejeté
  pour éviter la dette de maintenance de 2 backends côte à côte. Reversible
  via git si besoin.
- **SDK natif `ollama-python`** : rejeté au profit d'`openai`, plus standard
  et compatible avec OpenRouter/LM Studio/vLLM sans rework.
- **Modèles plus petits** (Qwen 7B/14B) : rejetés pour le défaut — qualité
  insuffisante sur QG et BusinessAnalyst. Restent configurables via `.env`
  pour les machines modestes.
- **Llama 3.3 70B** : rejeté pour le défaut — empreinte mémoire ~40 Go vs
  ~20 Go pour Qwen 32B, gains qualité non décisifs sur les tâches du repo.

## Métriques de suivi (post-bascule)

À mesurer sur les 5 premières missions réelles après bascule :
- Durée moyenne par mission (Engineering / Research / Creative / Business)
- Taux APPROVED vs avant
- Score qualité moyen vs avant
- Fréquence de saturation (`finish_reason == "length"`)
- Fréquence de YAML mal-formé (parser fallback déclenché)

Si dégradation sévère sur QG ou BusinessAnalyst : pull Llama 3.3 70B et
remapper `model_strategic`.
