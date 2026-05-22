# Déploiement LAN et VPS — IA-Expert-Army

Guide pour exposer IA-Expert-Army au-delà du `localhost` : depuis un autre
poste du même réseau (LAN privé) jusqu'à un VPS internet.

> **TL;DR** : `docker compose --profile app up -d` lance l'app sur
> `http://<ip-du-host>:8501`. Tu y accèdes depuis n'importe quel poste du
> LAN. Pour VPS internet, ajoute Caddy + auth avant de pointer vers `8501`.

---

## Pourquoi

Le `localhost` only de v0.5.0 → v0.9.0 est très bien pour l'usage perso à
un seul poste. Mais 3 cas d'usage débordent ce périmètre :

| Cas | Besoin | Solution |
|---|---|---|
| **PC fixe + laptop sur même WiFi** | Lancer mission depuis le laptop, exécution sur le PC fixe (GPU) | Mode LAN — ce guide §1 |
| **VPS Docker mutualisé pour un cercle restreint** | Accès depuis n'importe où via internet | Mode VPS — ce guide §3 |
| **Démo à un collègue** | Lui partager l'URL temporairement | Mode LAN + tunnel (ngrok, tailscale) |

---

## 1. Mode LAN — autre PC sur le même réseau

### 1.1 Pré-requis sur le PC qui héberge

- Docker Desktop (Windows/Mac) ou docker-engine + docker-compose-plugin (Linux)
- **Ollama** installé et démarré sur le PC host (les modèles Qwen2.5 doivent
  être pullés — cf. page Setup de la GUI ou `ollama pull qwen2.5-coder:32b`)
- Port `8501` non-bloqué par le firewall (cf. §1.4)

### 1.2 Build et lancement

```bash
# Une fois (build de l'image, ~3 minutes la 1ère fois)
docker compose --profile app build

# À chaque démarrage
docker compose --profile app up -d

# Vérifier que ça tourne
docker compose --profile app ps
docker compose --profile app logs -f app   # follow logs
```

L'image embarque l'app Python complète. Elle utilise les modèles Ollama
installés sur le PC host via `host.docker.internal:11434` (configuré
automatiquement dans `docker-compose.yml`).

### 1.3 Identifier l'IP du PC host

Tu en as besoin pour te connecter depuis l'autre PC.

**Windows (PowerShell)** :
```powershell
ipconfig | Select-String "IPv4"
# Cherche l'IP de l'interface WiFi/Ethernet active (typiquement 192.168.x.x)
```

**Linux/Mac (terminal)** :
```bash
# Linux
ip addr | grep "inet " | grep -v 127.0.0.1
# Mac
ifconfig | grep "inet " | grep -v 127.0.0.1
```

Exemple typique : `192.168.1.42`

### 1.4 Ouvrir le port 8501 dans le firewall

**Windows Defender** :
- Panneau de configuration → Système et sécurité → Pare-feu Windows
- Paramètres avancés → Règles de trafic entrant → Nouvelle règle
- Type : Port · Protocole : TCP · Port spécifique : `8501`
- Action : Autoriser la connexion · Profil : Privé uniquement (PAS public)
- Nom : `IA-Expert-Army (LAN only)`

**Linux (ufw)** :
```bash
sudo ufw allow from 192.168.0.0/16 to any port 8501
# `from 192.168.0.0/16` restreint au LAN privé, pas internet
```

**Mac (System Preferences)** : Sécurité → Pare-feu → Autoriser entrées
pour `python` ou `Docker`.

### 1.5 Tester depuis l'autre PC

Ouvre un navigateur sur le 2ème PC :
```
http://192.168.1.42:8501
```
(remplace par l'IP réelle du PC host trouvée en §1.3)

La GUI Streamlit doit s'afficher. Tu peux lancer une mission depuis ce
poste — l'exécution se fait sur le PC host (qui a Ollama + les modèles).

### 1.6 Stop / restart

```bash
docker compose --profile app stop          # stop sans supprimer les containers
docker compose --profile app down          # stop + supprimer (les volumes restent)
docker compose --profile app down -v       # ⚠ supprime AUSSI les volumes data/
```

---

## 2. Architecture du déploiement

```
       PC2 (laptop)                    PC1 (host avec GPU + Ollama)
       ┌──────────────┐                ┌────────────────────────────────┐
       │  Browser     │                │                                │
       │              │ HTTP/WS        │  ┌──────────────────────────┐  │
       │ http://192. ─┼───────────────►│  │  Container iaa-app       │  │
       │  168.1.42:   │                │  │  (Streamlit + agents)    │  │
       │  8501        │                │  │  Port 8501               │  │
       └──────────────┘                │  └──────────┬───────────────┘  │
                                       │             │                   │
                                       │  host.docker│.internal:11434    │
                                       │             ▼                   │
                                       │  ┌──────────────────────────┐  │
                                       │  │  Ollama (host process)   │  │
                                       │  │  qwen2.5:32b             │  │
                                       │  │  qwen2.5-coder:32b       │  │
                                       │  │  qwen2.5:14b             │  │
                                       │  └──────────────────────────┘  │
                                       └────────────────────────────────┘
                                              LAN privé 192.168.x.x
```

**Pourquoi Ollama reste sur le host (pas en container)** :
- Le GPU n'est pas trivialement exposé à Docker sans CUDA toolkit
- Les modèles pèsent 20-40 Go — pas envie de les dupliquer dans une image
- Performance native (pas de couche réseau supplémentaire pour 30s+ d'inférence)

---

## 3. Migration vers VPS internet

⚠ **NE PAS exposer le port 8501 directement à internet.** Streamlit n'a
pas d'auth native ; tout le monde pourrait lancer des missions sur ta VM.

### 3.1 Schéma cible

```
Internet ──HTTPS──► Caddy/Nginx (port 443)
                      │
                      ├── Basic Auth / OAuth
                      │
                      ▼
                    iaa-app:8501 (réseau Docker privé)
                      │
                      ▼
              Ollama (sur le VPS, ou cluster GPU dédié)
```

### 3.2 Pré-requis VPS

- 32+ Go RAM (Qwen2.5:32b en RAM seul, sans GPU) ou 24 Go RAM + GPU 24Go
- 100+ Go disk (data/ + modèles Ollama)
- Docker + docker-compose-plugin
- Domaine pointant sur l'IP du VPS (pour TLS Let's Encrypt via Caddy)

### 3.3 Étapes recommandées

1. **Cloner le repo + builder l'image** :
   ```bash
   git clone https://github.com/Mikaelarth/IA-Expert-Army.git
   cd IA-Expert-Army
   docker compose --profile app build
   ```

2. **Installer Ollama sur le VPS** :
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull qwen2.5:32b
   ollama pull qwen2.5-coder:32b
   ollama pull qwen2.5:14b
   ```

3. **Reverse proxy Caddy avec basic auth** — exemple `Caddyfile` :
   ```caddy
   ia.tondomaine.com {
       basicauth {
           ton_user $2a$14$hash_bcrypt_de_ton_mot_de_passe
       }
       reverse_proxy localhost:8501
   }
   ```
   Générer le hash : `caddy hash-password`.

4. **Bind 127.0.0.1 dans docker-compose.yml** (pas 0.0.0.0 sur le VPS) :
   ```yaml
   ports:
     - "127.0.0.1:8501:8501"  # accessible UNIQUEMENT via Caddy
   ```

5. **Lancer Caddy + l'app** :
   ```bash
   sudo systemctl enable --now caddy
   docker compose --profile app up -d
   ```

### 3.4 Pour aller plus loin (Phase 2 VPS)

- **OAuth via Authelia** au lieu de Basic Auth (multi-utilisateurs)
- **Backup automatique** des volumes via `scripts/backup.py` en cron
- **Notifier webhook** pour les missions terminées (cf. `.env` `NOTIFY_WEBHOOK_URL`)
- **Monitoring** : Prometheus + Grafana (à câbler, pas livré v0.9.x)

---

## 4. Sandbox Docker dans le container app

Par défaut, le container `iaa-app` n'a PAS accès au socket Docker du host
(défense en profondeur). Conséquence : `--validate` qui lance le sandbox
pytest échoue avec "Docker daemon down" depuis l'app conteneurisée.

**Pour activer le sandbox dans le container app** (à tes risques) :

```yaml
# Dans docker-compose.yml, service app, ajouter :
volumes:
  - /var/run/docker.sock:/var/run/docker.sock  # ⚠ container peut piloter Docker
environment:
  ENABLE_SANDBOX: "true"
```

Avec cette config, le container peut lancer/arrêter d'autres containers
sur le host — c'est l'équivalent d'un accès root sur le host. À éviter
en mode VPS multi-tenant.

**Alternative plus propre** (non livrée v0.9.x) : sysbox runtime ou
DinD (Docker-in-Docker) sandboxé. Cf. ADR futur.

---

## 5. Troubleshooting

| Symptôme | Cause probable | Fix |
|---|---|---|
| `http://<ip>:8501` timeout depuis l'autre PC | Firewall bloque 8501 | Cf. §1.4 |
| `connection refused` depuis l'autre PC | `0.0.0.0:8501` pas appliqué | Vérifier `docker compose ps` → port binding affiche `0.0.0.0:8501->8501/tcp` |
| Container démarre mais GUI vide | Ollama injoignable | `docker compose logs app` — chercher `Connection refused on /api/tags`. Vérifier `ollama serve` tourne sur le host |
| `host.docker.internal` ne résout pas (Linux) | Docker < 20.10 | Upgrader Docker, ou utiliser l'IP du host directement dans `OLLAMA_BASE_URL` |
| Mission échoue avec sandbox error | `ENABLE_SANDBOX=true` mais socket Docker pas monté | Cf. §4. En mode LAN test, laisser `ENABLE_SANDBOX=false` |
| Page Setup signale "Daemon Ollama injoignable" | Ollama tourne sur host mais l'app conteneurisée ne l'atteint pas | Vérifier `extra_hosts` dans docker-compose et que le firewall host autorise `localhost:11434` côté loopback |

---

## 6. Coûts et limites

- **Build initial** : ~3 min sur connection rapide (uv sync + COPY src/)
- **Image size** : ~800 Mo (Python 3.12-slim + deps + src)
- **Startup container** : 2-5 sec (Streamlit boot)
- **Latence LAN** : négligeable vs 30s+ d'inférence Ollama
- **RAM container** : ~200 Mo (Streamlit + app) + Ollama qui reste sur host
- **Persistence** : tout ce qui est sous `./docker-volumes/app/data/` survit aux
  redémarrages. Le code source est dans l'image (rebuild pour update).

Pour update le code sans rebuild complet :
```bash
docker compose --profile app build app   # rebuild juste le service app
docker compose --profile app up -d app   # restart avec la nouvelle image
```
