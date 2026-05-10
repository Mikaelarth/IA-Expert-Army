"""Tests pour src.core.config."""
from __future__ import annotations

import os

import pytest

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
    with pytest.raises(Exception):
        Settings(_env_file=None)  # type: ignore[call-arg]
