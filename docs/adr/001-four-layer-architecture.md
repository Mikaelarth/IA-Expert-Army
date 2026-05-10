# ADR-001 — Architecture en 4 couches

**Statut :** Accepted
**Date :** 2026-05-10

## Contexte

Le projet vise une **armée d'agents IA experts** multi-domaines, autonome, à mémoire partagée et capacité d'évolution. Une architecture monolithique (un agent généraliste) ou plate (N agents indépendants sans hiérarchie) ne tiendrait pas la promesse :

- Un agent unique sature en complexité (trop de tâches hétérogènes dans un seul prompt) et reste limité par les capacités d'un seul appel LLM.
- N agents indépendants ne se coordonnent pas, dupliquent du travail, et n'ont pas de mécanisme commun pour la qualité finale.

Il faut un cadre qui permette : **spécialisation forte + coordination fiable + mémoire commune + évolution mesurable**.

## Décision

L'architecture est organisée en **4 couches**, du plus stratégique au plus opérationnel :

```
Couche 4 — APPRENTISSAGE & ÉVOLUTION
    Outcome tracking · Pattern mining · Few-shot library · Prompt refinement
                              ▲
Couche 3 — INFRASTRUCTURE PARTAGÉE
    Mémoire (Files + Vector + KG) · MCP · Bus · Sandbox · Observabilité
                              ▲
Couche 2 — LES 4 GUILDES SPÉCIALISÉES
    Engineering · Research · Creative · Business
                              ▲
Couche 1 — COMITÉ DE DIRECTION
    Chief Orchestrator · Chief of Staff · Quality Guardian · Budget Controller
```

**Règles de couche :**
- Une couche supérieure peut consommer les services de toutes les couches inférieures.
- Une couche inférieure n'a aucune connaissance de la couche supérieure.
- L'apprentissage (couche 4) observe sans intervenir directement dans le flux d'exécution.

## Conséquences

**Positives :**
- Spécialisation : chaque agent a un prompt et un modèle (Opus/Sonnet/Haiku) adapté à son rôle, économisant les coûts.
- Évolution : ajouter une guilde ne touche pas le comité de direction.
- Testabilité : chaque couche est testable indépendamment (mocks pour les couches inférieures).
- Lisibilité : la hiérarchie reflète une métaphore d'entreprise familière.

**Négatives / à surveiller :**
- Couches = couches d'indirection. Pour une mission triviale, le surcoût (latence, tokens) peut dépasser la valeur de la spécialisation. Mitigation : la Phase 1 garde un workflow linéaire simple, les optimisations viennent ensuite.
- Le Chief Orchestrator devient un point central : si son prompt est mal calibré, tout le système souffre. Mitigation : prompt versionné Git + A/B testing (Phase 5).

## Alternatives considérées

- **Agent unique généraliste :** rejeté → ne tient pas la promesse multi-domaines, sature en complexité.
- **Pattern peer-to-peer (tous les agents égaux) :** rejeté → pas de mécanisme d'arbitrage, conflits ingérables.
- **DAG explicite (workflow par mission) :** considéré, à introduire en Phase 3+ via LangGraph pour les missions complexes. Le pattern Supervisor + Workers (couches 1+2) reste valide à l'intérieur.
