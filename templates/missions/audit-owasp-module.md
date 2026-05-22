---
id: audit-owasp-module
name: "Audit OWASP d'un module"
description: "Audit sécurité défensif (OWASP Top 10 pertinent) sur un module Python avec remédiations actionnables."
guild: engineering
tags: [security, owasp, audit, defensive]
params:
  - name: module_path
    label: "Chemin du module à auditer"
    example: "src/api/auth.py"
    required: true
  - name: threat_model
    label: "Contexte de déploiement (single-user local | multi-user web | service interne)"
    example: "single-user local"
    required: true
---
Réalise un audit sécurité défensif du module **`{{ module_path }}`** dans
le contexte de déploiement **{{ threat_model }}**.

## Grille d'analyse OWASP (Top 10 2021 — pertinent pour Python backend)

Pour chaque catégorie applicable, lister :
- Présence / absence du risque dans le module
- Niveau de gravité (faible / moyen / élevé)
- Remédiation concrète actionnable

Catégories à considérer :

1. **A01 Broken Access Control** — vérifications autorisation, paths
   traversal, IDOR, élévation de privilèges.
2. **A02 Cryptographic Failures** — hashing passwords, secrets en clair,
   randomness (`random` vs `secrets`), TLS hard-coded.
3. **A03 Injection** — SQL (paramétrisation), command (subprocess.run avec
   shell=True), template (Jinja autoescape), regex injection (catastrophic
   backtracking).
4. **A05 Security Misconfiguration** — defaults dangereux, debug=True en
   prod, CORS trop large, headers manquants (HSTS, CSP).
5. **A06 Vulnerable Components** — deps non pinnées, dépendances connues
   vulnérables (vérifier `uv pip list` + CVE).
6. **A07 Identification & Authentication** — sessions prédictibles, brute
   force protection, password policy.
7. **A08 Software & Data Integrity** — désérialisation insecure (pickle,
   yaml.load sans Loader), signature des updates.
8. **A09 Logging & Monitoring** — logs qui leak des secrets, absence
   d'audit trail sur opérations sensibles.
9. **A10 SSRF** — `requests.get` sur URL utilisateur sans whitelist.

## Format de sortie attendu

Tableau markdown ordonné par gravité :

| OWASP | Finding | Sévérité | Remédiation |
|---|---|---|---|
| A03 | `subprocess.run(cmd, shell=True)` ligne 47 | Élevée | Passer cmd en liste, drop shell=True |

Suivi d'une section "Score global de sécurité" : note /100 + recommandation
prioritaire en 1 phrase.

## Contraintes

- **Pas de modifications de code dans cette mission** — c'est un audit.
  Les fixes seront livrés via missions séparées.
- Si aucune vulnérabilité n'est trouvée, le dire explicitement avec
  justification (pas de finding inventé pour faire du volume).
- Adapter la sévérité au `threat_model` : un audit "single-user local"
  juge différemment qu'un "multi-user web".
