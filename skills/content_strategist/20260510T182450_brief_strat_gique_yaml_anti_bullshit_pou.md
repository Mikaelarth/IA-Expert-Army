---
summary: 'Pour des audiences tech (CTO, tech leads, devs Python sceptiques), produire
  un brief YAML

  qui prescrit un ton pair-to-pair, des preuves chiffrées vérifiables, et bannit explicitement

  le vocabulaire marketing. La précision des anti-patterns vaut autant que les do_use.'
tags:
- copywriting-technique
- audience-tech-lead
- brief-strategique
- anti-marketing
- yaml-structure
sources:
- 20260510T181205_904151fb_content_strategist
- 20260510T181848_109e7ce2_content_strategist
- 20260510T182045_0447068e_content_strategist
sources_avg_score: 0.887
extracted_from: 3
skill_id: 20260510T182450_brief_strat_gique_yaml_anti_bullshit_pou
agent: content_strategist
title: Brief stratégique YAML anti-bullshit pour devs
created_at: '2026-05-10T18:24:50.899698+00:00'
---

## Résumé

Pour des audiences tech (CTO, tech leads, devs Python sceptiques), produire un brief YAML
qui prescrit un ton pair-to-pair, des preuves chiffrées vérifiables, et bannit explicitement
le vocabulaire marketing. La précision des anti-patterns vaut autant que les do_use.

## Patterns clés
- audience.who toujours décrit comme une scène concrète (le tech lead seul à 22h, le CTO qui scrolle entre 2 meetings) plutôt qu'un persona abstrait
- pain_or_desire formulé comme une fatigue/scepticisme par défaut, pas comme un manque que le produit comble
- proofs systématiquement typées (stat / démo / garantie / référence) avec contenu chiffré ou techniquement vérifiable
- tone.do_not_use plus long et plus précis que do_use — la valeur du brief est dans ce qui est interdit
- structure découpée section par section avec un champ intent qui explique le rôle narratif, pas juste le contenu
- anti_patterns nommés avec exemples textuels concrets entre guillemets ('Je suis ravi de partager...', 'Bienvenue dans l'aventure')

## Techniques
- Lister les superlatifs/jargon interdits avec exemples littéraux : 'révolutionnaire', 'game-changer', 'next-gen', 'paradigm shift'
- Imposer le tutoiement et l'impératif quand l'audience est dev (lance, vérifie, clone, audite)
- Citer la stack technique réelle dans proofs (sandbox Docker, pytest, ChromaDB, ADR) pour ancrer la crédibilité
- Bannir les hashtags génériques et emojis décoratifs ; tolérer 1 emoji fonctionnel max
- Inclure une mention honnête des limites/statut early dans le positionnement
- CTA unique et concret (étoile GitHub + lien doc) plutôt que CTA multiples qui dispersent

## Pièges évités
- Personas marketing fictifs ('imaginez Sarah, CTO débordée')
- Comparaisons nominales agressives avec concurrents (LangChain, CrewAI) — risque de flame
- CTA mou ('thoughts?', 'dites-moi ce que vous en pensez')
- Storytelling personnel forcé en intro ('il y a 6 mois je me demandais...')
- Promesses au-delà du livrable réel — chaque promesse doit être adossée à une preuve listée
- Réutiliser le pitch d'un canal sur un autre (la landing ≠ l'email post-clone ≠ le post LinkedIn)

## Template d'exemple

```
audience:
  who: |
    <scène concrète : qui, où, quand, dans quel état mental>
  pain_or_desire: |
    <fatigue/scepticisme + signal recherché>
  prior_knowledge: expert
objective:
  primary_action: <1 action mesurable>
  secondary_outcomes: [<2-3 effets de halo>]
positioning:
  promise: |<promesse bornée, vérifiable>
  angle: |<contre-position vs l'écosystème>
proofs:
  - {type: stat|démo|garantie|référence, content: <fait chiffré ou vérifiable>}
tone:
  adjectives: [direct, technique, <3e>]
  do_use: [<patterns linguistiques concrets>]
  do_not_use: [<superlatifs/jargon interdits avec exemples>]
structure:
  - {section: <nom>, intent: |<rôle narratif>}
anti_patterns: [<formules à bannir, citées littéralement>]
constraints: {length, format, language}
```

## Sources
- 20260510T181205_904151fb_content_strategist (score 0.91)
- 20260510T181848_109e7ce2_content_strategist (score 0.88)
- 20260510T182045_0447068e_content_strategist (score 0.87)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
title: Brief stratégique YAML anti-bullshit pour devs
agent: content_strategist
tags:
  - copywriting-technique
  - audience-tech-lead
  - brief-strategique
  - anti-marketing
  - yaml-structure
summary: |
  Pour des audiences tech (CTO, tech leads, devs Python sceptiques), produire un brief YAML
  qui prescrit un ton pair-to-pair, des preuves chiffrées vérifiables, et bannit explicitement
  le vocabulaire marketing. La précision des anti-patterns vaut autant que les do_use.
key_patterns:
  - "audience.who toujours décrit comme une scène concrète (le tech lead seul à 22h, le CTO qui scrolle entre 2 meetings) plutôt qu'un persona abstrait"
  - "pain_or_desire formulé comme une fatigue/scepticisme par défaut, pas comme un manque que le produit comble"
  - "proofs systématiquement typées (stat / démo / garantie / référence) avec contenu chiffré ou techniquement vérifiable"
  - "tone.do_not_use plus long et plus précis que do_use — la valeur du brief est dans ce qui est interdit"
  - "structure découpée section par section avec un champ intent qui explique le rôle narratif, pas juste le contenu"
  - "anti_patterns nommés avec exemples textuels concrets entre guillemets ('Je suis ravi de partager...', 'Bienvenue dans l'aventure')"
prior_knowledge_default: expert
techniques:
  - "Lister les superlatifs/jargon interdits avec exemples littéraux : 'révolutionnaire', 'game-changer', 'next-gen', 'paradigm shift'"
  - "Imposer le tutoiement et l'impératif quand l'audience est dev (lance, vérifie, clone, audite)"
  - "Citer la stack technique réelle dans proofs (sandbox Docker, pytest, ChromaDB, ADR) pour ancrer la crédibilité"
  - "Bannir les hashtags génériques et emojis décoratifs ; tolérer 1 emoji fonctionnel max"
  - "Inclure une mention honnête des limites/statut early dans le positionnement"
  - "CTA unique et concret (étoile GitHub + lien doc) plutôt que CTA multiples qui dispersent"
pitfalls_avoided:
  - "Personas marketing fictifs ('imaginez Sarah, CTO débordée')"
  - "Comparaisons nominales agressives avec concurrents (LangChain, CrewAI) — risque de flame"
  - "CTA mou ('thoughts?', 'dites-moi ce que vous en pensez')"
  - "Storytelling personnel forcé en intro ('il y a 6 mois je me demandais...')"
  - "Promesses au-delà du livrable réel — chaque promesse doit être adossée à une preuve listée"
  - "Réutiliser le pitch d'un canal sur un autre (la landing ≠ l'email post-clone ≠ le post LinkedIn)"
example_template: |
  audience:
    who: |
      <scène concrète : qui, où, quand, dans quel état mental>
    pain_or_desire: |
      <fatigue/scepticisme + signal recherché>
    prior_knowledge: expert
  objective:
    primary_action: <1 action mesurable>
    secondary_outcomes: [<2-3 effets de halo>]
  positioning:
    promise: |<promesse bornée, vérifiable>
    angle: |<contre-position vs l'écosystème>
  proofs:
    - {type: stat|démo|garantie|référence, content: <fait chiffré ou vérifiable>}
  tone:
    adjectives: [direct, technique, <3e>]
    do_use: [<patterns linguistiques concrets>]
    do_not_use: [<superlatifs/jargon interdits avec exemples>]
  structure:
    - {section: <nom>, intent: |<rôle narratif>}
  anti_patterns: [<formules à bannir, citées littéralement>]
  constraints: {length, format, language}
sources_count: 3
```

</details>
