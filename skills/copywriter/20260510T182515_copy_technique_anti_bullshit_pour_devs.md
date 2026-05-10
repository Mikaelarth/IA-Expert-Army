---
summary: 'Recette de copy pour audience technique exigeante (devs, équipes post-POC)
  : attaque factuelle qui qualifie le lecteur, preuves chiffrées contextualisées,
  ton tutoyant impératif sans superlatifs, CTA unique ou couplé. Le copywriter livre
  toujours le texte + un bloc de notes meta qui flag les déviations du brief et les
  preuves manquantes.'
tags:
- copywriting
- technical-audience
- developer-marketing
- honest-positioning
- cta-minimal
sources:
- 20260510T181227_904151fb_copywriter
- 20260510T181906_109e7ce2_copywriter
- 20260510T182103_0447068e_copywriter
sources_avg_score: 0.887
extracted_from: 3
skill_id: 20260510T182515_copy_technique_anti_bullshit_pour_devs
agent: copywriter
title: Copy technique anti-bullshit pour devs
created_at: '2026-05-10T18:25:15.773579+00:00'
---

## Résumé

Recette de copy pour audience technique exigeante (devs, équipes post-POC) : attaque factuelle qui qualifie le lecteur, preuves chiffrées contextualisées, ton tutoyant impératif sans superlatifs, CTA unique ou couplé. Le copywriter livre toujours le texte + un bloc de notes meta qui flag les déviations du brief et les preuves manquantes.

## Patterns clés
- Attaque qui qualifie l'audience plutôt que d'accrocher (sous-titre "Pour les équipes qui ont dépassé le POC", "Tu viens de cloner le repo", dichotomie tranchante volume/vérifié)
- Chaque chiffre/preuve est immédiatement interprété en demi-phrase ("170 tests — pas un side-project", "5 bugs corrigés — elle tourne vraiment") pour éviter le chiffre nu
- Honnêteté assumée comme argument : "early access actif", limites déclarées, ce qui manque est nommé plutôt que camouflé
- Bloc "Notes copywriting (à supprimer avant publication)" systématique qui justifie l'attaque, le ton, le CTA, signale les preuves manquantes et les déviations du brief
- Comptage de mots explicite en fin de notes, vérifié contre la contrainte du brief

## Techniques
- Tutoiement + impératif technique ("lance", "audite", "copie") ; zéro superlatif, zéro emoji décoratif (sauf 1 emoji fonctionnel max en attaque)
- Vocabulaire technique brut non vulgarisé (sandbox Docker, APPROVED, gated, 3-tiers) qui agit comme signal d'appartenance
- CTA unique primaire + secondaire couplé dans la même phrase (étoile GitHub + Discord), micro-qualification type "si ça vous parle"
- Code blocks volontairement minimaux (`make install && make test`) plutôt qu'un setup complet — montre la simplicité sans mentir
- Séparateurs `---` pour scannabilité, sections courtes numérotées [1][2][3] pour les formats email/tutoriel

## Pièges évités
- Pas de question rhétorique d'ouverture, pas de storytelling marketing, pas d'accueil chaleureux
- Pas de chiffres sans interprétation contextuelle
- Pas de CTA multiples dispersés ni de CTA émotionnel mou
- Pas de roadmap floue ni de camouflage du statut early/limites
- Pas d'invention de preuves : les éléments non fournis dans le brief sont flaggés explicitement comme "Preuve manquante" dans les notes

## Template d'exemple

```
[Attaque qualifiante : 1-2 phrases factuelles qui posent le contexte ou la dichotomie]

---

**[Section preuves]**
— [Chiffre/fait] — [interprétation demi-phrase]
— [Chiffre/fait] — [interprétation demi-phrase]

---

[Section "comment c'est construit" : 3-4 phrases avec vocabulaire technique brut]

---

[CTA primaire (lien) + secondaire couplé], formulation micro-qualifiée.

---

## Notes copywriting (à supprimer avant publication)
- 'Choix de l''attaque : [justification]'
- 'Ton préservé : [mots-clés du brief respectés]'
- 'CTA : [logique du choix]'
- 'Preuve manquante : [ce qui doit être remplacé avant publi]'
- 'Décompte mots : ~XXX (contrainte: YYY)'
```

## Sources
- 20260510T181227_904151fb_copywriter (score 0.91)
- 20260510T181906_109e7ce2_copywriter (score 0.88)
- 20260510T182103_0447068e_copywriter (score 0.87)

<details><summary>YAML brut du Skill Extractor</summary>

```yaml
title: Copy technique anti-bullshit pour devs
agent: copywriter
tags:
  - copywriting
  - technical-audience
  - developer-marketing
  - honest-positioning
  - cta-minimal
summary: |
  Recette de copy pour audience technique exigeante (devs, équipes post-POC) : attaque factuelle qui qualifie le lecteur, preuves chiffrées contextualisées, ton tutoyant impératif sans superlatifs, CTA unique ou couplé. Le copywriter livre toujours le texte + un bloc de notes meta qui flag les déviations du brief et les preuves manquantes.
key_patterns:
  - Attaque qui qualifie l'audience plutôt que d'accrocher (sous-titre "Pour les équipes qui ont dépassé le POC", "Tu viens de cloner le repo", dichotomie tranchante volume/vérifié)
  - Chaque chiffre/preuve est immédiatement interprété en demi-phrase ("170 tests — pas un side-project", "5 bugs corrigés — elle tourne vraiment") pour éviter le chiffre nu
  - Honnêteté assumée comme argument : "early access actif", limites déclarées, ce qui manque est nommé plutôt que camouflé
  - Bloc "Notes copywriting (à supprimer avant publication)" systématique qui justifie l'attaque, le ton, le CTA, signale les preuves manquantes et les déviations du brief
  - Comptage de mots explicite en fin de notes, vérifié contre la contrainte du brief
techniques:
  - Tutoiement + impératif technique ("lance", "audite", "copie") ; zéro superlatif, zéro emoji décoratif (sauf 1 emoji fonctionnel max en attaque)
  - Vocabulaire technique brut non vulgarisé (sandbox Docker, APPROVED, gated, 3-tiers) qui agit comme signal d'appartenance
  - CTA unique primaire + secondaire couplé dans la même phrase (étoile GitHub + Discord), micro-qualification type "si ça vous parle"
  - Code blocks volontairement minimaux (`make install && make test`) plutôt qu'un setup complet — montre la simplicité sans mentir
  - Séparateurs `---` pour scannabilité, sections courtes numérotées [1][2][3] pour les formats email/tutoriel
pitfalls_avoided:
  - Pas de question rhétorique d'ouverture, pas de storytelling marketing, pas d'accueil chaleureux
  - Pas de chiffres sans interprétation contextuelle
  - Pas de CTA multiples dispersés ni de CTA émotionnel mou
  - Pas de roadmap floue ni de camouflage du statut early/limites
  - Pas d'invention de preuves : les éléments non fournis dans le brief sont flaggés explicitement comme "Preuve manquante" dans les notes
example_template: |
  [Attaque qualifiante : 1-2 phrases factuelles qui posent le contexte ou la dichotomie]
  
  ---
  
  **[Section preuves]**
  — [Chiffre/fait] — [interprétation demi-phrase]
  — [Chiffre/fait] — [interprétation demi-phrase]
  
  ---
  
  [Section "comment c'est construit" : 3-4 phrases avec vocabulaire technique brut]
  
  ---
  
  [CTA primaire (lien) + secondaire couplé], formulation micro-qualifiée.
  
  ---
  
  ## Notes copywriting (à supprimer avant publication)
  - Choix de l'attaque : [justification]
  - Ton préservé : [mots-clés du brief respectés]
  - CTA : [logique du choix]
  - Preuve manquante : [ce qui doit être remplacé avant publi]
  - Décompte mots : ~XXX (contrainte: YYY)
sources_count: 3
```

</details>
