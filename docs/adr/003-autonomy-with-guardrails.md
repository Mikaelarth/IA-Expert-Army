# ADR-003 — Mode opérationnel : autonome avec garde-fous obligatoires

**Statut :** Accepted
**Date :** 2026-05-10

## Contexte

L'utilisateur a explicitement choisi le **mode pleinement autonome** (face aux options *interactif* / *semi-autonome* / *autonome*). Cela signifie que l'équipe doit pouvoir traiter des missions sans validation humaine en boucle. Mais "autonome" ne signifie pas "sans garde-fous" : un agent qui peut écrire du code, exécuter des commandes, appeler des APIs, dépenser de l'argent en tokens, doit être encadré.

Sans garde-fous, le coût d'un seul incident (boucle infinie d'appels LLM, exécution destructrice, exfiltration accidentelle) dépasse largement la valeur produite par 100 missions réussies.

## Décision

10 garde-fous **non négociables**, implémentés progressivement :

| # | Garde-fou | Phase | Statut |
|---|---|---|---|
| 1 | Sandbox Docker pour exécution de code | 3 | ✅ code-complete (sandbox runner + Dockerfile) |
| 2 | Filesystem restreint (whitelist `src/`, `tests/`, `scripts/`, `docs/`, `prompts/`, `skills/`) | 1.5 | ✅ implémenté dans `apply_files` |
| 3 | Pas d'accès réseau par défaut, whitelist explicite | 3 | ✅ container `network=none` |
| 4 | Hard cap budget API journalier | 6 | 🚧 en cours |
| 5 | Circuit breakers sur taux d'erreur | 6 | 🚧 prévu |
| 6 | Approbation humaine forcée pour : prod deploy, dépenses > seuil, suppressions massives, envois externes | 6 | 🚧 prévu |
| 7 | Logs immutables (Langfuse) | 3 | ⏭ docker-compose prêt, intégration en Phase 3 finition |
| 8 | Killswitch global (sentinel file ou Redis topic) | 6 | 🚧 en cours |
| 9 | Daily digest envoyé à l'utilisateur | 6 | 🚧 en cours |
| 10 | Backups automatiques mémoire + skills (Git) | — | ✅ via versioning Git natif |

**Règle d'or :** un nouveau type d'action (autoriser un nouveau MCP server, élargir un whitelist, augmenter un cap) **doit** s'accompagner d'un nouveau garde-fou ou d'une révision de cet ADR.

## Conséquences

**Positives :**
- L'utilisateur peut lâcher l'équipe sur une mission longue (heures, voire jours) en confiance.
- Les incidents sont contenus (rayonnement limité par sandbox + whitelist).
- Toute dépense est traçable et plafonnée.

**Négatives / à surveiller :**
- Les garde-fous ajoutent de la latence (validation, sandbox spin-up) — acceptable pour le bénéfice sécuritaire.
- Le mode "pleinement autonome" sans intervention reste théorique tant que daily digest + killswitch ne sont pas en place. La Phase 6 finalise cela.
- Les garde-fous peuvent générer des faux positifs (refus légitimes mal interprétés). Mitigation : logs détaillés des refus pour analyse post-mortem.

## Alternatives considérées

- **Mode interactif (validation à chaque étape) :** rejeté par l'utilisateur — cela contredit l'objectif d'autonomie et tue la productivité.
- **Mode semi-autonome (validation finale seulement) :** plus prudent, gardé en option via le flag `--apply` (par défaut dry-run dans `run_mission.py`).
- **Pas de garde-fous, foi en l'IA :** rejeté immédiatement — état de l'art 2026 démontre que les LLM hallucinent encore et que les coûts API peuvent exploser.
