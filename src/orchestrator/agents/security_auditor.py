"""SecurityAuditor — audit sécurité OWASP/secrets/pratiques défensives (Sprint AAA).

Complémentaire au CodeReviewer (qualité technique), pas redondant. Intervient
APRÈS le CodeReviewer sur les missions APPROVED — si findings BLOCKER/MAJOR,
peut downgrader le verdict à NEEDS_CHANGES.

Tier Sonnet (5× moins cher qu'Opus, suffit pour les patterns OWASP standards).
Activable via `Settings.enable_security_auditor`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from src.core.config import Settings, get_settings
from src.learning.skills_library import SkillsLibrary
from src.memory.file_memory import FileMemory
from src.memory.vector_memory import VectorMemory
from src.orchestrator.agents._parsers import extract_yaml
from src.orchestrator.base_agent import AgentInput, BaseAgent

_PROMPT = Path(__file__).resolve().parents[3] / "prompts" / "orchestrator" / "security_auditor.md"


class SecurityAuditor(BaseAgent):
    # Findings YAML : 0-5 issues avec location + remediation détaillées.
    # 4096 suffit largement (le prompt cappe à 5 findings max).
    DEFAULT_MAX_TOKENS = 4096

    def __init__(
        self,
        memory: FileMemory,
        settings: Settings | None = None,
        client: AsyncOpenAI | None = None,
        vector_memory: VectorMemory | None = None,
        skills_library: SkillsLibrary | None = None,
    ) -> None:
        s = settings or get_settings()
        super().__init__(
            name="security_auditor",
            prompt_path=_PROMPT,
            model=s.model_operational,  # Sonnet — discernement suffisant pour OWASP
            memory=memory,
            settings=s,
            client=client,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            vector_memory=vector_memory,
            skills_library=skills_library,
        )

    def parse_output(self, raw: str, agent_input: AgentInput) -> dict[str, Any] | None:
        return extract_yaml(raw)


# Sévérités utilisées pour la décision de downgrade
SEVERITY_BLOCKER = "BLOCKER"
SEVERITY_MAJOR = "MAJOR"
SEVERITY_MINOR = "MINOR"
SEVERITY_NIT = "NIT"

_DOWNGRADE_SEVERITIES = {SEVERITY_BLOCKER, SEVERITY_MAJOR}


def has_downgrade_findings(parsed: dict[str, Any] | None) -> bool:
    """Détermine si l'audit sécurité doit downgrader le verdict guilde.

    Vrai SSI au moins un finding de sévérité BLOCKER ou MAJOR. MINOR/NIT
    sont informatifs et ne bloquent pas.
    """
    if not parsed:
        return False
    findings = parsed.get("findings") or []
    if not isinstance(findings, list):
        return False
    for f in findings:
        if not isinstance(f, dict):
            continue
        sev = str(f.get("severity", "")).strip().upper()
        if sev in _DOWNGRADE_SEVERITIES:
            return True
    return False
