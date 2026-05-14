"""Tests d'assignation des tiers Anthropic par agent — garde-fou anti-dérive.

Sprint EEE (2026-05-14) : tier mixing pour réduire le coût Anthropic.
On a déplacé SkillExtractor + MetaDecomposer de Opus → Sonnet (synthèse
template-guidée, pas de jugement critique). Économie attendue ~10-20%
sur les missions cross-guildes (MetaDecomposer en amont de chaque) et
sur le mining nightly (SkillExtractor).

Ces tests garantissent que :
  1. Le tier de chaque agent reste explicite et documenté
  2. Aucun "downgrade" silencieux d'un agent critique (Architect, QG, BA)
  3. Aucun "upgrade" silencieux d'un agent économe (Sonnet → Opus)
  4. Le ratio Opus/total reste sous contrôle (frein à la dérive)

Cf. ADR-016 (à venir) pour la stratégie de tier mixing complète.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.config import Settings
from src.guilds.business.agents import BusinessAnalyst, LegalReviewer, ProjectManager
from src.guilds.creative.agents import ContentStrategist, Copywriter, Editor
from src.guilds.research.agents import (
    DocumentSynthesizer,
    ResearchLead,
    ResearchReviewer,
    TechWatch,
)
from src.learning.skill_extractor import SkillExtractor
from src.memory.file_memory import FileMemory
from src.orchestrator.agents import (
    BackendDeveloper,
    ChiefOrchestrator,
    CodeReviewer,
    SecurityAuditor,
    SoftwareArchitect,
)
from src.orchestrator.meta_workflow import MetaDecomposer
from src.orchestrator.quality_guardian import QualityGuardian


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


# ============================================================================
# Tier "strategic" (Opus) — agents à jugement critique
# ============================================================================
# Critère : si l'agent se trompe, la mission entière est compromise et le
# repair loop ne peut pas rattraper (le mauvais skeleton entraîne du code
# pourri sur lequel le reviewer ne peut que mettre REJECTED).


def test_software_architect_uses_opus(settings: Settings, memory: FileMemory) -> None:
    """SoftwareArchitect produit le squelette dont dépend tout le reste —
    erreur d'arch = mission ratée. Coût Opus justifié."""
    agent = SoftwareArchitect(memory=memory, settings=settings)
    assert agent.model == settings.model_strategic, (
        f"SoftwareArchitect doit rester Opus (raisonnement architectural critique). "
        f"Actuellement : {agent.model}"
    )


def test_quality_guardian_uses_opus(settings: Settings, memory: FileMemory) -> None:
    """Quality Guardian est l'arbitre méta cross-guilde. Sa raison d'être est
    le discernement nuancé — pas de tier inférieur acceptable."""
    agent = QualityGuardian(memory=memory, settings=settings)
    assert agent.model == settings.model_strategic, (
        f"QualityGuardian doit rester Opus (arbitrage méta-cross-guilde). "
        f"Actuellement : {agent.model}"
    )


def test_business_analyst_uses_opus(settings: Settings, memory: FileMemory) -> None:
    """BusinessAnalyst engage des décisions humaines (verdict viable/non) —
    raisonnement économique nuancé requis."""
    agent = BusinessAnalyst(memory=memory, settings=settings)
    assert agent.model == settings.model_strategic, (
        f"BusinessAnalyst doit rester Opus (raisonnement économique → décisions). "
        f"Actuellement : {agent.model}"
    )


def test_chief_orchestrator_uses_opus(settings: Settings, memory: FileMemory) -> None:
    """ChiefOrchestrator décompose la mission — erreur ici = travail downstream
    sur le mauvais problème. Pour l'instant on garde Opus, candidate vague 2 EEE."""
    agent = ChiefOrchestrator(memory=memory, settings=settings)
    assert agent.model == settings.model_strategic, (
        f"ChiefOrchestrator garde Opus pour l'instant (vague 2 EEE prévue). "
        f"Actuellement : {agent.model}"
    )


def test_research_lead_uses_opus(settings: Settings, memory: FileMemory) -> None:
    """ResearchLead produit le plan de recherche — angle de découpage critique
    pour la qualité downstream. Garde Opus, vague 2 EEE prévue."""
    agent = ResearchLead(memory=memory, settings=settings)
    assert agent.model == settings.model_strategic, (
        f"ResearchLead garde Opus pour l'instant (vague 2 EEE prévue). "
        f"Actuellement : {agent.model}"
    )


def test_content_strategist_uses_opus(settings: Settings, memory: FileMemory) -> None:
    """ContentStrategist produit le brief — angle / positioning critique pour
    la qualité downstream. Garde Opus, vague 2 EEE prévue."""
    agent = ContentStrategist(memory=memory, settings=settings)
    assert agent.model == settings.model_strategic, (
        f"ContentStrategist garde Opus pour l'instant (vague 2 EEE prévue). "
        f"Actuellement : {agent.model}"
    )


# ============================================================================
# Tier "operational" (Sonnet) — production / review structurée
# ============================================================================


def test_backend_developer_uses_sonnet(settings: Settings, memory: FileMemory) -> None:
    """BackendDeveloper produit du code suivant un plan d'architecte. Sonnet
    suffit (et permet max_tokens=16384 sans coût Opus)."""
    agent = BackendDeveloper(memory=memory, settings=settings)
    assert agent.model == settings.model_operational


def test_code_reviewer_uses_sonnet(settings: Settings, memory: FileMemory) -> None:
    """CodeReviewer juge sur critères structurés (correctness/style/coverage).
    Sonnet adéquat — le QG re-couvre le jugement nuancé en méta."""
    agent = CodeReviewer(memory=memory, settings=settings)
    assert agent.model == settings.model_operational


def test_security_auditor_uses_sonnet(settings: Settings, memory: FileMemory) -> None:
    """SecurityAuditor checkliste OWASP — pattern matching technique."""
    agent = SecurityAuditor(memory=memory, settings=settings)
    assert agent.model == settings.model_operational


def test_document_synthesizer_uses_sonnet(settings: Settings, memory: FileMemory) -> None:
    """DocumentSynthesizer agrège les findings du TechWatch en markdown."""
    agent = DocumentSynthesizer(memory=memory, settings=settings)
    assert agent.model == settings.model_operational


def test_research_reviewer_uses_sonnet(settings: Settings, memory: FileMemory) -> None:
    """ResearchReviewer évalue selon template (sources, divergences, etc.)."""
    agent = ResearchReviewer(memory=memory, settings=settings)
    assert agent.model == settings.model_operational


def test_copywriter_uses_sonnet(settings: Settings, memory: FileMemory) -> None:
    """Copywriter écrit selon brief — Sonnet excellent en rédaction."""
    agent = Copywriter(memory=memory, settings=settings)
    assert agent.model == settings.model_operational


def test_editor_uses_sonnet(settings: Settings, memory: FileMemory) -> None:
    """Editor révise selon checklist éditoriale."""
    agent = Editor(memory=memory, settings=settings)
    assert agent.model == settings.model_operational


def test_project_manager_uses_sonnet(settings: Settings, memory: FileMemory) -> None:
    """ProjectManager planifie selon template (milestones, scope, risks)."""
    agent = ProjectManager(memory=memory, settings=settings)
    assert agent.model == settings.model_operational


def test_legal_reviewer_uses_sonnet(settings: Settings, memory: FileMemory) -> None:
    """LegalReviewer applique des règles de conformité — pattern matching
    juridique (RGPD, mentions, etc.)."""
    agent = LegalReviewer(memory=memory, settings=settings)
    assert agent.model == settings.model_operational


# ============================================================================
# Sprint EEE — Tiers descendus de Opus → Sonnet
# ============================================================================
# Ces tests sont les "verrous" de Sprint EEE. Ils plantent si quelqu'un
# remet ces agents en Opus sans audit conscient.


def test_skill_extractor_sprint_eee_moved_to_sonnet(
    settings: Settings, memory: FileMemory
) -> None:
    """Sprint EEE : SkillExtractor passe Opus → Sonnet.

    Justification : tâche = synthèse d'épisodes déjà structurés vers template
    YAML strict. Sonnet gère cette synthèse. Tourne en NIGHTLY → impact
    qualité court terme nul (rollback trivial si dégradation observée)."""
    agent = SkillExtractor(memory=memory, settings=settings)
    assert agent.model == settings.model_operational, (
        "Sprint EEE a déplacé SkillExtractor en Sonnet. "
        "Si vous le remettez en Opus, documentez la régression observée "
        "(ADR-016 + miner stats avant/après)."
    )


def test_meta_decomposer_sprint_eee_moved_to_sonnet(
    settings: Settings, memory: FileMemory
) -> None:
    """Sprint EEE : MetaDecomposer passe Opus → Sonnet.

    Justification : décomposition très contrainte (4 guildes valides max,
    4 sous-missions max, depends_on borné). Sonnet gère ce planning contraint.
    Économie ~5x sur ce poste, qui s'applique à CHAQUE mission cross-guildes."""
    agent = MetaDecomposer(memory=memory, settings=settings)
    assert agent.model == settings.model_operational, (
        "Sprint EEE a déplacé MetaDecomposer en Sonnet. "
        "Si vous le remettez en Opus, documentez la régression observée."
    )


# ============================================================================
# Tier "bulk" (Haiku) — balayage économe
# ============================================================================


def test_tech_watch_uses_haiku(settings: Settings, memory: FileMemory) -> None:
    """TechWatch fait du balayage de connaissances — Haiku largement suffisant
    (et permet max_tokens=8192 à coût négligeable)."""
    agent = TechWatch(memory=memory, settings=settings)
    assert agent.model == settings.model_bulk


# ============================================================================
# Garde-fou méta : ratio Opus/total
# ============================================================================


def test_opus_agent_count_under_threshold(settings: Settings, memory: FileMemory) -> None:
    """Garde-fou anti-dérive : pas plus de 7 agents en Opus.

    Au-delà, le coût Anthropic devient déraisonnable (Opus ~5x Sonnet).
    Si quelqu'un veut ajouter un nouvel agent Opus, il doit soit :
      - bumper ce seuil consciemment (avec ADR justifiant)
      - soit déplacer un autre Opus → Sonnet en compensation

    État au Sprint EEE : 6 agents Opus restants
    (Architect, QG, BA, ChiefOrchestrator, ResearchLead, ContentStrategist).
    """
    all_agents = [
        SoftwareArchitect(memory=memory, settings=settings),
        QualityGuardian(memory=memory, settings=settings),
        BusinessAnalyst(memory=memory, settings=settings),
        ChiefOrchestrator(memory=memory, settings=settings),
        ResearchLead(memory=memory, settings=settings),
        ContentStrategist(memory=memory, settings=settings),
        BackendDeveloper(memory=memory, settings=settings),
        CodeReviewer(memory=memory, settings=settings),
        SecurityAuditor(memory=memory, settings=settings),
        DocumentSynthesizer(memory=memory, settings=settings),
        ResearchReviewer(memory=memory, settings=settings),
        Copywriter(memory=memory, settings=settings),
        Editor(memory=memory, settings=settings),
        ProjectManager(memory=memory, settings=settings),
        LegalReviewer(memory=memory, settings=settings),
        SkillExtractor(memory=memory, settings=settings),
        MetaDecomposer(memory=memory, settings=settings),
        TechWatch(memory=memory, settings=settings),
    ]

    opus_count = sum(1 for a in all_agents if a.model == settings.model_strategic)
    assert opus_count <= 7, (
        f"Trop d'agents en Opus ({opus_count}). Maximum recommandé : 7. "
        "Soit déplacer un Opus en Sonnet, soit bumper le seuil + ADR."
    )

    sonnet_count = sum(1 for a in all_agents if a.model == settings.model_operational)
    haiku_count = sum(1 for a in all_agents if a.model == settings.model_bulk)
    total = opus_count + sonnet_count + haiku_count
    assert total == len(all_agents), (
        f"Tous les agents doivent matcher un des 3 tiers. "
        f"Opus={opus_count}, Sonnet={sonnet_count}, Haiku={haiku_count}, total agents={len(all_agents)}"
    )
