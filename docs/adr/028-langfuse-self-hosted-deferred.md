# ADR-028 — Langfuse self-hosted v3 differé (cloud uniquement)

**Statut :** Accepted
**Date :** 2026-05-22
**Sprint :** v0.7.0 audit zéro-dette

## Contexte

L'observabilité multi-agents repose sur Langfuse pour visualiser les traces (chaîne d'appels orchestrator → agents → outputs, durée, coût, tokens). Trois modes envisagés depuis le début :

1. **NO-OP** (défaut) — `LANGFUSE_PUBLIC_KEY` absent, `init_tracing()` retourne `False`, aucun appel réseau. Décorateur `@observe` se charge mais est inerte.
2. **Cloud Langfuse** — credentials renseignés, traces envoyées à `https://cloud.langfuse.com`. Aucune infra à maintenir, ~free tier suffit pour usage perso. **Statut : ✅ Opérationnel.**
3. **Self-hosted v3** — stack Docker complet (web + worker + ClickHouse + PostgreSQL + Redis + MinIO) déployée via `docker compose --profile observability up -d`. **Statut : ⛔ Non-fonctionnel.**

Le mode self-hosted v3 traîne depuis Phase 3 (mai 2026). `docker-compose.yml` ligne 53-59 le reconnaît explicitement :

> NOTE Phase 3 : la config Langfuse v3 a évolué — plusieurs env vars supplémentaires sont attendues par le worker/web (CLICKHOUSE_MIGRATION_URL, variantes S3 spécifiques, etc.) qui ne sont PAS encore mappées ici. Le stack démarre les 6 containers mais le worker ne réussit pas les migrations ClickHouse au premier boot.

Cet état mi-livré ouvre la porte à des configurations cassées chez les utilisateurs qui essaient `--profile observability`.

## Décision

**Geler le développement du Langfuse self-hosted v3 jusqu'à une décision produit ultérieure.** Trois conséquences immédiates :

1. **`docker-compose.yml`** : la stack `observability` est **annotée DEFERRED** avec un avertissement explicite en tête de section. Les containers ne sont pas retirés (un opérateur expérimenté peut toujours les lancer manuellement), mais la doc invite à utiliser Langfuse cloud à la place.

2. **`docs/runbook.md`** + **`README.md`** : référencer explicitement le mode cloud comme **canal recommandé**. Self-hosted = mode avancé non-supporté.

3. **`Settings.langfuse_host`** garde `http://localhost:3000` par défaut pour compatibilité historique, mais le `health_check` mentionne désormais "self-hosted v3 deferred (ADR-028)" quand l'URL pointe sur localhost et qu'aucun container Langfuse n'est joignable.

### Alternatives évaluées

| Option | Pourquoi rejetée |
|---|---|
| **Continuer à debugger v3** | Coût : 8-12 h estimées (ClickHouse migrations, S3 endpoints, worker queue). Bénéfice : zéro pour usage perso solo. Langfuse cloud fait le job pour $0. |
| **Downgrade vers Langfuse v2 self-hosted** | v2 est EOL (fin 2025), pas de patch sécurité. |
| **Remplacer par autre outil (Helicone, Phoenix, LangSmith)** | Migration des décorateurs `@observe` partout, perte des traces historiques. Coût élevé pour un gain incertain. |
| **Retirer complètement la stack docker-compose** | Risque de casser le workflow de quelqu'un qui aurait commencé à expérimenter. Conservation avec annotation DEFERRED = compromis. |

## Conséquences

### Positives

- **Plus d'illusion** : la doc d'aujourd'hui affirme honnêtement « self-hosted v3 cassé, utilisez le cloud ».
- **Coût d'opportunité libéré** : les 8-12 h estimées vont à des features productives (E2E Ollama, classifier LLM, audit zéro-dette).
- **Réactivation possible** : la stack reste référencée dans docker-compose, un futur sprint peut la reprendre avec les env vars manquantes documentées par l'amont Langfuse.

### Négatives / à surveiller

- **Dépendance cloud externe** pour l'observabilité : pas de souveraineté complète sur les traces. Acceptable pour usage perso ; un utilisateur entreprise devra trancher.
- **Risque que la stack obsolète accumule de la dette** : Langfuse v4 va sortir, le docker-compose annoté pointera sur v3 retiré. Mitigation : revue annuelle de l'ADR.

### Conditions de réactivation

Cet ADR sera reconsidéré si **au moins une** des conditions est remplie :

1. Un utilisateur du projet réclame explicitement le self-hosted (souveraineté des traces, RGPD interne).
2. Langfuse upstream publie une procédure d'install self-hosted v3 reproductible en 1 commande.
3. Une bascule vers un autre outil (LangSmith, Phoenix) devient préférable et nécessite un sprint d'observabilité.

## Métriques de suivi

À la prochaine version mineure (v0.8.0) :
- Vérifier qu'aucun utilisateur n'a ouvert d'issue « self-hosted v3 cassé » depuis ce gel.
- Vérifier que `LANGFUSE_HOST=http://localhost:3000` ne cause pas de timeouts cumulés dans les missions (le `init_tracing()` doit fail-fast et retomber en NO-OP).
