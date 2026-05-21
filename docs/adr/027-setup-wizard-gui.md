# ADR-027 — Setup Wizard GUI (installation/config click-to-go)

**Statut :** Accepted
**Date :** 2026-05-21
**Sprint :** v0.6.0

## Contexte

Après la livraison de la GUI Streamlit (ADR-026, v0.5.0), l'auteur souhaite que **toute l'installation et la configuration de l'application se fassent depuis l'interface, en cliquant** :

- détecter ce qui manque sur la machine (Python, uv, Ollama, modèles Qwen2.5, Docker, image sandbox, `.env`) ;
- lancer les actions qui peuvent l'être en sans-élévation (start daemon, pull modèle avec progression, build image sandbox, créer `.env`) ;
- pour les composants qui exigent un installeur système (Ollama, Docker Desktop), guider l'utilisateur vers le téléchargement officiel d'un clic.

Aujourd'hui, l'onboarding est documenté dans `README.md` et `docs/getting-started/installation.md` mais demande à l'utilisateur de basculer entre terminal, navigateur, et installeurs. C'est un mur d'entrée injuste pour un projet par ailleurs ergonomique.

## Décision

Ajouter une page **`0_🛠_Setup.py`** (préfixe `0_` pour qu'elle apparaisse en première position dans la sidebar Streamlit), backed par un service **`src/gui/services/setup_runner.py`** qui :

1. **Détecte** 9 composants en parallèle (`detect_all() -> list[ComponentStatus]`) :
   1. Python ≥ 3.12 (toujours OK puisque la GUI tourne, mais affiché pour confort)
   2. `uv` installé (résolution `shutil.which`)
   3. Ollama installé (`ollama --version`)
   4. Ollama daemon démarré (HTTP GET `/api/tags`)
   5. Modèle stratégique pullé (`model_strategic` dans `/api/tags`)
   6. Modèle opérationnel pullé (`model_operational`)
   7. Modèle bulk pullé (`model_bulk`)
   8. Docker installé + daemon up (best-effort, optionnel — mode `enable_sandbox=False` les rend non-bloquants)
   9. Image sandbox `iaa-sandbox:latest` présente
   10. Fichier `.env` présent à la racine

2. **Agit** quand l'action est faisable sans UAC :
   - `start_ollama_daemon()` — lance `ollama serve` en sous-processus détaché (`Popen` sans capture, restart si déjà en cours = no-op)
   - `pull_model(name)` — `POST /api/pull` en streaming JSON, affiche barre de progression Streamlit (% basé sur `completed/total` quand fourni par Ollama)
   - `build_sandbox_image()` — wrap de `scripts/check_sandbox.py --build` via subprocess avec log live
   - `create_env_from_example()` — copie `.env.example` → `.env` si absent (puis affiche un `st.text_area` pour édition inline + bouton save)

3. **Ouvre les URLs officielles** pour ce qui exige un installeur système (boutons `st.link_button`) :
   - Ollama : https://ollama.com/download
   - Docker Desktop : https://www.docker.com/products/docker-desktop/
   - uv : https://docs.astral.sh/uv/getting-started/installation/

### Scope **réaliste** (livré v0.6.0)

| Composant | Détection | Action depuis GUI |
|---|---|---|
| Python | version `sys.version_info` | — (déjà OK si la GUI tourne) |
| `uv` | `shutil.which("uv")` | bouton **Télécharger uv** (ouvre URL) |
| Ollama installé | `shutil.which("ollama")` | bouton **Télécharger Ollama** |
| Ollama daemon | HTTP `/api/tags` | bouton **Démarrer le daemon** (`ollama serve` détaché) |
| Modèles Qwen2.5 | présence dans `/api/tags` | bouton **Pull `<nom>`** avec barre de progression streaming |
| Docker installé | `shutil.which("docker")` | bouton **Télécharger Docker Desktop** |
| Docker daemon | `client.ping()` | bouton **Démarrer Docker Desktop** (Windows seulement, lance `Docker Desktop.exe`) |
| Image sandbox | `images.get("iaa-sandbox:latest")` | bouton **Build image** (subprocess + log live) |
| `.env` | fichier présent | bouton **Créer `.env`** (copie depuis `.env.example`) + éditeur inline |

### Scope **hors-périmètre** (volontairement non-livré)

| Idée | Raison de l'exclusion |
|---|---|
| Auto-installer Ollama / Docker Desktop sans UAC | Windows exige une élévation administrateur. Faisable uniquement via `runas` interactif (UAC popup) — discutable côté sécurité et fragile cross-version. On guide l'URL officielle. |
| Packager l'app en `.exe` standalone (PyInstaller + Streamlit) | Streamlit n'est pas designé pour PyInstaller (race conditions sur `tornado`, `watchdog`). Maintenance fragile, gain pour un usage perso solo limité. |
| Pull "intelligent" qui choisit un modèle plus petit selon la RAM | Heuristique fragile (VRAM ≠ RAM système, modèles quantifiés). On laisse `.env` éditable ; l'utilisateur ajuste à `qwen2.5:14b` ou `7b` si besoin. |
| Désinstallation depuis la GUI | Mêmes contraintes UAC. Un `winget uninstall ollama` ouvrira un terminal admin — pas pertinent en MVP. |
| Persistance d'état "wizard complété" | Inutile : `detect_all()` est rapide (< 1 s en quick mode, ~5 s avec Docker). On re-détecte à chaque visite. |

### Alternatives évaluées

| Approche | Pourquoi rejetée |
|---|---|
| **Page Settings classique** (cocher des cases, valider) | Ne résout pas le problème — l'utilisateur veut voir l'état et **agir**, pas seulement déclarer. |
| **Script `setup.py`** lancé une fois | Existe déjà conceptuellement (`just bootstrap`) mais demande un terminal, ce qui contredit le besoin "tout cliquer". |
| **Détection au boot Streamlit + bannières d'alerte sur chaque page** | Pollue toutes les pages, et empêche d'agir depuis un endroit central. |
| **Réutiliser la page Health** | Health est en lecture seule (diagnostic). Setup est actif (déclenche pull, build). Mélanger les deux casse la séparation des responsabilités. |

## Conséquences

### Positives

- **Onboarding zéro-terminal** : un nouvel utilisateur Windows clone le repo, lance `streamlit run scripts/run_gui.py` (ou le `just gui`), et voit immédiatement ce qui manque + comment l'obtenir.
- **Mauvais setup observable** : un utilisateur qui se demande "pourquoi mes missions échouent ?" obtient en 1 s la réponse (modèle pas pullé, daemon down, image sandbox manquante).
- **Cohérent avec ADR-026** : la GUI devient le canal d'entrée par défaut. Setup → Mission → Historique → Skills → Health → Probes est un parcours linéaire.

### Négatives / à surveiller

- **Subprocess `Popen` détaché sur Windows** pour `ollama serve` : si l'utilisateur ferme la GUI, le daemon continue de tourner (volontaire, mais à documenter). Pas de PID-tracking côté GUI — on délègue la gestion process à l'OS.
- **`/api/pull` streaming** : 38 Go pour `qwen2.5:32b`, donc plusieurs heures sur ADSL. La barre de progression doit refléter cela honnêtement (`{completed}/{total}` octets, ETA estimée). Pas d'annulation propre en MVP (Ctrl-C dans Streamlit ne propage pas) — on documente que la fermeture de la page n'interrompt pas le pull, qu'il faut `ollama stop` côté terminal.
- **Surface de bugs cross-plateforme** : un `which("docker")` qui retourne `/usr/local/bin/docker` n'implique pas que le daemon réponde. La détection sépare bien "installé" vs "running". Mais sur Linux/Mac, la commande "Démarrer Docker Desktop" n'existe pas (paquet `docker.io`) — bouton désactivé hors Windows.

### Coût estimé

- Phase A (service `setup_runner.py` + page `0_🛠_Setup.py` basique + ouverture URLs) : ~1.5 h
- Phase B (actions : start daemon, pull streaming, build sandbox, créer `.env`) : ~2 h
- Phase C (tests AppTest + smoke + doc) : ~1 h
- Phase D (CHANGELOG + version bump + tag v0.6.0 + push) : ~30 min

**Total ~4-5 h.**

## Métriques de suivi

À 2 semaines post-livraison :
- L'auteur lance > 0 fois la page Setup en cold-start sur une machine vierge (validation cas d'usage primaire)
- Pas de bug critique remonté sur les 9 détections
- La doc d'installation pointe en premier vers `just gui` + page Setup (pas vers les commandes CLI)

Si métriques OK : la section "Installation manuelle" du README devient un fallback, pas la voie principale.
