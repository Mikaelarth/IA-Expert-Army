# ADR-012 — Security Auditor (audit OWASP / secrets / pratiques défensives)

**Statut :** Accepted
**Date :** 2026-05-14
**Commits associés :** Sprint AAA

## Contexte

Le master plan prévoit en Couche 2 (Guild Engineering) un agent **Security Auditor** spécialisé en OWASP, secrets et vulnérabilités. Promesse non livrée jusqu'à v0.2.0.

Le `CodeReviewer` existant juge la **qualité technique** du code (propreté, tests, design). Mais il n'a typiquement pas le réflexe d'attraper :
- Vulnérabilités OWASP Top 10 (injection, XSS, deserialization unsafe, etc.)
- Secrets hardcodés (clés API, mots de passe en clair)
- Pratiques défensives manquantes (`eval()` avec input externe, `shell=True`, etc.)

En mode autonome, où l'utilisateur ne valide pas chaque mission, l'absence de ce garde-fou = risque de propager des skills polluées par du code vulnérable et de livrer des outputs APPROVED par la guilde mais exploitables.

## Décision

Introduire le **`SecurityAuditor`** comme agent **complémentaire** au `CodeReviewer` dans le `Workflow` Engineering :

- **Modèle** : Sonnet (`model_operational`) — 5× moins cher qu'Opus, suffisant pour les patterns OWASP standards.
- **Position dans le pipeline** : après `CodeReviewer`, **uniquement sur missions APPROVED**. Pas la peine d'auditer un code que la guilde a déjà refusé.
- **Effet sur le verdict** : si l'audit produit ≥1 finding de sévérité `BLOCKER` ou `MAJOR`, le verdict guilde APPROVED est downgradé à `NEEDS_CHANGES`. Les findings sont injectés dans le contexte du `repair loop` (Architect + Developer y répondent).
- **Findings `MINOR` / `NIT`** : informatifs, le verdict reste APPROVED.
- **Activable** via `Settings.enable_security_auditor` (défaut `False` — opt-in).

### Sémantique des sévérités

| Sévérité | Critère | Effet |
|---|---|---|
| **BLOCKER** | Vuln exploitable avec PoC, secret réel hardcodé, OWASP critical | Downgrade APPROVED → NEEDS_CHANGES |
| **MAJOR** | Pratique défensive importante manquante (input validation, etc.) | Idem (downgrade) |
| **MINOR** | Hygiène sécurité à améliorer | Informatif, verdict reste APPROVED |
| **NIT** | Suggestion d'amélioration sans impact immédiat | Idem |

### Pourquoi Sonnet et pas Opus

Testé mentalement et tranché : les patterns OWASP sont **structurels et reconnaissables**, pas du discernement subtil comme le Quality Guardian. Sonnet identifie sans peine SQL injection, eval() unsafe, secrets hardcodés. Économie de 5× justifiée. Si l'observation de N missions révèle des faux négatifs systématiques (un BLOCKER raté ≠ un finding MINOR conservé), bumper à Opus avec un commentaire pointant l'incident.

### Pourquoi ne pas remplacer CodeReviewer

Les 2 agents ont des focus orthogonaux :
- CodeReviewer : "le code est-il propre/testable/maintenable ?"
- SecurityAuditor : "le code est-il sûr ?"

Un code propre peut être vulnérable (SQL injection bien indentée reste une SQL injection). Un code sale peut être sûr (logique défensive verbeuse mais correcte). Les fusionner = un agent qui fait mal les deux jobs.

### Pourquoi ne pas l'appliquer hors Engineering

- Research, Creative, Business produisent du texte (synthèses, copy, plans) — pas de surface d'attaque code-level.
- Le pattern d'audit méta cross-guilde est déjà couvert par le Quality Guardian (ADR-011).
- Si une mission cross-guildes a une sub-mission Engineering, son SecurityAuditor s'applique normalement (l'opt-in se cascade via Settings).

## Conséquences

**Positives :**
- Promesse Phase 4 du master plan livrée pour la Guild Engineering.
- Pattern repair loop existant (Sprint SS) **réutilisé naturellement** : les findings security sont injectés en contexte aux 3 agents v2 sans modification de structure.
- Coût additionnel maîtrisé : ~$0.05-0.10 par mission APPROVED Engineering (Sonnet, 4096 max tokens).
- Skill `security_auditor` auto-générable par le `PatternMiner` (whitelist mise à jour).

**Négatives / à surveiller :**
- **Couplage Workflow ↔ SecurityAuditor** : le `Workflow` Engineering importe directement `SecurityAuditor` + `has_downgrade_findings`. Acceptable car symétrique au pattern existant (le Workflow importe déjà les 4 autres agents). Si on multiplie les auditeurs spécialisés (perf, accessibilité, etc.), refactor possible en `auditors: list[BaseAgent]`.
- **Faux positifs possibles sur fixtures de test** : le prompt exclut explicitement les `sk-ant-test-12345` et `password = "fake-for-test"` mais Sonnet peut être trop zélé sur du code de tests générés. À surveiller sur les premières missions et raffiner le prompt si > 10% des findings sont sur des fixtures évidentes.
- **Pas d'audit sur les missions cross-guildes meta** : le SecurityAuditor s'applique à la **sub-mission** Engineering individuelle, pas au livrable global de la meta-mission. Si une meta-mission produit un livrable engineering + business plan qui exposerait des secrets dans des screenshots du business plan, ce n'est pas attrapé. v2 : étendre le QG (ADR-011) pour signaler ce cas.

## Alternatives considérées

- **SecurityAuditor en parallèle du CodeReviewer (asyncio.gather)** : rejeté pour v1 — gain de latence ~30s mais complexité de gestion d'erreur (l'un peut planter, l'autre OK). Mieux à implémenter une fois le pattern de base validé.
- **Override automatique du verdict guilde sans repair loop** : rejeté — un BLOCKER de sécurité mérite que Architect/Developer y répondent, pas juste un rejet final. Le repair loop existant est l'outil naturel pour ça.
- **Audit sur TOUTES les missions (pas uniquement APPROVED)** : rejeté — pour les NEEDS_CHANGES/REJECTED, le code va de toute façon être révisé. Auditer en plus = double coût pour zéro bénéfice marginal.
- **Audit par Bandit/Semgrep static analysis au lieu d'un agent LLM** : reporté. Bandit/Semgrep produisent du bruit (faux positifs très nombreux) et ne comprennent pas le contexte sémantique. v2 possible : combiner static analysis (rapide, exhaustif sur les patterns connus) + LLM auditor (sémantique, contextual). Pour v1, le LLM seul est l'investissement minimal pour la valeur maximale.
- **Opus au lieu de Sonnet** : voir section « Pourquoi Sonnet ».

## Pour la suite

- **CLI `--sec` flag** dans `run_mission.py` (similaire au `--qg` Sprint ZZ.1) — activer le SecurityAuditor par mission, indépendamment de la Setting globale. Quick win 30 min.
- **Métriques SecurityAuditor dans `daily_digest`** : compteur findings par sévérité, distribution OWASP catégories. Permet de voir si le code généré régresse en sécurité sur le temps.
- **PatternMiner — skill `security_auditor`** : exemple de "ce qu'un bon audit ressemble". Naturellement minable une fois N missions ont des audits APPROVED par le QG (cf. Sprint ZZ.2 filter).
- **Static analysis hybrid** : `pre-commit` hook qui lance Bandit/Semgrep en amont du LLM auditor, pour ne pas payer un appel API pour ce qu'un linter peut attraper.
