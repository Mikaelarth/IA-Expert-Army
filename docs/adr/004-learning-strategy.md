# ADR-004 — Stratégie d'apprentissage : RAG + skills synthétisées, pas de fine-tuning

**Statut :** Accepted
**Date :** 2026-05-10

## Contexte

L'utilisateur veut que l'équipe **« évolue collectivement, s'auto-entraîne, et apprenne grâce à l'expérience qu'elle aura avec le temps »**. C'est le cœur de sa vision.

Mais l'état de l'art 2026 impose une contrainte technique : **les LLM ne mettent pas à jour leurs poids à l'exécution**. "Apprendre" au sens biologique (modifier ses neurones en continu) est impossible. Toute solution doit donc *simuler* l'apprentissage par d'autres mécanismes.

Plusieurs voies existent :
1. **Mémoire externe + RAG** : l'agent cherche dans ses précédents avant chaque action.
2. **Skills extraites** : un méta-agent synthétise des « recettes » à partir des succès passés.
3. **Few-shot dynamique** : injection d'exemples réussis dans chaque prompt.
4. **Refinement de prompts** : les system prompts sont versionnés et modifiés sur la base des outcomes.
5. **Fine-tuning périodique** : entraînement réel sur les meilleures missions (coûteux, complexe, lent).

## Décision

L'apprentissage se fait par **trois mécanismes combinés**, **sans fine-tuning** :

1. **RAG sur épisodes** (Phase 2 ✅) : chaque agent stocke ses sorties dans Chroma. Avant un nouvel appel, il récupère les K plus pertinentes (sémantiquement) et les injecte dans son user message.
2. **Skills auto-générées** (Phase 5 ✅) : un job nightly (`PatternMiner` + `SkillExtractor`) analyse les top-K épisodes par rôle, demande à Opus de synthétiser une « skill » markdown structurée (patterns, techniques, pièges, template), et la stocke dans `skills/<agent>/`. Les agents lisent ces skills (sémantiquement les plus pertinentes) à chaque exécution.
3. **Prompts versionnés Git** : les system prompts sont dans `prompts/`, versionnés. La modification se fait par PR humaine en Phase 5, A/B testing automatique prévu en Phase 5+.

**Le fine-tuning est explicitement reporté hors-scope** pour les raisons suivantes :
- Coût élevé (formation + hébergement d'un modèle fine-tuné).
- Complexité opérationnelle (pipeline MLOps, évaluation, rollback).
- Bénéfice incertain tant qu'on n'a pas saturé les gains des 3 mécanismes ci-dessus.
- Un fine-tuning prématuré gèle un comportement qu'on pourrait améliorer plus simplement par prompt.

## Conséquences

**Positives :**
- Effet observable de l'apprentissage **dès la 3ᵉ mission** (validé : Architect cite skill + précédents et adapte intelligemment).
- Coût marginal très faible : le mining nightly coûte ~$0.70 par run, quel que soit le volume futur.
- Réversibilité totale : supprimer une skill ou un épisode défait son influence immédiatement.
- Auditabilité : chaque skill cite ses épisodes sources, chaque réponse cite ses précédents.

**Négatives / à surveiller :**
- Le contexte des appels LLM grossit avec les skills + précédents → coût en tokens augmente. Mitigation : truncation par skill (800 chars), top-K limité à 2 par défaut.
- La qualité des skills dépend de la qualité de l'extraction par Opus. Si une skill est mauvaise, elle pollue les futures missions. Mitigation : skills versionnées Git, supprimables, A/B testing prévu en Phase 5+.
- Pas de "vraie" mise à jour des poids → l'équipe ne deviendra jamais expert d'un domaine au sens d'un humain qui a fait sa thèse. Acceptable : la spécialisation par prompt + skills suffit pour les tâches opérationnelles.

## Alternatives considérées

- **Fine-tuning Claude via Anthropic :** considéré → reporté. Sera réévalué quand on aura > 100 missions de qualité dans un domaine homogène.
- **RLHF / DPO sur les feedbacks utilisateur :** considéré → reporté. Nécessite une infrastructure ML séparée et beaucoup de données.
- **Ne rien faire, faire confiance au modèle de base :** rejeté → ne tient pas la promesse de "l'équipe évolue avec le temps".
- **Mémoire courte (in-context only, pas de DB) :** rejeté → perte totale entre sessions, incompatible avec l'objectif long-terme.
