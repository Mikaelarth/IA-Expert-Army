# ADR-018 — Notifications mobiles via webhook (Discord / Slack / Telegram / generic)

**Statut :** Accepted
**Date :** 2026-05-15
**Commits associés :** Sprint HHH

## Contexte

Avec l'arrivée du mode autonome 24/7 sur VPS (cf. ADR-003 + ADR-017), l'utilisateur ne sera plus devant son écran. Il a néanmoins besoin de :

1. **Voir le daily digest sur son téléphone** sans devoir SSH dans le VPS chaque soir
2. **Être alerté immédiatement** d'un incident critique (budget cap atteint, killswitch déclenché, garde-fou levé)
3. **Confirmer qu'autonomous_run a fini** sa queue de missions sans dérive

Sans canal de notification mobile, le gain d'autonomie est partiellement perdu : l'utilisateur retomberait dans le pattern "je vérifie manuellement à 7h, à 12h, à 19h" qui est l'antithèse du mode autonome.

Trois canaux candidats :
- **Discord** : utilisé par la communauté dev (Mike a déjà un compte), webhook gratuit, embeds colorés
- **Slack** : standard pro (potentielle équipe future), webhook gratuit
- **Telegram** : meilleur push mobile, Bot API gratuite, marche bien hors écosystème Big Tech
- **Generic** (n8n, Pipedream, Zapier, custom) : fallback pour tout autre besoin

## Décision

### Module `src/core/notifier.py`

Une classe `Notifier` unifiée qui :
- Prend une `webhook_url` en config (vide → no-op silencieux)
- **Auto-détecte le backend** depuis l'URL (regex : `discord.com/api/webhooks/`, `hooks.slack.com/services/`, `api.telegram.org/bot.../sendMessage`)
- Génère le payload **adapté à chaque backend** (Discord embeds avec couleur par level, Slack blocks, Telegram markdown, generic JSON)
- Méthodes de convenance : `info()`, `success()`, `warning()`, `critical()` (mappées sur emoji + couleur)
- POST via **`urllib.request` stdlib** (zéro nouvelle dépendance)
- **Échec gracieux** : aucune exception ne remonte, log warning et retourne `False`

### Settings

```python
notify_webhook_url: str = Field("")
notify_backend: Literal["auto", "discord", "slack", "telegram", "generic", "none"] = Field("auto")
```

### Intégration

Deux scripts wirés en opt-in (`--notify` flag) :

1. **`scripts/daily_digest.py --notify`** : envoie le digest markdown du jour. Level = `WARNING` si "REJECTED" présent dans le digest, sinon `INFO`.

2. **`scripts/autonomous_run.py --notify`** : envoie le rapport final. Level = `SUCCESS` si queue épuisée proprement, `WARNING` si garde-fou déclenché.

Cas d'usage typique sur VPS — cron quotidien :
```cron
0 22 * * * cd /opt/ia-expert-army && uv run python scripts/daily_digest.py --notify
```

### Choix de design assumés

**Pourquoi `urllib.request` plutôt que `httpx` ou `requests`** : zéro nouvelle dep, surface d'attaque réduite, stdlib stable. Le notifier ne fait que des POST simples vers des endpoints HTTPS — aucun besoin de la sophistication d'httpx (async, http/2, streaming).

**Pourquoi auto-détection d'URL** : permet à l'utilisateur de simplement coller l'URL dans `.env` sans avoir à choisir explicitement le backend. Réduit la friction d'install. L'override explicite (`NOTIFY_BACKEND=discord`) reste possible pour cas tordus (proxy custom, etc.).

**Pourquoi pas de niveau "DEBUG"** : on évite la fatigue de notification. Les 4 levels (INFO, SUCCESS, WARNING, CRITICAL) couvrent tous les besoins identifiés. Le mode autonome verbose va dans les logs locaux, pas dans le téléphone.

**Pourquoi pas de retry automatique** : 1 try, 1 fail = log et continue. Si l'utilisateur veut de la résilience (queue persistante de notifications), il branche un `generic` backend vers son n8n / Pipedream qui, lui, gère la résilience. Sortir du périmètre du module.

## Conséquences

**Positives** :
- L'utilisateur peut laisser tourner le mode autonome 24/7 et voir l'activité sur son téléphone
- Setup en 1 ligne dans `.env` — l'utilisateur teste un webhook Discord en 30 secondes
- Pas de couplage à un fournisseur — Discord aujourd'hui, Telegram demain, n8n après-demain : juste change l'URL
- Échec gracieux garantit qu'un webhook cassé ne casse pas le système (le digest local reste affiché normalement)

**Négatives** :
- Le notifier ne **persiste pas** les notifications échouées. Si Discord est down et qu'une critique arrive, elle est juste loggée puis perdue. Mitigation : pour les incidents critiques (budget exceeded, killswitch), le système écrit déjà dans `data/error_log.json` et le runbook documente le diagnostic.
- Pas de batching : chaque appel = 1 POST. À l'échelle (≥ 100 notifications/jour) ça peut être un anti-pattern. Mitigation : on n'envoie que sur événements significatifs (digest quotidien + garde-fous), pas sur chaque mission.
- Telegram nécessite un BOT_TOKEN + CHAT_ID que l'utilisateur doit configurer (pas du tout évident pour un non-dev). Mitigation : `docs/deploy.md` aura une mini-section "comment créer un bot Telegram" si la demande émerge.

**À surveiller** :
- Volume de notifications réelles sur 1 mois en mode autonome. Si > 200/mois, repenser au batching.
- Stabilité des URLs Discord/Slack (révoquables côté admin du serveur). Documenter dans le runbook : "si soudainement le notifier renvoie 401, renouveler l'URL".

## Alternatives considérées

1. **Email SMTP** : refusé. SMTP nécessite une config plus complexe (SPF/DKIM, password app), et l'email est lent (push pas instantané, dans la boîte spam parfois). Webhook Discord/Telegram est instantané et trivial à configurer.

2. **Push iOS via APNS / Android via FCM** : refusé. Surcharge énorme (certificats Apple, Firebase, app native). Hors-périmètre.

3. **Twilio SMS** : refusé. Coûte de l'argent et c'est over-kill pour un user solo.

4. **Pas de notifier, l'utilisateur SSH manuellement** : refusé. C'est exactement ce qu'on essaie d'éviter avec le mode autonome — il faut un canal pull/push moderne.

5. **Library `apprise` (multi-backend)** : refusé. Belle lib mais ajoute une dépendance lourde (~30 deps transitives) pour un cas d'usage où 200 lignes de stdlib suffisent. Si on doit support 30+ backends, on reviendra à apprise.

## Suivi

À mesurer après 2 semaines d'usage en mode autonome :
- Nombre de notifications envoyées
- Nombre d'échecs de delivery (URL HTTP 4xx/5xx)
- Temps de réaction utilisateur sur warning/critical (cible : < 1h pour warning, < 15 min pour critical)

Si délais > cibles, ajouter un escalation (relance après 30 min si pas vu).

## Sources

- Discord webhook docs : https://discord.com/developers/docs/resources/webhook
- Slack incoming webhook : https://api.slack.com/messaging/webhooks
- Telegram Bot API : https://core.telegram.org/bots/api#sendmessage
- ADR-003 (autonomy with guardrails) — ce notifier complète le garde-fou #9 "daily digest"
- ADR-010 (Phase 6 autonomous validation) — le notifier ferme la boucle "user-aware"
- ADR-017 (VPS deployment) — le mode autonome 24/7 sur VPS rend le notifier essentiel
