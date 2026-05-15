"""Smoke tests E2E du mode autonome — Sprint OOO.

Garantit que toute la chaîne autonomous_run fonctionne sans coût API :
  router → workflow → agents → archivage → digest

Le client AsyncAnthropic est mocké au niveau de src.orchestrator.base_agent
(le seul endroit qui instancie un client par défaut). Un FakeAsyncAnthropic
détecte l'agent appelant via son system prompt et renvoie une réponse canon
réaliste (YAML/markdown au format attendu par chaque parser).

Pourquoi ce test : avant Sprint OOO, on avait des tests unitaires par agent
et par workflow, mais AUCUN test qui validait que la chaîne complète (de la
création de la queue à l'archivage final) tourne sans crash. Une régression
silencieuse au niveau du Router ou du Workflow ne se voyait qu'au moment de
lancer une vraie mission (= dépense API).

Ce test tourne en < 1 seconde et garantit l'intégrité du chemin E2E.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.config import Settings
from src.memory.file_memory import FileMemory

# ============================================================================
# Réponses canon par agent — format réaliste pour passer les parsers
# ============================================================================
# Ces réponses sont copiées-collées du PATTERN observé sur de vraies missions
# APPROVED (cf. data/memory/missions/*.md). Pas inventées — réplication d'un
# format que le parser tolérant accepte sans broncher.

_CHIEF_ORCHESTRATOR_YAML = """```yaml
mission_understanding: |
  Crée une fonction `slugify(text: str) -> str` simple qui produit un slug
  url-safe à partir d'un texte arbitraire. Pas de dépendance externe, juste
  unicodedata + regex stdlib.
decomposition:
  - id: T1
    title: Implémenter slugify dans src/utils/text.py
    estimated_lines: 30
  - id: T2
    title: Tester edge cases (accents, espaces, ponctuation, vide)
    estimated_lines: 40
estimated_cost_usd: 0.05
estimated_files: 2
```"""


_SOFTWARE_ARCHITECT_MD = """## Approche

Une fonction `slugify(text: str) -> str` qui :
1. Normalise NFKD pour décomposer les accents
2. Encode en ASCII pour drop les diacritiques
3. Lowercase + remplace les non-alphanum par `-`
4. Strip les `-` en début/fin et compacte les multiples

## Architecture

- Module : `src/utils/text.py`
- Fonction unique exposée : `slugify`
- Tests : `tests/unit/test_text.py` couvrant accents, espaces, ponctuation, edge cases

## Contrats

```python
def slugify(text: str) -> str:
    \"\"\"Produit un slug url-safe.

    >>> slugify("Hello World")
    'hello-world'
    >>> slugify("Café à Paris !")
    'cafe-a-paris'
    >>> slugify("")
    ''
    \"\"\"
```

## Erreurs prévues

- `text=None` → `TypeError` (laisser propager, pas de catch)
- `text=""` → `""` (pas d'exception)
"""


_BACKEND_DEVELOPER_MD = """## Approche

Implémentation directe selon le plan d'architecte. Module `src/utils/text.py`
avec une fonction unique `slugify`. Tests pytest pour les cas canoniques +
edge cases (vide, espaces multiples, accents complexes).

## Fichiers produits

### `src/utils/text.py`

```python
\"\"\"Helpers texte : slugify et compagnie.\"\"\"

from __future__ import annotations

import re
import unicodedata


def slugify(text: str) -> str:
    \"\"\"Produit un slug url-safe à partir d'un texte arbitraire.

    >>> slugify("Hello World")
    'hello-world'
    >>> slugify("Café à Paris !")
    'cafe-a-paris'
    >>> slugify("")
    ''
    \"\"\"
    # Normalise NFKD puis drop les diacritiques
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    # Lowercase + remplace non-alphanum par dash + compacte les dashes
    lowered = ascii_only.lower()
    dashed = re.sub(r"[^a-z0-9]+", "-", lowered)
    return dashed.strip("-")
```

### `tests/unit/test_text.py`

```python
from src.utils.text import slugify


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"


def test_slugify_accents():
    assert slugify("Café à Paris") == "cafe-a-paris"


def test_slugify_empty():
    assert slugify("") == ""


def test_slugify_punctuation():
    assert slugify("Hello, World!!!") == "hello-world"
```

## Notes

- Pas de dépendance externe (stdlib uniquement)
- Idempotent : `slugify(slugify(x)) == slugify(x)` toujours
"""


_CODE_REVIEWER_YAML = """```yaml
verdict: APPROVED
quality_score: 0.94
summary: |
  Implémentation propre et idiomatique de slugify. Le développeur a suivi
  fidèlement le plan d'architecte. Tests couvrent les cas canoniques + 2
  edge cases (vide, ponctuation). Pas de dépendance externe inutile.

strengths:
  - Doctring conforme (3 doctests valides)
  - Pas de dépendance externe (juste unicodedata + re stdlib)
  - 4 tests pytest couvrant les cas canoniques

issues: []
required_actions: []
```"""


_RESEARCH_LEAD_YAML = """```yaml
research_question: Comment choisir entre Pydantic v1 et v2 en 2026 ?
sub_questions:
  - id: SQ1
    question: Quelles différences API majeures entre v1 et v2 ?
  - id: SQ2
    question: Quelles librairies populaires bloquent l'adoption v2 ?
sources_strategy:
  - Documentation officielle Pydantic
  - Issues GitHub des 6 derniers mois
risks: []
estimated_cost_usd: 0.10
```"""


_TECH_WATCH_YAML = """```yaml
findings_by_subquestion:
  SQ1:
    - finding: Pydantic v2 utilise Rust pour la validation (10-100x plus rapide)
      confidence: high
      sources:
        - https://docs.pydantic.dev/latest/migration/
    - finding: API ConfigDict remplace l'ancien Config inner class
      confidence: high
      sources:
        - https://docs.pydantic.dev/latest/concepts/models/#model-config
  SQ2:
    - finding: FastAPI < 0.100 ne supporte que v1 (résolu depuis)
      confidence: medium
      sources:
        - https://github.com/tiangolo/fastapi/issues/4915
```"""


_DOCUMENT_SYNTHESIZER_MD = """# Pydantic v1 vs v2 — Synthèse

## TL;DR

Pydantic v2 (Rust-powered) est ~10-100x plus rapide que v1 et c'est la
direction officielle. Les blockers majeurs (FastAPI, etc.) sont résolus
depuis fin 2023. Pour un nouveau projet en 2026 : **v2 sans hésitation**.

## SQ1 — Différences API majeures

Pydantic v2 introduit deux changements de surface significatifs :
- `BaseModel.dict()` → `BaseModel.model_dump()`
- `class Config:` → `model_config = ConfigDict(...)`

Pour le reste, les BaseModel restent largement compatibles.

## SQ2 — Librairies bloquantes

Aucune librairie majeure ne bloque encore l'adoption v2 en 2026. FastAPI,
SQLModel, ORMs : tous v2-compatible depuis ~2 ans.

## Sources consolidées

- https://docs.pydantic.dev/latest/migration/
- https://docs.pydantic.dev/latest/concepts/models/#model-config
- https://github.com/tiangolo/fastapi/issues/4915
"""


_RESEARCH_REVIEWER_YAML = """```yaml
verdict: APPROVED
quality_score: 0.91
summary: |
  Synthèse claire et bien sourcée. Couvre les 2 sous-questions avec
  recommandation actionnable. Aucune divergence non traitée.
strengths:
  - 3 sources nommées avec URLs vérifiables
  - Recommandation finale tranchée et justifiée
issues: []
required_actions: []
```"""


_SECURITY_AUDITOR_YAML = """```yaml
verdict_sec: APPROVED
risk_level: low
findings: []
summary: |
  Pas de vulnérabilité OWASP détectée. slugify est purement déterministe,
  aucune surface d'injection.
```"""


CANON_RESPONSES: dict[str, str] = {
    "chief_orchestrator": _CHIEF_ORCHESTRATOR_YAML,
    "software_architect": _SOFTWARE_ARCHITECT_MD,
    "backend_developer": _BACKEND_DEVELOPER_MD,
    "code_reviewer": _CODE_REVIEWER_YAML,
    "security_auditor": _SECURITY_AUDITOR_YAML,
    "research_lead": _RESEARCH_LEAD_YAML,
    "tech_watch": _TECH_WATCH_YAML,
    "document_synthesizer": _DOCUMENT_SYNTHESIZER_MD,
    "research_reviewer": _RESEARCH_REVIEWER_YAML,
}


# Mapping H1 prompt → agent_name. Les system prompts du repo commencent
# tous par `# <Display Name> — System Prompt`. C'est le marqueur LE PLUS
# fiable (le frontmatter `agent: <name>` est supprimé par
# MemoryRecord.from_markdown avant que le prompt n'arrive ici).
#
# IMPORTANT : matcher sur H1 et PAS sur "occurrences quelconques" évite les
# faux positifs (le prompt CodeReviewer contient "Backend Developer" en
# référence au rôle amont — ne PAS détecter Backend Developer dans ce cas).
_H1_RE = re.compile(r"^#\s+([^\n—-]+?)\s+[—-]\s+System Prompt", re.MULTILINE)

_DISPLAY_NAME_TO_AGENT = {
    "chief orchestrator": "chief_orchestrator",
    "software architect": "software_architect",
    "backend developer": "backend_developer",
    "code reviewer": "code_reviewer",
    "security auditor": "security_auditor",
    "quality guardian": "quality_guardian",
    "skill extractor": "skill_extractor",
    "meta decomposer": "meta_decomposer",
    "research lead": "research_lead",
    "tech watch": "tech_watch",
    "document synthesizer": "document_synthesizer",
    "research reviewer": "research_reviewer",
    "content strategist": "content_strategist",
    "copywriter": "copywriter",
    "editor": "editor",
    "project manager": "project_manager",
    "business analyst": "business_analyst",
    "legal reviewer": "legal_reviewer",
}


def _detect_agent_name(system_prompt: str) -> str:
    """Détecte le nom de l'agent à partir du H1 de son system prompt.

    Stratégie : tous les system prompts du repo suivent le pattern
    `# <Display Name> — System Prompt` (cf. prompts/**/*.md).
    On extrait ce H1 et on mappe vers le nom canonique de l'agent.

    Fallback : si le H1 n'est pas reconnu, on retourne "unknown" (le
    FakeAsyncAnthropic produira alors une réponse vide qui fera échouer
    le parser → diagnostic immédiat).
    """
    match = _H1_RE.search(system_prompt)
    if match:
        display = match.group(1).strip().lower()
        if display in _DISPLAY_NAME_TO_AGENT:
            return _DISPLAY_NAME_TO_AGENT[display]
    return "unknown"


def _build_fake_response(agent_name: str, model: str) -> SimpleNamespace:
    """Construit une réponse canon pour l'agent détecté."""
    response_text = CANON_RESPONSES.get(agent_name, "(no canon for this agent)")
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=response_text)],
        usage=SimpleNamespace(input_tokens=500, output_tokens=300),
        model=model,
        stop_reason="end_turn",
    )


class FakeAsyncAnthropic:
    """Drop-in replacement pour AsyncAnthropic. Inspecte le system prompt
    pour détecter l'agent et renvoie une réponse canon correspondante."""

    def __init__(self, **kwargs: Any) -> None:
        # On ignore tous les params (api_key, max_retries, timeout) — on
        # ne fait pas de vrais appels.
        self.messages = self  # alias pour que client.messages.create marche

    async def create(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict[str, str]],
    ) -> SimpleNamespace:
        agent_name = _detect_agent_name(system)
        return _build_fake_response(agent_name, model)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-smoke-test-12345")
    monkeypatch.setenv("ENABLE_SANDBOX", "false")  # pas de Docker en smoke
    from src.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


@pytest.fixture
def patch_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remplace AsyncAnthropic dans base_agent par notre FakeAsyncAnthropic.

    C'est le seul endroit où AsyncAnthropic est instancié quand client=None
    est passé (cas par défaut quand le Workflow crée ses agents).
    """
    monkeypatch.setattr(
        "src.orchestrator.base_agent.AsyncAnthropic",
        FakeAsyncAnthropic,
    )


# ============================================================================
# Tests
# ============================================================================


def test_engineering_workflow_smoke_e2e(
    patch_anthropic: None,
    settings: Settings,
    memory: FileMemory,
) -> None:
    """Sprint OOO : exécute une mission Engineering complète sans coût API.

    Vérifie que la chaîne Orchestrator → Architect → Developer → Reviewer
    tourne, produit un MissionResult valide, et archive ce qu'il faut.

    Pas de coût API : les 4 agents reçoivent leurs réponses canon depuis
    CANON_RESPONSES via le FakeAsyncAnthropic.
    """
    from src.orchestrator.workflow import Workflow

    wf = Workflow(memory=memory, settings=settings)
    result = asyncio.run(
        wf.run(
            title="Crée slugify utilitaire",
            description=(
                "Implémente une fonction `slugify(text: str) -> str` qui produit un "
                "slug url-safe. Pas de dépendance externe, juste stdlib. "
                "Inclus tests pytest pour les cas canoniques + edge cases."
            ),
        )
    )

    # 1. Mission complète, verdict APPROVED
    assert result.success is True, f"Mission échouée : verdict={result.final_verdict}"
    assert result.final_verdict == "APPROVED", f"Verdict inattendu : {result.final_verdict}"
    assert result.quality_score is not None and result.quality_score >= 0.85

    # 2. Fichiers extraits du Developer
    assert len(result.files_produced) == 2, (
        f"Attendu 2 fichiers, got {len(result.files_produced)} : "
        f"{[f.get('path') for f in result.files_produced]}"
    )
    paths = {f["path"] for f in result.files_produced}
    assert "src/utils/text.py" in paths
    assert "tests/unit/test_text.py" in paths

    # 3. Code généré contient bien la fonction slugify
    impl = next(f for f in result.files_produced if f["path"] == "src/utils/text.py")
    assert "def slugify" in impl["content"]
    assert "unicodedata" in impl["content"]

    # 4. Épisodes archivés (chief_orchestrator + architect + developer + reviewer)
    episodes = memory.list_episodes(result.mission_id)
    assert len(episodes) == 4, f"Attendu 4 épisodes, got {len(episodes)}"

    # 5. Coût > 0 (mais petit, car on simule des tokens)
    assert result.total_cost_usd > 0
    assert result.total_cost_usd < 1.0  # smoke = pas une vraie mission $$$

    # 6. Mission archivée dans data/memory/missions/
    mission_record = memory.get_mission_summary(str(result.mission_id))
    assert mission_record is not None
    assert mission_record.metadata.get("final_verdict") == "APPROVED"


def test_research_workflow_smoke_e2e(
    patch_anthropic: None,
    settings: Settings,
    memory: FileMemory,
) -> None:
    """Sprint OOO : pareil mais pour la guilde Research.

    Vérifie que ResearchLead → TechWatch → DocumentSynthesizer → ResearchReviewer
    tourne et produit un livrable markdown."""
    from src.guilds.research.workflow import ResearchWorkflow

    wf = ResearchWorkflow(memory=memory, settings=settings)
    result = asyncio.run(
        wf.run(
            title="Pydantic v1 vs v2 en 2026",
            description=(
                "Synthétise les différences API + l'état de l'écosystème pour "
                "trancher si on doit utiliser v1 ou v2 sur un nouveau projet."
            ),
        )
    )

    assert result.success is True
    assert result.final_verdict == "APPROVED", f"Verdict : {result.final_verdict}"
    assert result.quality_score is not None and result.quality_score >= 0.85
    assert (
        "Pydantic v1 vs v2" in result.synthesis_markdown
        or "TL;DR" in result.synthesis_markdown
    )


def test_router_dispatches_engineering_correctly(
    patch_anthropic: None,
    settings: Settings,
    memory: FileMemory,
) -> None:
    """Sprint OOO : le MissionRouter doit auto-router vers Engineering sur
    une mission qui parle de code. C'est le test "ChiefOrchestrator → routing
    → Workflow Engineering" complet."""
    from src.orchestrator.router import MissionRouter

    router = MissionRouter(memory=memory, settings=settings)
    result = asyncio.run(
        router.run(
            title="Endpoint FastAPI /ping",
            description="Crée un endpoint FastAPI GET /ping qui retourne {pong: true}. Inclus pytest.",
        )
    )

    # Routage automatique vers Engineering (sans force_guild)
    assert result.guild == "engineering", (
        f"Le router doit auto-détecter Engineering, got : {result.guild}"
    )
    assert result.success is True
    assert result.final_verdict == "APPROVED"


def test_router_force_guild_overrides_classifier(
    patch_anthropic: None,
    settings: Settings,
    memory: FileMemory,
) -> None:
    """Sprint OOO : force_guild='research' doit gagner sur le classifier
    même si la description ressemble à de l'Engineering."""
    from src.orchestrator.router import MissionRouter

    router = MissionRouter(memory=memory, settings=settings)
    result = asyncio.run(
        router.run(
            title="Pydantic v2",
            description="Trade-offs et migration depuis v1.",
            force_guild="research",
        )
    )

    assert result.guild == "research"
    assert result.success is True


# ============================================================================
# Test du sous-helper _detect_agent_name (utilitaire)
# ============================================================================


@pytest.mark.parametrize(
    "system,expected",
    [
        # H1 standard du repo — tous les agents
        ("# Software Architect — System Prompt\n\nTu produis…", "software_architect"),
        ("# Backend Developer — System Prompt\n\nTu écris…", "backend_developer"),
        ("# Code Reviewer — System Prompt\n\nTu juges…", "code_reviewer"),
        ("# Tech Watch — System Prompt\n\nTu veilles…", "tech_watch"),
        ("# Chief Orchestrator — System Prompt\n\nTu décomposes…", "chief_orchestrator"),
        # Cas piège : le prompt CodeReviewer contient "Backend Developer" en
        # référence au rôle amont. La détection par H1 doit ignorer ces refs.
        (
            "# Code Reviewer — System Prompt\n\nTu juges le code "
            "produit par le Backend Developer.",
            "code_reviewer",
        ),
        # Pas de H1 reconnu
        ("Just text, no H1 marker", "unknown"),
    ],
)
def test_detect_agent_name(system: str, expected: str) -> None:
    """Garantit que la détection par H1 est stable face aux variations
    et aux cross-références dans les prompts (ex: code_reviewer.md cite
    "Backend Developer" — il ne faut PAS le détecter comme backend_developer)."""
    assert _detect_agent_name(system) == expected
