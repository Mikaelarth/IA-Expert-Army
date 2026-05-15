"""Tests pour les checks de scripts/health_check.py — Sprint NNN.

On teste seulement les checks AJOUTÉS par Sprint NNN (ceux qui inspectent
des fichiers du repo : VPS config, coverage gate, deploy scripts, ADRs index,
notifier config). Les checks "live" (Docker, FileMemory, etc.) restent
exercés indirectement par les tests d'intégration.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Permet l'import du script health_check qui vit hors src/
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings nécessite une clé valide pour s'instancier."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    # Reset le cache de get_settings pour que les changements env prennent effet
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _reset_get_settings_cache() -> None:
    yield
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]


# ===== check_vps_config =====


def test_check_vps_config_default_shows_auto_and_sandbox_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sprint NNN : par défaut, vps_profile vide → 'auto/inconnu', sandbox ON."""
    monkeypatch.delenv("VPS_PROFILE", raising=False)
    monkeypatch.delenv("ENABLE_SANDBOX", raising=False)
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    from health_check import check_vps_config

    status, detail = check_vps_config()
    assert "OK" in status
    assert "auto/inconnu" in detail or "auto" in detail
    assert "ON" in detail


def test_check_vps_config_with_explicit_vps2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VPS_PROFILE", "vps2")
    monkeypatch.setenv("ENABLE_SANDBOX", "true")
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    from health_check import check_vps_config

    status, detail = check_vps_config()
    assert "OK" in status
    assert "vps2" in detail


def test_check_vps_config_sandbox_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_SANDBOX", "false")
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    from health_check import check_vps_config

    status, detail = check_vps_config()
    assert "OK" in status
    assert "OFF" in detail or "skip" in detail.lower()


# ===== check_coverage_config =====


def test_check_coverage_config_finds_fail_under() -> None:
    """Sprint NNN : vérifie que fail_under est bien dans pyproject.toml."""
    from health_check import check_coverage_config

    status, detail = check_coverage_config()
    assert "OK" in status
    assert "fail_under" in detail
    assert "90" in detail


# ===== check_adrs_index =====


def test_check_adrs_index_cohérent() -> None:
    """Sprint NNN : tous les ADR-NNN-*.md sur disque doivent être référencés
    dans docs/adr/README.md."""
    from health_check import check_adrs_index

    status, _detail = check_adrs_index()
    # Le projet est censé être propre — soit OK, soit WARN si quelqu'un a
    # ajouté un ADR sans MAJ l'index. Pas FAIL car ce serait gérable.
    assert "OK" in status or "WARN" in status


# ===== check_deploy_scripts =====


def test_check_deploy_scripts_both_present_and_valid() -> None:
    """Sprint NNN : les 2 scripts deploy_vps + migrate_vps doivent exister
    et avoir une syntaxe bash valide."""
    from health_check import check_deploy_scripts

    status, detail = check_deploy_scripts()
    # OK (bash dispo) ou WARN (bash absent — Windows pur)
    assert "OK" in status or "WARN" in status
    if "OK" in status:
        assert "2 scripts" in detail


# ===== check_notifier_config =====


def test_check_notifier_config_skipped_when_no_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sprint NNN : pas d'URL → SKIP (no-op silencieux, comportement attendu)."""
    monkeypatch.delenv("NOTIFY_WEBHOOK_URL", raising=False)
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    from health_check import check_notifier_config

    status, detail = check_notifier_config()
    assert "SKIP" in status
    assert "NOTIFY_WEBHOOK_URL" in detail


def test_check_notifier_config_ok_with_discord_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sprint NNN : URL Discord configurée → OK + backend détecté."""
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://discord.com/api/webhooks/123/abc")
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    from health_check import check_notifier_config

    status, detail = check_notifier_config()
    assert "OK" in status
    assert "discord" in detail


# ===== check_notifier_send_test (mocké pour ne pas envoyer en réel) =====


def test_check_notifier_send_test_skipped_without_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NOTIFY_WEBHOOK_URL", raising=False)
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    from health_check import check_notifier_send_test

    status, _detail = check_notifier_send_test()
    assert "SKIP" in status


def test_check_notifier_send_test_ok_when_send_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sprint NNN : avec webhook configuré + envoi mocké → OK."""
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://discord.com/api/webhooks/X/Y")
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    # Mock urllib.urlopen pour simuler un envoi réussi (204 Discord)
    from unittest.mock import MagicMock, patch

    fake_resp = MagicMock()
    fake_resp.status = 204
    fake_resp.__enter__ = MagicMock(return_value=fake_resp)
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch(
        "src.core.notifier.urllib.request.urlopen", return_value=fake_resp
    ):
        from health_check import check_notifier_send_test

        status, detail = check_notifier_send_test()

    assert "OK" in status
    assert "discord" in detail


def test_check_notifier_send_test_fails_when_send_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sprint NNN : si l'envoi échoue (réseau down, URL invalide), report FAIL."""
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://example.com/bad-webhook")
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    import urllib.error
    from unittest.mock import patch

    def _raises(req, timeout=0):
        raise urllib.error.URLError("network down")

    with patch("src.core.notifier.urllib.request.urlopen", side_effect=_raises):
        from health_check import check_notifier_send_test

        status, _detail = check_notifier_send_test()

    assert "FAIL" in status
