---
id: landing-page-saas
name: "Landing page SaaS (copywriting)"
description: "Rédige une landing page SaaS structurée (hero + features + social proof + CTA) ciblée."
guild: creative
tags: [copywriting, landing, saas, marketing]
params:
  - name: product_name
    label: "Nom du produit"
    example: "FlowSync"
    required: true
  - name: product_pitch
    label: "Pitch en 1 phrase (problème + solution)"
    example: "FlowSync élimine les frictions de handoff entre équipes design et dev en synchronisant Figma et Linear automatiquement."
    required: true
  - name: target_audience
    label: "Cible (ICP — Ideal Customer Profile)"
    example: "PMs et tech leads dans des startups Series A/B (50-200 employés) où design et dev sont séparés."
    required: true
  - name: tone
    label: "Ton souhaité (technique-pro | empathique-startup | luxe | etc.)"
    example: "empathique-startup"
    required: false
---
Rédige le copy d'une landing page SaaS pour **{{ product_name }}**.

## Brief produit

- **Pitch** : {{ product_pitch }}
- **Cible** : {{ target_audience }}
- **Ton** : {{ tone | default("empathique-startup, direct, sans jargon") }}

## Structure attendue

1. **Hero** (above the fold) :
   - H1 : promesse forte en 6-10 mots (pas le nom du produit).
   - Sous-titre : pitch en 2 phrases, max 200 caractères.
   - CTA primaire : verbe d'action + bénéfice immédiat.

2. **Section "Problème"** (3 paragraphes courts) :
   - Empathie avec la douleur quotidienne de l'ICP.
   - Pas de techno-jargon, parler des conséquences vécues.

3. **Section "Solution"** (3-4 features avec H3 + 2 phrases chacune) :
   - Bénéfice utilisateur EN PREMIER, capacité technique en second.
   - Verbes au présent, "vous" plutôt que "les utilisateurs".

4. **Social proof** (placeholder pour 2-3 témoignages) :
   - Format : nom + rôle + entreprise + citation 1-2 phrases.
   - Les noms peuvent être fictifs marqués `[PLACEHOLDER]`.

5. **CTA final** : variation du CTA hero, plus urgent ou plus engageant.

## Contraintes éditoriales

- **Pas de bullshit** : éviter "révolutionnaire", "disruptif", "synergie",
  "10x", "next-gen", "AI-powered" (sauf si vraiment central et expliqué).
- **Phrases courtes** : 15-20 mots max en moyenne.
- **Bénéfices > features** : un dev qui a 30 sec pour scanner doit
  comprendre "à quoi ça me sert" avant "comment ça marche".
- **Français impeccable** : pas d'anglicismes injustifiés, mais "SaaS",
  "dashboard", "workflow" sont acceptables car standard.
- Longueur cible : 600-900 mots total (sans les placeholders).

## Critères de succès

- Le Reviewer (Editor) doit valider que le copy passe le test "5 secondes" :
  un visiteur cible doit pouvoir résumer le produit après 5 sec sur la page.
- Pas de Lorem Ipsum ni de placeholder non-marqué `[...]`.
- Le hero H1 doit fonctionner SANS le sous-titre (test isolé).
