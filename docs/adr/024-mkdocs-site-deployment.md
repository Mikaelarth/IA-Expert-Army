# ADR-024 — Site mkdocs déployé automatiquement sur GitHub Pages

**Statut :** Accepted
**Date :** 2026-05-15
**Commits associés :** Sprint RRR
**Précédents :** ADR-022/023 (politique anti-dérive automatisée), Sprint PPP (3 docs utilisateur consolidées)

## Contexte

Sprint PPP a livré 3 docs utilisateur structurées (`getting-started.md`,
`operations.md`, `architecture.md`) + 23 ADRs + un README condensé. Mais
**lire des markdown bruts sur GitHub** :
- Pas de navigation par tabs / sidebar
- Pas de recherche
- Pas de copy-to-clipboard sur les blocs de code
- Pas de mode sombre / clair
- Mermaid diagrams pas toujours bien rendus
- Liens entre fichiers cassent souvent (chemins relatifs vs absolus)

Un projet "vendable" mérite mieux. ADR-024 transforme les markdown en un
site statique pro avec `mkdocs-material` + déploiement auto sur GitHub Pages.

## Décision

### Configuration `mkdocs.yml`

Theme : **mkdocs-material** — référence du marché, look pro out-of-the-box,
mode sombre intégré, recherche client-side, copy-to-clipboard, etc.

Plugins :
- `search` (multi-langue fr + en)
- `mermaid2` (rendu des diagrammes Mermaid embarqués dans la doc d'archi)

Markdown extensions :
- `pymdownx.highlight` + `pymdownx.superfences` (code blocks pro)
- `pymdownx.tabbed` (onglets Linux/macOS/Windows pour les commandes)
- `pymdownx.tasklist` (checklists)
- `pymdownx.emoji` (emojis Material Design via `:material-rocket-launch:`)
- `admonition` + `pymdownx.details` (callouts colorés)
- `toc` avec `permalink: true` (lien direct sur chaque section)

Navigation : **explicite via `nav:`** dans `mkdocs.yml` (sinon ordre alpha
qui mélange les ADRs). 4 sections :
- **Accueil** (`docs/index.md` — nouvelle page d'accueil web-friendly)
- **Démarrer** (Getting Started)
- **Opérations** (autonome + deploy + runbook)
- **Architecture** (vue 4 couches + Mermaid)
- **Décisions (ADRs)** (23 ADRs listés explicitement)

### `docs/index.md` — page d'accueil dédiée au site

Le README.md GitHub a son propre style (badges Shields.io, table des matières
condensée pour scrolling). Pour le site, on crée `docs/index.md` :
- Hero header avec titre + sous-titre stylé
- 3 cartes (Getting Started / Operations / Architecture) en grille
- Section "Garanties auto-vérifiées" tabulée
- Démarrage express en 5 lignes

Avantage : on garde le README optimisé pour GitHub ET on a une vraie home
web pour le site. Pas de duplication maintenance lourde — les 2 fichiers
ont des objectifs distincts.

### Strict mode obligatoire

```bash
mkdocs build --strict
```

`--strict` échoue sur tout **warning** (lien cassé, fichier introuvable,
ancre manquante). Cohérent avec la politique anti-dérive Sprint LLL/QQQ :
si une PR casse un lien dans la doc, le CI bloque le merge.

### Workflow `.github/workflows/docs.yml`

```yaml
on:
  push:
    branches: [main]
    paths:
      - "docs/**"
      - "mkdocs.yml"
      - "README.md"
      - ".github/workflows/docs.yml"
  workflow_dispatch:
```

- Trigger : push sur main qui touche la doc OU déclenchement manuel
- Build via `uv sync --all-extras` + `mkdocs build --strict`
- Deploy via `actions/deploy-pages@v4` dans l'environnement `github-pages`
- Concurrency : annule les builds anciennes sur même branche
- Permissions minimales : `contents: read`, `pages: write`, `id-token: write`

Premier setup côté repo : **Settings → Pages → Source : GitHub Actions**
(une seule fois, manuel).

URL finale : `https://mikaelarth.github.io/IA-Expert-Army/`.

### Recipes justfile

```bash
just docs-build    # build strict (= ce que CI fait)
just docs-serve    # live reload sur http://127.0.0.1:8000
just docs-clean    # supprime site/
```

### `.gitignore`

```
site/
.mkdocs-cache/
```

Le `site/` est généré, jamais committé. Source de vérité = `docs/` + `mkdocs.yml`.

## Bugs trouvés pendant le sprint

**Bug 1 — Liens d'ancre avec accents cassent en slug mkdocs**

`pymdownx.toc` retire les accents lors de la slugification :
- `## 5. Monitoring et observabilité` → slug `#5-monitoring-et-observabilite`
- Mes liens TOC pointaient vers `#5-monitoring-et-observabilité` (avec accent)
- Build strict : 7 warnings "no such anchor"

Fix : remplacer les ancres avec accents par leurs versions slugifiées dans
les liens TOC. Conserve les titres avec accents (lisibles), corrige les
références.

**Bug 2 — Liens `../README.md` depuis `docs/getting-started.md`**

Le README est à la racine, pas dans `docs/`. mkdocs build strict refuse les
liens hors du `docs_dir`.

Fix : remplacer par référence vers `index.md` (page d'accueil web) ou les
autres docs (`operations.md`, etc.). Cohérent avec la séparation README
GitHub / index web.

**Bug 3 — Liens vers `docs/adr/` (dossier) au lieu de `adr/README.md`**

`[ADRs](adr/)` est ambigu — mkdocs voit un dossier sans index.html.

Fix : pointer explicitement vers `adr/README.md` qui est l'index des ADRs.

Ces 3 bugs auraient causé du contenu cassé sur le site live sans le strict
mode + le build local préalable. Validation de la politique "strict-first".

## Conséquences

**Positives** :
- **Site doc public, search, mobile-friendly, mode sombre**, à URL fixe
- Déployé **automatiquement** à chaque push main qui touche la doc
- `--strict` aligne avec la politique anti-dérive (Sprint LLL/QQQ)
- Les Mermaid diagrams sont rendus proprement (architecture.md a 3 diagrams)
- Le README GitHub reste son propre média (badges Shields, scroll court)
- La home web (`docs/index.md`) peut être plus "marketing" sans toucher
  au README — séparation de responsabilités saine

**Négatives** :
- Maintenance : 2 fichiers d'entrée (README.md + docs/index.md). Mitigation :
  les deux sont volontairement DIFFÉRENTS dans leur focus (GitHub vs Web).
  Pas de duplication de fond.
- Coût build : ~3s. Coût artifact upload : ~1 Mo. Négligeable.
- Une nouvelle dépendance dev (mkdocs-material + mermaid2-plugin). Maintenue
  activement, populaire (8k stars), risque faible.

**À surveiller** :
- Le `mkdocs-material 2.0` est annoncé pour février 2026 avec breaking changes.
  Affichage de l'avertissement actuel à chaque build : on reste sur v1
  (9.7.6) jusqu'à stabilisation de la v2.
- Si les ADRs grossissent à 30+, restructurer la nav (par exemple grouper
  par phase : Sprint phase 0-2, phase 3-5, phase 6+).

## Workflow d'évolution

**Ajouter une nouvelle page** :
1. Créer `docs/ma-page.md`
2. Ajouter à `nav:` dans `mkdocs.yml` (l'ordre détermine la navigation)
3. `just docs-build` pour valider en strict local
4. Commit + push → CI déploie auto

**Ajouter un nouvel ADR** :
1. Créer `docs/adr/NNN-mon-adr.md`
2. Ajouter à l'index `docs/adr/README.md`
3. Ajouter à `nav:` dans `mkdocs.yml` (section "Décisions (ADRs)")
4. Commit + push → CI déploie auto

**Changer le thème / la nav globale** :
1. Éditer `mkdocs.yml`
2. `just docs-serve` pour preview live
3. Commit + push

## Alternatives considérées

1. **Sphinx + Read the Docs** : refusé. RTD est puissant mais lourd (RST
   par défaut, config plus complexe). mkdocs-material couvre 95% des besoins
   avec moins de friction.

2. **Docusaurus** : refusé. Node.js stack = nouvelle dépendance lourde dans
   un projet 100% Python. Maintenance + CI plus complexes.

3. **GitBook / Notion** : refusé. Vendor lock-in. Sources hors du repo.
   Pas viable pour un projet open-source.

4. **README étendu sans site** : refusé. C'est ce qu'on avait — pas suffisant
   pour rendre le projet "vendable" à des contributeurs / employeurs.

5. **mkdocs (sans material)** : refusé. Theme par défaut moins pro, pas de
   mode sombre, pas de recherche client-side. Material est le standard.

## Sources

- [mkdocs-material](https://squidfunk.github.io/mkdocs-material/) — référence
- [GitHub Pages docs](https://docs.github.com/en/pages)
- [actions/deploy-pages](https://github.com/actions/deploy-pages)
- Sprint PPP : 3 docs utilisateur consolidées (input pour le site)
- Sprint LLL/QQQ : politique strict-first (alignement avec `--strict`)
