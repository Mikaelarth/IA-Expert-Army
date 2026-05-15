---
hide:
  - navigation
  - toc
---

# IA Expert Army

<p style="font-size: 1.2em; color: var(--md-default-fg-color--light);">
Une armée d'agents IA experts spécialisés qui collaborent comme une entreprise distribuée :
<strong>mémoire partagée vivante</strong>, <strong>évolution par expérience</strong>, <strong>autonomie sécurisée</strong>.
</p>

[![Tests](https://img.shields.io/badge/tests-573%20passing-brightgreen)](https://github.com/MikaelArth/IA-Expert-Army){ .md-button }
[![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen)](adr/020-coverage-ci-automation.md){ .md-button }
[![Audit](https://img.shields.io/badge/audit-0%20findings-brightgreen)](adr/022-codebase-audit-rules.md){ .md-button }
[![ADRs](https://img.shields.io/badge/ADRs-23-blueviolet)](adr/README.md){ .md-button }

---

## En 3 liens

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **[Getting Started](getting-started.md)**

    ---

    De zéro à ta première mission live en **5 minutes**. Et un smoke test sans
    coût API en 5 secondes pour voir ce que ça fait.

-   :material-server-network:{ .lg .middle } **[Operations](operations.md)**

    ---

    Mode autonome 24/7 sur VPS. Déploiement, garde-fous, notifications mobiles,
    backup, migration sans perte.

-   :material-sitemap:{ .lg .middle } **[Architecture](architecture.md)**

    ---

    Vue d'ensemble de l'architecture en 4 couches. Diagrammes Mermaid, état
    d'implémentation, points d'extension futurs.

</div>

---

## Promesse vérifiable

```bash
uv run python scripts/run_mission.py \
  --title "Endpoint /uptime" \
  --description "Crée un endpoint FastAPI GET /uptime qui retourne {seconds: float}..." \
  --apply --validate
# → mission APPROVED 0.93 → 2 fichiers écrits → 3/3 pytest dans sandbox PASSED
# → "Boucle qualité fermée : mission APPROVED + apply OK + sandbox pytest OK."
```

**Une commande.** Code généré, écrit sur disque, validé en sandbox Docker isolé, en ~100s pour ~0,50 $.

---

## Pourquoi ce projet est différent

Plutôt qu'**un** agent IA généraliste, **une équipe** d'agents spécialisés qui se passent
le travail comme une PME. Avec :

- :material-brain: **Mémoire partagée vivante** qui s'enrichit à chaque mission (RAG sémantique sur Chroma)
- :material-school: **Apprentissage par expérience** : skills auto-extraites des meilleurs épisodes, citées par les agents
- :material-shield-check: **Autonomie sécurisée** : 5 garde-fous (budget cap, killswitch, error rate, saturation, quality drift)
- :material-test-tube: **Boucle qualité fermée** : code → fichiers → sandbox pytest, en une commande

---

## Garanties auto-vérifiées

Pour qu'une régression atterrisse en `main`, il faut explicitement bypasser **trois portes** :

| Porte | Mécanisme | Sprint |
|---|---|---|
| **Coverage ≥ 90%** | `pyproject.toml` `fail_under = 90` + step CI dédié | [JJJ/KKK](adr/020-coverage-ci-automation.md) |
| **Anti-patterns = 0** | 5 règles AST-based (`audit_codebase.py --strict`) en CI + pre-commit | [LLL/QQQ](adr/023-audit-ci-pre-commit-integration.md) |
| **Smoke E2E sans coût** | `FakeAsyncAnthropic` simule toute la chaîne en 5s à chaque PR | [OOO](adr/021-smoke-e2e-tests.md) |

Beaucoup plus dur de dériver silencieusement.

---

## Les 4 guildes

<div class="grid cards" markdown>

-   :material-code-braces: **Engineering**

    Code, tests, infra. Architect + Developer + Reviewer + Security Auditor.

-   :material-magnify: **Research**

    Synthèse, veille, analyse. Lead + TechWatch + Synthesizer + Reviewer.

-   :material-feather: **Creative**

    Contenu (landing, email, blog). Strategist + Copywriter + Editor.

-   :material-briefcase: **Business**

    Roadmap, viabilité, conformité. PM + BA + Legal Reviewer.

</div>

Plus le **Chief Orchestrator** (routage), le **Quality Guardian** (peer review méta cross-guilde),
et la possibilité d'enchaîner cross-guildes via `MetaWorkflow`.

---

## Démarrage express

```bash
git clone https://github.com/MikaelArth/IA-Expert-Army.git
cd IA-Expert-Army
uv sync                      # ~30s
cp .env.example .env         # ajoute ANTHROPIC_API_KEY=sk-ant-...
uv run python scripts/health_check.py --quick
uv run pytest tests/integration/test_smoke_autonomous.py -v   # 5s, $0
```

Pour la suite : **[Getting Started](getting-started.md)**.
