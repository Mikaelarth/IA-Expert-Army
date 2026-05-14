"""Tests pour src.core.config."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config import Settings


def test_settings_loads_with_minimum_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-1234567890")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.anthropic_api_key.get_secret_value() == "sk-ant-test-1234567890"
    assert s.model_strategic.startswith("claude-opus")
    assert s.model_operational.startswith("claude-sonnet")
    assert s.model_bulk.startswith("claude-haiku")
    assert s.daily_budget_usd > 0
    assert s.max_agent_turns >= 1


def test_settings_circuit_breaker_in_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("CIRCUIT_BREAKER_ERROR_RATE", "0.5")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert 0 <= s.circuit_breaker_error_rate <= 1


def test_settings_rejects_invalid_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("LOG_LEVEL", "BANANA")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


# ===== Sprint GGG.1 — settings adaptables pour VPS =====


def test_settings_enable_sandbox_default_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sprint GGG.1 : enable_sandbox=True par défaut (préserve le comportement
    existant). Doit être désactivable via env var pour les VPS sans Docker."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.enable_sandbox is True


def test_settings_enable_sandbox_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sprint GGG.1 : ENABLE_SANDBOX=false dans .env doit court-circuiter
    validate_files_in_sandbox sur VPS sans Docker."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ENABLE_SANDBOX", "false")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.enable_sandbox is False


def test_settings_vps_profile_default_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sprint GGG.1 : vps_profile vide par défaut (auto/inconnu)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.vps_profile == ""


@pytest.mark.parametrize("profile", ["vps1", "vps2", "vps3", "local", ""])
def test_settings_vps_profile_accepts_known_values(
    monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    """Sprint GGG.1 : les 4 profiles documentés + '' doivent être acceptés."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VPS_PROFILE", profile)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.vps_profile == profile


def test_settings_vps_profile_rejects_unknown_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sprint GGG.1 : un profile inconnu (typo, valeur arbitraire) doit être rejeté."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VPS_PROFILE", "vps42")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
