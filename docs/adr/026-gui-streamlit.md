# ADR-026 — Interface GUI : Streamlit

**Statut :** Accepted
**Date :** 2026-05-21
**Sprint :** v0.5.0

## Contexte

Depuis v0.1.0, le projet est piloté exclusivement en CLI (`scripts/run_mission.py`, `scripts/daily_digest.py`, `scripts/probe_reviewer.py`, etc.). C'est ergonomique pour automatiser et scripter, mais inconfortable pour :

- **Lancer une mission ponctuelle** : il faut composer manuellement un long `--description` shell-quoté avec des accents/caractères spéciaux, ce qui est pénible sur Windows PowerShell.
- **Consulter l'historique** : lire un par un les `data/memory/missions/*.md` ne donne pas de vue d'ensemble (verdict, score, durée par mission, filtrage par guilde).
- **Explorer les skills** : 16 skills auto-extraites dans `skills/<agent>/*.md` — pas pratique en CLI à naviguer.
- **Vérifier la santé du système** : `just health` est text-based, peu visuel.
- **Lancer des probes** : `probe_reviewer.py`, `probe_sandbox.py` sont des outils techniques que la CLI cache derrière des chemins.

Le projet est en mode "outil perso" (cf. choix Session 0). L'auteur l'utilise au quotidien, donc l'ergonomie GUI vaut le coût.

## Décision

**Adopter Streamlit** comme couche GUI, avec architecture multipages native :

```
src/gui/
  app.py                 # entry + sidebar + page d'accueil
  pages/
    1_🚀_Mission.py      # form + lancement mission
    2_📜_Historique.py   # liste + détail des missions archivées
    3_🧠_Skills.py       # explorateur skills par agent
    4_🏥_Health.py       # health_check live
    5_🔬_Probes.py       # lancer/voir probe_reviewer + probe_sandbox
  services/
    mission_runner.py    # wraps MissionRouter avec progression
    memory_browser.py    # wraps FileMemory pour list/detail
    health.py            # wraps health_check.py
```

Lancement : `streamlit run scripts/run_gui.py` (port 8501, bind localhost only).

### Alternatives évaluées

| Techno | Pourquoi rejetée |
|---|---|
| **FastAPI + React/Vue** | Stack JS séparée à maintenir solo. Disproportionné. |
| **FastAPI + HTMX** | Plus léger que React mais nécessite serveur ASGI + setup HTML manuel. |
| **Gradio** | Orienté ML demos (single function input→output), pas multipages explorer. |
| **Textual (TUI)** | Terminal-only, pas une vraie GUI navigable à la souris. |
| **PyWebIO** | Moins maintenu, communauté plus petite. |
| **tkinter / PyQt** | App desktop native lourde, peu de gain visuel vs Streamlit. |

Streamlit gagne sur 4 axes pour ce projet : (1) stack Python pure, (2) hot reload, (3) multipages natif, (4) très bien pour outils LLM/data (Hugging Face Spaces, etc.).

### Architecture — choix d'intégration

- **Pas de couche REST** entre GUI et backend. Streamlit tourne dans le même process Python, importe directement `MissionRouter`, `FileMemory`, `SkillsLibrary`. Plus simple, moins de duplication, et OK pour usage perso solo.
- **Lancement de mission synchrone** dans le button handler : `asyncio.run(router.run(...))` avec `st.spinner`. Bloquant côté UI (le spinner tourne 20-40 min), pas de streaming live des logs en MVP. **Acceptable** : l'utilisateur peut suivre `data/memory/episodes/*.md` côté disque OU les logs structlog dans un terminal séparé. Phase 2 ajoutera du streaming WebSocket / `st.status` si besoin.
- **Cache `st.cache_data`** sur les chargements de skills/missions pour éviter de re-lire le disque à chaque interaction.
- **Bind localhost only** par défaut (`streamlit run ... --server.address 127.0.0.1`). Pas d'auth requise (usage perso). Si déploiement multi-utilisateur, Phase 2 ajoutera auth Basic ou reverse proxy.

### Dépendance

Nouveau groupe `[dependency-groups].gui` dans `pyproject.toml` :

```toml
[dependency-groups]
gui = ["streamlit>=1.40.0"]
```

Installation : `uv sync --group gui` (opt-in, ~50 Mo de dépendances). La CLI fonctionne sans Streamlit installé.

## Conséquences

### Positives

- **Ergonomie quotidienne** : lancer une mission devient un formulaire + bouton, pas un long PowerShell quoté.
- **Découverte du projet** : un nouvel utilisateur voit l'historique, les skills, la santé d'un coup d'œil — bien meilleur que de demander "où sont mes missions ?"
- **Réutilisable hors-perso** : si un jour le projet sert un petit cercle, Streamlit gère 2-5 utilisateurs concurrent sans drame.
- **Tests dispos** : `streamlit.testing.AppTest` permet des smoke tests automatiques (page render sans exception).

### Négatives / à surveiller

- **Surface de dépendances** : streamlit traîne ~30 packages (tornado, altair, watchdog…). Mitigé en mettant dans `[dependency-groups].gui` (opt-in).
- **Pas de streaming live des logs en MVP** : le user voit un spinner 20-40 min sans détail. Compensable en gardant un terminal `tail -f` sur les logs structlog, ou via Phase 2.
- **État partagé entre pages limité** : Streamlit reset le state à chaque interaction. Pour des flows multi-étapes (ex : composer une mission complexe en plusieurs onglets), il faudra `st.session_state` explicite.

### Coût estimé

- Phase 1 MVP (5 pages basiques + tests) : ~3-4 h de travail
- Phase 2 (streaming live, edit prompts, mode autonome UI) : ~2-3 h si besoin futur

## Métriques de suivi

À 1 mois post-livraison, valider que :
- L'auteur lance > 80% de ses missions via la GUI (vs CLI direct)
- Pas de bug critique remonté sur les 5 pages
- Temps de chargement initial < 5 s

Si métriques OK : GUI devient le canal d'usage par défaut, la CLI reste pour scripting et CI.
