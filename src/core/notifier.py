"""Notifier — webhook notifications mobiles (Discord / Slack / Telegram / generic).

Sprint HHH.2 — permet à l'utilisateur de recevoir le daily digest, les
warnings du mode autonome et les alertes critiques sur son téléphone via
un webhook configuré dans `.env`.

Backends supportés :
  - **Discord** : webhook URL → POST avec `embeds` (couleurs par level)
  - **Slack** : webhook URL → POST avec `blocks` markdown
  - **Telegram** : URL Bot API `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<ID>` → POST `text` markdown
  - **generic** : POST JSON brut `{level, title, body, timestamp}` (compat Pipedream, n8n, custom)

Détection auto du backend depuis l'URL :
  - contient `discord.com/api/webhooks/` → discord
  - contient `hooks.slack.com/services/` → slack
  - contient `api.telegram.org/bot` → telegram
  - sinon → generic

Pas de nouvelle dépendance : utilise `urllib.request` de stdlib (POST simple).
Échec gracieux : log warning et continue, ne crash JAMAIS le caller.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from src.core.logging import get_logger

log = get_logger("notifier")

NotifyBackend = Literal["auto", "discord", "slack", "telegram", "generic", "none"]


class NotifyLevel(str, Enum):
    """Niveau de sévérité — utilisé pour le rendu visuel (couleur Discord, emoji)."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    SUCCESS = "success"


# Emojis et couleurs par level (couleurs Discord = int RGB).
_LEVEL_META: dict[NotifyLevel, dict[str, Any]] = {
    NotifyLevel.INFO: {"emoji": "ℹ️", "color": 0x3498DB, "slack_color": "#3498db"},
    NotifyLevel.SUCCESS: {"emoji": "✅", "color": 0x2ECC71, "slack_color": "#2ecc71"},
    NotifyLevel.WARNING: {"emoji": "⚠️", "color": 0xF39C12, "slack_color": "warning"},
    NotifyLevel.CRITICAL: {"emoji": "🚨", "color": 0xE74C3C, "slack_color": "danger"},
}


def _detect_backend(url: str) -> NotifyBackend:
    """Devine le backend depuis l'URL. Refactor central pour clarté."""
    if not url:
        return "none"
    if "discord.com/api/webhooks/" in url or "discordapp.com/api/webhooks/" in url:
        return "discord"
    if "hooks.slack.com/services/" in url:
        return "slack"
    if re.search(r"api\.telegram\.org/bot[^/]+/sendMessage", url):
        return "telegram"
    return "generic"


def _truncate(text: str, max_chars: int) -> str:
    """Coupe avec ellipsis si trop long. Discord limite embed.description à 4096,
    Slack block.text à 3000, Telegram message à 4096."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n…(tronqué)"


def _payload_discord(level: NotifyLevel, title: str, body: str) -> dict[str, Any]:
    meta = _LEVEL_META[level]
    return {
        "embeds": [
            {
                "title": f"{meta['emoji']} {_truncate(title, 250)}",
                "description": _truncate(body, 4000),
                "color": meta["color"],
                "footer": {"text": "IA-Expert-Army"},
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ]
    }


def _payload_slack(level: NotifyLevel, title: str, body: str) -> dict[str, Any]:
    meta = _LEVEL_META[level]
    return {
        "attachments": [
            {
                "color": meta["slack_color"],
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{meta['emoji']} {_truncate(title, 140)}",
                        },
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": _truncate(body, 2900)},
                    },
                    {
                        "type": "context",
                        "elements": [
                            {"type": "mrkdwn", "text": "_IA-Expert-Army_"},
                        ],
                    },
                ],
            }
        ]
    }


def _payload_telegram(level: NotifyLevel, title: str, body: str) -> dict[str, Any]:
    meta = _LEVEL_META[level]
    text = f"{meta['emoji']} *{title}*\n\n{body}"
    return {"text": _truncate(text, 4000), "parse_mode": "Markdown"}


def _payload_generic(level: NotifyLevel, title: str, body: str) -> dict[str, Any]:
    return {
        "level": level.value,
        "title": title,
        "body": body,
        "timestamp": datetime.now(UTC).isoformat(),
        "source": "ia-expert-army",
    }


def _build_payload(
    backend: NotifyBackend, level: NotifyLevel, title: str, body: str
) -> dict[str, Any]:
    if backend == "discord":
        return _payload_discord(level, title, body)
    if backend == "slack":
        return _payload_slack(level, title, body)
    if backend == "telegram":
        return _payload_telegram(level, title, body)
    return _payload_generic(level, title, body)


class Notifier:
    """Notifier configurable. Si webhook_url vide → no-op silencieux."""

    def __init__(
        self,
        webhook_url: str | None = None,
        backend: NotifyBackend = "auto",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.webhook_url = (webhook_url or "").strip()
        if backend == "auto":
            self.backend: NotifyBackend = _detect_backend(self.webhook_url)
        else:
            self.backend = backend
        self.timeout_seconds = timeout_seconds

    @property
    def is_enabled(self) -> bool:
        """True si une URL valide est configurée."""
        return bool(self.webhook_url) and self.backend != "none"

    def send(
        self,
        level: NotifyLevel | str,
        title: str,
        body: str,
    ) -> bool:
        """Envoie une notification. Renvoie True si succès, False sinon.

        Ne lève JAMAIS d'exception : log warning et continue.
        """
        if not self.is_enabled:
            log.debug("notifier.skip", reason="not_enabled")
            return False

        if isinstance(level, str):
            try:
                level = NotifyLevel(level.lower())
            except ValueError:
                log.warning("notifier.bad_level", level=level)
                level = NotifyLevel.INFO

        payload = _build_payload(self.backend, level, title, body)
        return self._post(payload)

    def _post(self, payload: dict[str, Any]) -> bool:
        """POST JSON via urllib (stdlib, zéro dep)."""
        # Sécurité (ruff S310) : on rejette explicitement les schemes non-http/https.
        # `file://` ou autres schemes custom ne devraient JAMAIS apparaître ici car
        # _detect_backend renvoie "none" pour url vide, et un user qui colle une URL
        # arbitraire dans .env doit pas pouvoir lire le filesystem local.
        if not (self.webhook_url.startswith("https://") or self.webhook_url.startswith("http://")):
            log.warning("notifier.bad_scheme", url=self.webhook_url[:50])
            return False

        body_bytes = json.dumps(payload).encode("utf-8")
        # Scheme http(s) déjà validé ci-dessus → S310 légitimement bypass.
        req = urllib.request.Request(  # noqa: S310
            self.webhook_url,
            data=body_bytes,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ia-expert-army-notifier/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:  # noqa: S310
                # Discord renvoie 204, Slack 200, Telegram 200 — tout 2xx est OK
                if 200 <= resp.status < 300:
                    log.info("notifier.sent", backend=self.backend, status=resp.status)
                    return True
                log.warning("notifier.bad_status", backend=self.backend, status=resp.status)
                return False
        except urllib.error.HTTPError as e:
            # Lecture du body d'erreur pour debug (Discord renvoie un JSON détaillé)
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                err_body = ""
            log.warning(
                "notifier.http_error",
                backend=self.backend,
                status=e.code,
                error=err_body,
            )
            return False
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log.warning("notifier.connection_error", backend=self.backend, error=str(e))
            return False
        except Exception as e:
            # Garde-fou final : aucune exception ne doit JAMAIS faire crash le caller.
            # Les notifications échouées sont au pire loggées et perdues — bien moins
            # grave que de tuer un autonomous_run en cours.
            log.warning("notifier.unexpected_error", error=str(e), error_type=type(e).__name__)
            return False

    # ===== Helpers de convenance =====

    def info(self, title: str, body: str) -> bool:
        return self.send(NotifyLevel.INFO, title, body)

    def success(self, title: str, body: str) -> bool:
        return self.send(NotifyLevel.SUCCESS, title, body)

    def warning(self, title: str, body: str) -> bool:
        return self.send(NotifyLevel.WARNING, title, body)

    def critical(self, title: str, body: str) -> bool:
        return self.send(NotifyLevel.CRITICAL, title, body)


def get_notifier_from_settings() -> Notifier:
    """Construit un Notifier depuis Settings (NOTIFY_WEBHOOK_URL + NOTIFY_BACKEND).

    Utilitaire pour les scripts : `notifier = get_notifier_from_settings()`.
    Si pas configuré, renvoie un Notifier disabled (no-op silencieux).
    """
    from src.core.config import get_settings

    s = get_settings()
    return Notifier(
        webhook_url=s.notify_webhook_url,
        backend=s.notify_backend,
    )
