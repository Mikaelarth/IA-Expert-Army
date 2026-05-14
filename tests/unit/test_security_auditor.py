"""Tests Sprint AAA — SecurityAuditor (audit OWASP/secrets engineering).

Couvre :
- has_downgrade_findings : pure function pour décision BLOCKER/MAJOR
- SecurityAuditor agent class : tier, max_tokens, prompt loads
- PatternMiner whitelist inclut security_auditor
- Integration Workflow : opt-in via Settings, downgrade conditionnel
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.config import Settings
from src.learning.pattern_miner import PatternMiner
from src.memory.file_memory import FileMemory
from src.orchestrator.agents import SecurityAuditor
from src.orchestrator.agents.security_auditor import (
    SEVERITY_BLOCKER,
    SEVERITY_MAJOR,
    SEVERITY_MINOR,
    SEVERITY_NIT,
    has_downgrade_findings,
)
from src.orchestrator.base_agent import AgentOutput
from src.orchestrator.workflow import Workflow


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def _agent_output(
    agent_name: str,
    raw_text: str = "ok",
    parsed: object = None,
    success: bool = True,
) -> AgentOutput:
    return AgentOutput(
        agent_name=agent_name,
        mission_id=uuid4(),
        success=success,
        raw_text=raw_text,
        parsed=parsed,
        tokens_in=100,
        tokens_out=200,
        cost_usd=0.05,
        duration_seconds=1.0,
    )


# ===== has_downgrade_findings (pure function) =====


def test_has_downgrade_findings_none_or_empty() -> None:
    assert has_downgrade_findings(None) is False
    assert has_downgrade_findings({}) is False
    assert has_downgrade_findings({"findings": []}) is False


def test_has_downgrade_findings_only_minor_nit() -> None:
    """MINOR et NIT ne downgrade PAS — verdict reste APPROVED."""
    parsed = {
        "findings": [
            {"severity": SEVERITY_MINOR, "issue": "logs verbeux"},
            {"severity": SEVERITY_NIT, "issue": "header missing"},
        ]
    }
    assert has_downgrade_findings(parsed) is False


def test_has_downgrade_findings_blocker_triggers() -> None:
    parsed = {"findings": [{"severity": SEVERITY_BLOCKER, "issue": "SQL injection"}]}
    assert has_downgrade_findings(parsed) is True


def test_has_downgrade_findings_major_triggers() -> None:
    parsed = {"findings": [{"severity": SEVERITY_MAJOR, "issue": "missing input validation"}]}
    assert has_downgrade_findings(parsed) is True


def test_has_downgrade_findings_case_insensitive_severity() -> None:
    """Le prompt peut produire 'blocker' minuscule — on accepte."""
    parsed = {"findings": [{"severity": "blocker", "issue": "..."}]}
    assert has_downgrade_findings(parsed) is True


def test_has_downgrade_findings_mixed_severities() -> None:
    """Si AU MOINS UN BLOCKER/MAJOR, downgrade."""
    parsed = {
        "findings": [
            {"severity": SEVERITY_NIT},
            {"severity": SEVERITY_MAJOR, "issue": "real one"},
            {"severity": SEVERITY_MINOR},
        ]
    }
    assert has_downgrade_findings(parsed) is True


def test_has_downgrade_findings_tolerates_malformed_findings() -> None:
    """Findings list contenant des non-dict — ne crash pas, ignore juste."""
    parsed = {"findings": ["not-a-dict", {"severity": SEVERITY_MAJOR}, None]}
    assert has_downgrade_findings(parsed) is True


# ===== SecurityAuditor agent class =====


def test_security_auditor_uses_operational_tier(settings: Settings, memory: FileMemory) -> None:
    """Sonnet (operational) — pas Opus, pour économie."""
    agent = SecurityAuditor(memory=memory, settings=settings)
    assert "sonnet" in agent.model.lower()


def test_security_auditor_max_tokens_4096(settings: Settings, memory: FileMemory) -> None:
    """4096 suffit (max 5 findings dans le prompt). Si on observe une saturation,
    bumper à 8192 et référencer l'incident dans le commentaire de l'agent."""
    agent = SecurityAuditor(memory=memory, settings=settings)
    assert agent.max_tokens >= 4096


def test_security_auditor_loads_prompt(settings: Settings, memory: FileMemory) -> None:
    agent = SecurityAuditor(memory=memory, settings=settings)
    assert "Security Auditor" in agent.system_prompt
    assert "OWASP" in agent.system_prompt


# ===== PatternMiner whitelist =====


def test_security_auditor_in_pattern_miner_whitelist() -> None:
    """Régression : si on ajoute un agent et qu'on oublie le whitelist, son
    apprentissage n'a pas lieu. Pattern récurrent observé sur 3 guildes."""
    assert "security_auditor" in PatternMiner.AGENT_WHITELIST


# ===== Settings =====


def test_settings_enable_security_auditor_defaults_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.enable_security_auditor is False


def test_settings_enable_security_auditor_overridable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ENABLE_SECURITY_AUDITOR", "true")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.enable_security_auditor is True


# ===== Workflow integration =====


def _engineering_mocks() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    """Helper : crée les 4 mocks orchestrator/architect/developer/reviewer."""
    orch = MagicMock()
    orch.run = AsyncMock(
        return_value=_agent_output(
            "chief_orchestrator", parsed={"subtasks": [{"title": "X"}]}, raw_text="d"
        )
    )
    arch = MagicMock()
    arch.run = AsyncMock(return_value=_agent_output("software_architect", raw_text="arch"))
    dev = MagicMock()
    dev.run = AsyncMock(return_value=_agent_output("backend_developer", parsed=[], raw_text="dev"))
    rev = MagicMock()
    rev.run = AsyncMock(
        return_value=_agent_output(
            "code_reviewer", parsed={"verdict": "APPROVED", "quality_score": 0.92}
        )
    )
    return orch, arch, dev, rev


@pytest.mark.asyncio
async def test_workflow_does_not_call_security_auditor_when_disabled(
    settings: Settings, memory: FileMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """enable_security_auditor=False (défaut) → pas d'instanciation ni d'appel."""
    wf = Workflow(memory=memory, settings=settings)
    wf.orchestrator, wf.architect, wf.developer, wf.reviewer = _engineering_mocks()

    # Spy sur SecurityAuditor pour vérifier qu'il n'est PAS instancié
    sec_spy = MagicMock()
    monkeypatch.setattr("src.orchestrator.workflow.SecurityAuditor", sec_spy)

    result = await wf.run(title="X", description="y")

    assert result.final_verdict == "APPROVED"
    sec_spy.assert_not_called()


@pytest.mark.asyncio
async def test_workflow_calls_security_auditor_when_enabled_and_approved(
    memory: FileMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """enable_security_auditor=True + verdict APPROVED → SecurityAuditor appelé.
    Si findings sont MINOR/NIT → verdict reste APPROVED."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ENABLE_SECURITY_AUDITOR", "true")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    wf = Workflow(memory=memory, settings=settings)
    wf.orchestrator, wf.architect, wf.developer, wf.reviewer = _engineering_mocks()

    # Mock SecurityAuditor : retourne findings MINOR seulement → pas de downgrade
    sec_mock_instance = MagicMock()
    sec_mock_instance.run = AsyncMock(
        return_value=_agent_output(
            "security_auditor",
            parsed={
                "verdict_sec": "APPROVED",
                "risk_level": "low",
                "findings": [{"severity": "MINOR", "category": "logs", "issue": "..."}],
            },
        )
    )
    monkeypatch.setattr(
        "src.orchestrator.workflow.SecurityAuditor", MagicMock(return_value=sec_mock_instance)
    )

    result = await wf.run(title="X", description="y")

    sec_mock_instance.run.assert_awaited_once()
    # Verdict guilde APPROVED préservé car aucun BLOCKER/MAJOR
    assert result.final_verdict == "APPROVED"


@pytest.mark.asyncio
async def test_workflow_security_auditor_downgrade_on_blocker(
    memory: FileMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SecurityAuditor flag BLOCKER → verdict downgrade à NEEDS_CHANGES → repair loop."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ENABLE_SECURITY_AUDITOR", "true")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    wf = Workflow(memory=memory, settings=settings)
    orch, arch, dev, rev = _engineering_mocks()
    # Pour le repair loop, on simule un 2e tour qui passe
    arch.run = AsyncMock(
        side_effect=[
            _agent_output("software_architect", raw_text="arch v1"),
            _agent_output("software_architect", raw_text="arch v2"),
        ]
    )
    dev.run = AsyncMock(
        side_effect=[
            _agent_output("backend_developer", parsed=[], raw_text="dev v1"),
            _agent_output("backend_developer", parsed=[], raw_text="dev v2"),
        ]
    )
    rev.run = AsyncMock(
        side_effect=[
            _agent_output("code_reviewer", parsed={"verdict": "APPROVED", "quality_score": 0.9}),
            _agent_output("code_reviewer", parsed={"verdict": "APPROVED", "quality_score": 0.94}),
        ]
    )
    wf.orchestrator, wf.architect, wf.developer, wf.reviewer = orch, arch, dev, rev

    sec_mock_instance = MagicMock()
    sec_mock_instance.run = AsyncMock(
        return_value=_agent_output(
            "security_auditor",
            raw_text="findings yaml",
            parsed={
                "verdict_sec": "NEEDS_CHANGES",
                "risk_level": "high",
                "findings": [
                    {
                        "severity": "BLOCKER",
                        "category": "injection_sql",
                        "location": "src/api/users.py:42",
                        "issue": "SQL injection via string concat",
                        "remediation": "Use parameterized queries",
                    }
                ],
            },
        )
    )
    monkeypatch.setattr(
        "src.orchestrator.workflow.SecurityAuditor", MagicMock(return_value=sec_mock_instance)
    )

    result = await wf.run(title="API endpoint", description="Create POST /users")

    # SecurityAuditor a été appelé 1× (sur le verdict initial APPROVED)
    sec_mock_instance.run.assert_awaited_once()
    # Le repair loop a été déclenché (architect + dev + reviewer appelés 2×)
    assert arch.run.call_count == 2
    assert dev.run.call_count == 2
    assert rev.run.call_count == 2
    # Verdict final = APPROVED (le repair a corrigé)
    assert result.final_verdict == "APPROVED"
    # L'architect v2 doit avoir reçu les findings security dans son contexte
    arch_v2_call = arch.run.call_args_list[1]
    arch_v2_input = (
        arch_v2_call.args[0] if arch_v2_call.args else arch_v2_call.kwargs.get("agent_input")
    )
    assert "security_findings_yaml" in arch_v2_input.context


@pytest.mark.asyncio
async def test_workflow_does_not_audit_when_reviewer_already_rejected(
    memory: FileMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si CodeReviewer NEEDS_CHANGES déjà → pas d'appel SecurityAuditor inutile.
    (Le repair loop tournera sans SecurityAuditor v1.)"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ENABLE_SECURITY_AUDITOR", "true")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    wf = Workflow(memory=memory, settings=settings)
    orch, arch, dev, rev = _engineering_mocks()
    # Reviewer retourne NEEDS_CHANGES
    rev.run = AsyncMock(
        side_effect=[
            _agent_output("code_reviewer", parsed={"verdict": "NEEDS_CHANGES"}),
            _agent_output("code_reviewer", parsed={"verdict": "APPROVED", "quality_score": 0.9}),
        ]
    )
    # Repair loop : architect/dev re-run
    arch.run = AsyncMock(
        side_effect=[
            _agent_output("software_architect"),
            _agent_output("software_architect"),
        ]
    )
    dev.run = AsyncMock(
        side_effect=[
            _agent_output("backend_developer", parsed=[]),
            _agent_output("backend_developer", parsed=[]),
        ]
    )
    wf.orchestrator, wf.architect, wf.developer, wf.reviewer = orch, arch, dev, rev

    sec_spy = MagicMock()
    sec_instance = MagicMock()
    sec_instance.run = AsyncMock()
    sec_spy.return_value = sec_instance
    monkeypatch.setattr("src.orchestrator.workflow.SecurityAuditor", sec_spy)

    await wf.run(title="X", description="y")

    # SecurityAuditor NE doit PAS avoir été instancié ni appelé
    sec_spy.assert_not_called()
    sec_instance.run.assert_not_called()
