"""Tests pour src.core.config (bascule Ollama, ADR-025)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config import Settings


def test_settings_loads_with_defaults() -> None:
    """Backend Ollama : aucune variable requise, tout a un défaut sensé."""
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.ollama_base_url == "http://localhost:11434/v1"
    assert s.ollama_api_key == "ollama"
    assert s.model_strategic.startswith("qwen")
    assert s.model_operational.startswith("qwen")
    assert s.model_bulk.startswith("qwen")
    # Budget = 0 par défaut depuis ADR-025 (Ollama local = gratuit)
    assert s.daily_budget_usd == 0.0
    assert s.max_agent_turns >= 1


def test_settings_ollama_base_url_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    """L'URL Ollama doit pouvoir viser un LAN / un autre port."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.42:11500/v1")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.ollama_base_url == "http://192.168.1.42:11500/v1"


def test_settings_models_overridable_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les 3 tiers de modèles doivent être configurables via .env."""
    monkeypatch.setenv("MODEL_STRATEGIC", "llama3.3:70b")
    monkeypatch.setenv("MODEL_OPERATIONAL", "qwen2.5-coder:14b")
    monkeypatch.setenv("MODEL_BULK", "llama3.2:3b")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.model_strategic == "llama3.3:70b"
    assert s.model_operational == "qwen2.5-coder:14b"
    assert s.model_bulk == "llama3.2:3b"


def test_settings_circuit_breaker_in_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRCUIT_BREAKER_ERROR_RATE", "0.5")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert 0 <= s.circuit_breaker_error_rate <= 1


def test_settings_rejects_invalid_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "BANANA")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


# ===== Sprint GGG.1 — settings adaptables pour VPS =====


def test_settings_enable_sandbox_default_true() -> None:
    """Sprint GGG.1 : enable_sandbox=True par défaut (préserve le comportement
    existant). Doit être désactivable via env var pour les VPS sans Docker."""
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.enable_sandbox is True


def test_settings_enable_sandbox_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sprint GGG.1 : ENABLE_SANDBOX=false dans .env doit court-circuiter
    validate_files_in_sandbox sur VPS sans Docker."""
    monkeypatch.setenv("ENABLE_SANDBOX", "false")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.enable_sandbox is False


def test_settings_vps_profile_default_empty() -> None:
    """Sprint GGG.1 : vps_profile vide par défaut (auto/inconnu)."""
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.vps_profile == ""


@pytest.mark.parametrize("profile", ["vps1", "vps2", "vps3", "local", ""])
def test_settings_vps_profile_accepts_known_values(
    monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    """Sprint GGG.1 : les 4 profiles documentés + '' doivent être acceptés."""
    monkeypatch.setenv("VPS_PROFILE", profile)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.vps_profile == profile


def test_settings_vps_profile_rejects_unknown_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sprint GGG.1 : un profile inconnu (typo, valeur arbitraire) doit être rejeté."""
    monkeypatch.setenv("VPS_PROFILE", "vps42")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


# ===== Sprint HHH — Notifier =====


def test_settings_notify_disabled_by_default() -> None:
    """Sprint HHH : notify_webhook_url vide par défaut → no-op silencieux."""
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.notify_webhook_url == ""
    assert s.notify_backend == "auto"


def test_settings_notify_url_loaded_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://discord.com/api/webhooks/X/Y")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.notify_webhook_url == "https://discord.com/api/webhooks/X/Y"


@pytest.mark.parametrize("backend", ["auto", "discord", "slack", "telegram", "generic", "none"])
def test_settings_notify_backend_accepts_known_values(
    monkeypatch: pytest.MonkeyPatch, backend: str
) -> None:
    monkeypatch.setenv("NOTIFY_BACKEND", backend)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.notify_backend == backend


def test_settings_notify_backend_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFY_BACKEND", "smoke-signal")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
