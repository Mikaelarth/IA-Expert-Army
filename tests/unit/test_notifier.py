"""Tests pour src.core.notifier.

Couvre :
  - Détection automatique du backend depuis l'URL
  - Génération de payloads par backend (Discord/Slack/Telegram/generic)
  - Comportement quand désactivé (URL vide)
  - Échecs réseau / HTTP : pas de crash, log seulement
  - Truncation des messages trop longs
  - Helpers info/success/warning/critical
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.core.notifier import (
    Notifier,
    NotifyLevel,
    _build_payload,
    _detect_backend,
    _truncate,
)

# ===== Détection backend =====


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://discord.com/api/webhooks/123/abc", "discord"),
        ("https://discordapp.com/api/webhooks/456/xyz", "discord"),
        ("https://hooks.slack.com/services/T01/B02/abc", "slack"),
        ("https://api.telegram.org/bot1234:ABCDEF/sendMessage?chat_id=999", "telegram"),
        ("https://my-n8n.example.com/webhook/abc", "generic"),
        ("https://pipedream.com/webhook/xyz", "generic"),
        ("", "none"),
        ("   ", "generic"),  # non-vide même si whitespace
    ],
)
def test_detect_backend(url: str, expected: str) -> None:
    """Le détecteur reconnaît les patterns Discord/Slack/Telegram, sinon generic."""
    assert _detect_backend(url) == expected


# ===== Truncate =====


def test_truncate_keeps_short_text() -> None:
    assert _truncate("hello", 100) == "hello"


def test_truncate_cuts_long_text_with_ellipsis() -> None:
    long = "x" * 5000
    out = _truncate(long, 100)
    assert len(out) <= 100
    assert out.endswith("…(tronqué)")


# ===== Payloads par backend =====


def test_payload_discord_has_embeds_with_color() -> None:
    p = _build_payload("discord", NotifyLevel.WARNING, "Test", "Body content")
    assert "embeds" in p
    assert len(p["embeds"]) == 1
    embed = p["embeds"][0]
    assert "⚠️" in embed["title"]
    assert "Test" in embed["title"]
    assert embed["description"] == "Body content"
    assert embed["color"] == 0xF39C12  # orange warning


def test_payload_discord_critical_uses_red_color() -> None:
    p = _build_payload("discord", NotifyLevel.CRITICAL, "Crash", "All hands")
    assert p["embeds"][0]["color"] == 0xE74C3C  # rouge


def test_payload_slack_has_blocks_with_header() -> None:
    p = _build_payload("slack", NotifyLevel.SUCCESS, "Mission OK", "Score 0.95")
    assert "attachments" in p
    blocks = p["attachments"][0]["blocks"]
    assert any(b["type"] == "header" for b in blocks)
    assert any(b["type"] == "section" for b in blocks)
    # Couleur slack
    assert p["attachments"][0]["color"] == "#2ecc71"


def test_payload_telegram_has_markdown_text() -> None:
    p = _build_payload("telegram", NotifyLevel.INFO, "Title", "Body")
    assert p["parse_mode"] == "Markdown"
    assert "*Title*" in p["text"]
    assert "Body" in p["text"]


def test_payload_generic_is_flat_json() -> None:
    p = _build_payload("generic", NotifyLevel.WARNING, "Title", "Body")
    assert p["level"] == "warning"
    assert p["title"] == "Title"
    assert p["body"] == "Body"
    assert p["source"] == "ia-expert-army"
    assert "timestamp" in p


def test_payload_generic_for_unknown_backend() -> None:
    """Backend inattendu → fallback sur generic (jamais de crash)."""
    p = _build_payload("none", NotifyLevel.INFO, "T", "B")
    # _build_payload renvoie generic pour tout backend non reconnu
    assert "level" in p


# ===== Notifier instance =====


def test_notifier_disabled_when_url_empty() -> None:
    n = Notifier(webhook_url="")
    assert n.is_enabled is False
    # send doit retourner False sans rien tenter
    assert n.send(NotifyLevel.INFO, "X", "Y") is False


def test_notifier_disabled_when_url_none() -> None:
    n = Notifier(webhook_url=None)
    assert n.is_enabled is False


def test_notifier_auto_detects_backend() -> None:
    n = Notifier(webhook_url="https://discord.com/api/webhooks/123/abc")
    assert n.backend == "discord"
    assert n.is_enabled is True


def test_notifier_explicit_backend_overrides_auto() -> None:
    """Un backend explicite gagne sur auto-détection."""
    n = Notifier(
        webhook_url="https://discord.com/api/webhooks/123/abc",
        backend="generic",
    )
    assert n.backend == "generic"


def test_notifier_backend_none_disables_even_with_url() -> None:
    n = Notifier(webhook_url="https://example.com/hook", backend="none")
    assert n.is_enabled is False


# ===== Send : POST mocké =====


def _mock_response(status: int = 200) -> Any:
    """Construit un context manager mock pour urlopen."""
    resp = MagicMock()
    resp.status = status
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_notifier_send_posts_correct_payload_to_discord() -> None:
    n = Notifier(webhook_url="https://discord.com/api/webhooks/X/Y")
    captured: dict[str, Any] = {}

    def _fake_urlopen(req: Any, timeout: float = 0) -> Any:
        captured["url"] = req.full_url
        captured["data"] = req.data.decode("utf-8")
        captured["method"] = req.get_method()
        captured["content_type"] = req.headers.get("Content-type")
        return _mock_response(204)  # Discord renvoie 204 No Content

    with patch("src.core.notifier.urllib.request.urlopen", side_effect=_fake_urlopen):
        result = n.send(NotifyLevel.INFO, "Hello", "World")

    assert result is True
    assert captured["method"] == "POST"
    assert captured["url"] == "https://discord.com/api/webhooks/X/Y"
    assert captured["content_type"] == "application/json"
    payload = json.loads(captured["data"])
    assert "embeds" in payload  # format Discord


def test_notifier_send_returns_false_on_http_error() -> None:
    """Une 4xx/5xx ne doit pas crash, juste False."""
    import urllib.error

    n = Notifier(webhook_url="https://example.com/hook")

    def _raises_http_error(req: Any, timeout: float = 0) -> Any:
        raise urllib.error.HTTPError(
            "https://example.com/hook",
            401,
            "Unauthorized",
            {},
            None,  # type: ignore[arg-type]
        )

    with patch("src.core.notifier.urllib.request.urlopen", side_effect=_raises_http_error):
        result = n.send(NotifyLevel.INFO, "X", "Y")

    assert result is False


def test_notifier_send_returns_false_on_connection_error() -> None:
    """Connexion impossible → log + False, pas de crash."""
    import urllib.error

    n = Notifier(webhook_url="https://nonexistent-host-xyz.invalid/hook")

    def _raises_url_error(req: Any, timeout: float = 0) -> Any:
        raise urllib.error.URLError("Name resolution failed")

    with patch("src.core.notifier.urllib.request.urlopen", side_effect=_raises_url_error):
        result = n.send(NotifyLevel.WARNING, "Net down", "Body")

    assert result is False


def test_notifier_send_returns_false_on_timeout() -> None:
    n = Notifier(webhook_url="https://slow.example.com/hook")

    def _raises_timeout(req: Any, timeout: float = 0) -> Any:
        raise TimeoutError("read timed out")

    with patch("src.core.notifier.urllib.request.urlopen", side_effect=_raises_timeout):
        assert n.send(NotifyLevel.INFO, "X", "Y") is False


def test_notifier_send_returns_false_on_unexpected_exception() -> None:
    """Garde-fou final : même un Exception inattendue ne fait pas crash."""
    n = Notifier(webhook_url="https://example.com/hook")

    def _raises_random(req: Any, timeout: float = 0) -> Any:
        raise RuntimeError("totally unexpected")

    with patch("src.core.notifier.urllib.request.urlopen", side_effect=_raises_random):
        assert n.send(NotifyLevel.CRITICAL, "X", "Y") is False


def test_notifier_string_level_is_coerced_to_enum() -> None:
    """send accepte un str ou un NotifyLevel."""
    n = Notifier(webhook_url="https://example.com/hook")
    captured: dict[str, Any] = {}

    def _capture(req: Any, timeout: float = 0) -> Any:
        captured["data"] = req.data.decode("utf-8")
        return _mock_response(200)

    with patch("src.core.notifier.urllib.request.urlopen", side_effect=_capture):
        n.send("warning", "T", "B")

    payload = json.loads(captured["data"])
    assert payload["level"] == "warning"  # generic backend


def test_notifier_string_level_unknown_falls_back_to_info() -> None:
    n = Notifier(webhook_url="https://example.com/hook")
    captured: dict[str, Any] = {}

    def _capture(req: Any, timeout: float = 0) -> Any:
        captured["data"] = req.data.decode("utf-8")
        return _mock_response(200)

    with patch("src.core.notifier.urllib.request.urlopen", side_effect=_capture):
        n.send("frobnicate", "T", "B")  # level inconnu

    payload = json.loads(captured["data"])
    assert payload["level"] == "info"  # fallback


# ===== Helpers =====


def test_notifier_helpers_use_correct_levels() -> None:
    """info/success/warning/critical doivent passer le bon level."""
    n = Notifier(webhook_url="https://example.com/hook")
    captured_levels: list[str] = []

    def _capture(req: Any, timeout: float = 0) -> Any:
        captured_levels.append(json.loads(req.data.decode("utf-8"))["level"])
        return _mock_response(200)

    with patch("src.core.notifier.urllib.request.urlopen", side_effect=_capture):
        n.info("T", "B")
        n.success("T", "B")
        n.warning("T", "B")
        n.critical("T", "B")

    assert captured_levels == ["info", "success", "warning", "critical"]


# ===== Long body truncation =====


def test_notifier_truncates_huge_body_for_discord() -> None:
    """Discord limite description à ~4096 chars. Le notifier doit tronquer."""
    huge_body = "x" * 100_000
    n = Notifier(webhook_url="https://discord.com/api/webhooks/X/Y")
    captured: dict[str, Any] = {}

    def _capture(req: Any, timeout: float = 0) -> Any:
        captured["data"] = req.data.decode("utf-8")
        return _mock_response(204)

    with patch("src.core.notifier.urllib.request.urlopen", side_effect=_capture):
        n.send(NotifyLevel.INFO, "Big", huge_body)

    payload = json.loads(captured["data"])
    description = payload["embeds"][0]["description"]
    assert len(description) <= 4096
    assert "(tronqué)" in description


# ===== get_notifier_from_settings =====


def test_get_notifier_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.notifier import get_notifier_from_settings

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://discord.com/api/webhooks/X/Y")
    # get_settings est cached, on doit clear pour que le env var prenne effet
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    n = get_notifier_from_settings()
    assert n.is_enabled
    assert n.backend == "discord"
    get_settings.cache_clear()  # type: ignore[attr-defined]
