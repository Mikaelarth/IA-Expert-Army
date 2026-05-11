"""Tests pour src.orchestrator.meta_workflow.

Couvre : parsing YAML decomposition, tri topologique, contexte amont,
exécution end-to-end avec MissionRouter et MetaDecomposer mockés.

Décision archi : on mock le router (pas de vraies guildes invoquées) car
l'intégration guildes est déjà testée par leurs propres suites.
Le test prouve que MetaWorkflow orchestre correctement, pas que les
guildes fonctionnent — séparation des responsabilités."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.config import Settings
from src.memory.file_memory import FileMemory
from src.orchestrator.base_agent import AgentOutput
from src.orchestrator.meta_workflow import (
    MetaDecomposer,
    MetaDecompositionError,
    MetaWorkflow,
    SubMissionSpec,
    _enrich_description,
    _parse_decomposition,
    _topological_order,
)
from src.orchestrator.router import MissionRouter, UnifiedMissionResult


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def memory(tmp_path: Path) -> FileMemory:
    return FileMemory(tmp_path / "memory")


def _unified_result(
    guild: str = "engineering",
    title: str = "Sub",
    verdict: str = "APPROVED",
    quality: float = 0.85,
    cost: float = 0.10,
    summary: str = "Sub summary",
) -> UnifiedMissionResult:
    return UnifiedMissionResult(
        mission_id=str(uuid4()),
        title=title,
        guild=guild,
        success=verdict == "APPROVED",
        final_verdict=verdict,
        quality_score=quality,
        total_cost_usd=cost,
        total_duration_seconds=12.3,
        summary=summary,
        raw_result={"foo": "bar"},
    )


# ===== _parse_decomposition =====


def test_parse_decomposition_minimal_valid() -> None:
    parsed = {
        "rationale": "test",
        "sub_missions": [
            {
                "guild": "engineering",
                "title": "API",
                "description": "Build endpoint",
                "depends_on": [],
            }
        ],
    }
    decomp = _parse_decomposition(parsed)
    assert len(decomp.sub_missions) == 1
    assert decomp.sub_missions[0].guild == "engineering"
    assert decomp.rationale == "test"


def test_parse_decomposition_normalizes_guild_case() -> None:
    parsed = {
        "sub_missions": [
            {"guild": "ENGINEERING", "title": "x", "description": "y", "depends_on": []},
        ],
    }
    decomp = _parse_decomposition(parsed)
    assert decomp.sub_missions[0].guild == "engineering"


def test_parse_decomposition_rejects_invalid_guild() -> None:
    parsed = {
        "sub_missions": [
            {"guild": "marketing", "title": "x", "description": "y", "depends_on": []},
        ],
    }
    with pytest.raises(MetaDecompositionError, match="guilde invalide"):
        _parse_decomposition(parsed)


def test_parse_decomposition_rejects_empty_list() -> None:
    with pytest.raises(MetaDecompositionError, match="liste vide"):
        _parse_decomposition({"sub_missions": []})


def test_parse_decomposition_rejects_more_than_4() -> None:
    parsed = {
        "sub_missions": [
            {"guild": "engineering", "title": str(i), "description": "x", "depends_on": []}
            for i in range(5)
        ]
    }
    with pytest.raises(MetaDecompositionError, match="Trop de sub_missions"):
        _parse_decomposition(parsed)


def test_parse_decomposition_rejects_missing_title() -> None:
    parsed = {
        "sub_missions": [{"guild": "engineering", "description": "x", "depends_on": []}],
    }
    with pytest.raises(MetaDecompositionError, match="title ou description"):
        _parse_decomposition(parsed)


def test_parse_decomposition_rejects_self_dependency() -> None:
    parsed = {
        "sub_missions": [
            {"guild": "engineering", "title": "x", "description": "y", "depends_on": [0]},
        ],
    }
    with pytest.raises(MetaDecompositionError, match="auto-référence"):
        _parse_decomposition(parsed)


def test_parse_decomposition_rejects_out_of_range_dep() -> None:
    parsed = {
        "sub_missions": [
            {"guild": "engineering", "title": "x", "description": "y", "depends_on": [5]},
        ],
    }
    with pytest.raises(MetaDecompositionError, match="hors borne"):
        _parse_decomposition(parsed)


# ===== _topological_order =====


def test_topo_order_no_deps_preserves_input_order() -> None:
    subs = [
        SubMissionSpec(guild="engineering", title="A", description="x"),
        SubMissionSpec(guild="creative", title="B", description="x"),
        SubMissionSpec(guild="business", title="C", description="x"),
    ]
    assert _topological_order(subs) == [0, 1, 2]


def test_topo_order_respects_deps() -> None:
    # 0 indép, 1 dépend de 0, 2 dépend de 1
    subs = [
        SubMissionSpec(guild="business", title="biz", description="x"),
        SubMissionSpec(guild="engineering", title="eng", description="x", depends_on=[0]),
        SubMissionSpec(guild="creative", title="cre", description="x", depends_on=[1]),
    ]
    assert _topological_order(subs) == [0, 1, 2]


def test_topo_order_diamond_pattern() -> None:
    # 0 → 1, 0 → 2, (1 et 2) → 3
    subs = [
        SubMissionSpec(guild="business", title="biz", description="x"),
        SubMissionSpec(guild="engineering", title="eng", description="x", depends_on=[0]),
        SubMissionSpec(guild="creative", title="cre", description="x", depends_on=[0]),
        SubMissionSpec(guild="research", title="res", description="x", depends_on=[1, 2]),
    ]
    order = _topological_order(subs)
    assert order[0] == 0
    assert order[-1] == 3
    assert set(order[1:3]) == {1, 2}


def test_topo_order_detects_cycle() -> None:
    # Cycle 0 → 1 → 0 (impossible à construire via _parse, mais test du _topo seul)
    subs = [
        SubMissionSpec(guild="engineering", title="A", description="x", depends_on=[1]),
        SubMissionSpec(guild="engineering", title="B", description="x", depends_on=[0]),
    ]
    with pytest.raises(MetaDecompositionError, match="Cycle"):
        _topological_order(subs)


# ===== _enrich_description =====


def test_enrich_description_no_upstream_returns_unchanged() -> None:
    desc = "Mission originale"
    assert _enrich_description(desc, []) == desc


def test_enrich_description_injects_upstream_summary() -> None:
    upstream = [_unified_result(guild="business", title="Plan", summary="Audience: PME")]
    enriched = _enrich_description("Crée endpoint", upstream)
    assert "Crée endpoint" in enriched
    assert "Audience: PME" in enriched
    assert "Business" in enriched
    assert "Plan" in enriched
    # La mission originale apparaît en SECOND (après le contexte)
    ctx_pos = enriched.index("Audience: PME")
    mission_pos = enriched.index("Crée endpoint")
    assert ctx_pos < mission_pos


# ===== MetaWorkflow.run end-to-end (mocks) =====


def _decomp_yaml(*specs: tuple[str, str, list[int]]) -> dict:
    """Construit un payload parsed compatible avec _parse_decomposition."""
    return {
        "rationale": "test rationale",
        "sub_missions": [
            {"guild": g, "title": t, "description": f"desc {t}", "depends_on": deps}
            for g, t, deps in specs
        ],
    }


@pytest.mark.asyncio
async def test_meta_workflow_dispatches_3_guilds_sequentially(
    settings: Settings, memory: FileMemory
) -> None:
    """Cas canonique : business → engineering → creative."""
    decomposition_payload = _decomp_yaml(
        ("business", "Plan SaaS", []),
        ("engineering", "API endpoint", [0]),
        ("creative", "Landing copy", [0]),
    )

    fake_decomposer = MagicMock(spec=MetaDecomposer)
    fake_decomposer.run = AsyncMock(
        return_value=AgentOutput(
            agent_name="meta_decomposer",
            mission_id=uuid4(),
            success=True,
            raw_text="...",
            parsed=decomposition_payload,
            tokens_in=100,
            tokens_out=200,
            cost_usd=0.05,
            duration_seconds=2.0,
        )
    )

    fake_router = MagicMock(spec=MissionRouter)
    fake_router.run = AsyncMock(
        side_effect=[
            _unified_result(guild="business", title="Plan SaaS", cost=0.10),
            _unified_result(guild="engineering", title="API endpoint", cost=0.20),
            _unified_result(guild="creative", title="Landing copy", cost=0.15),
        ]
    )

    wf = MetaWorkflow(
        memory=memory, settings=settings, router=fake_router, decomposer=fake_decomposer
    )
    result = await wf.run(title="MVP SaaS TVA", description="Lance un MVP complet")

    assert result.final_verdict == "APPROVED"
    assert result.overall_quality_score == pytest.approx(0.85)
    assert result.total_cost_usd == pytest.approx(0.45)
    assert len(result.sub_results) == 3
    assert [r.guild for r in result.sub_results] == ["business", "engineering", "creative"]
    # Le router doit avoir reçu force_guild pour chaque appel
    for call in fake_router.run.call_args_list:
        assert call.kwargs["force_guild"] in {"business", "engineering", "creative"}
    # Persistence
    meta_dir = memory.root / "meta_missions"
    persisted = list(meta_dir.glob("*.md"))
    assert len(persisted) == 1


@pytest.mark.asyncio
async def test_meta_workflow_aggregates_verdict_rejected_if_any(
    settings: Settings, memory: FileMemory
) -> None:
    """Un seul REJECTED → meta verdict = REJECTED."""
    fake_decomposer = MagicMock(spec=MetaDecomposer)
    fake_decomposer.run = AsyncMock(
        return_value=AgentOutput(
            agent_name="meta_decomposer",
            mission_id=uuid4(),
            success=True,
            raw_text="",
            parsed=_decomp_yaml(("engineering", "A", []), ("creative", "B", [])),
            tokens_in=10,
            tokens_out=10,
            cost_usd=0.01,
            duration_seconds=1.0,
        )
    )
    fake_router = MagicMock(spec=MissionRouter)
    fake_router.run = AsyncMock(
        side_effect=[
            _unified_result(guild="engineering", verdict="APPROVED"),
            _unified_result(guild="creative", verdict="REJECTED", quality=0.3),
        ]
    )
    wf = MetaWorkflow(
        memory=memory, settings=settings, router=fake_router, decomposer=fake_decomposer
    )
    result = await wf.run(title="Mix", description="x")
    assert result.final_verdict == "REJECTED"


@pytest.mark.asyncio
async def test_meta_workflow_aggregates_verdict_needs_changes_when_mixed(
    settings: Settings, memory: FileMemory
) -> None:
    """APPROVED + NEEDS_CHANGES (sans REJECTED) → NEEDS_CHANGES."""
    fake_decomposer = MagicMock(spec=MetaDecomposer)
    fake_decomposer.run = AsyncMock(
        return_value=AgentOutput(
            agent_name="meta_decomposer",
            mission_id=uuid4(),
            success=True,
            raw_text="",
            parsed=_decomp_yaml(("engineering", "A", []), ("creative", "B", [])),
            tokens_in=10,
            tokens_out=10,
            cost_usd=0.01,
            duration_seconds=1.0,
        )
    )
    fake_router = MagicMock(spec=MissionRouter)
    fake_router.run = AsyncMock(
        side_effect=[
            _unified_result(guild="engineering", verdict="APPROVED"),
            _unified_result(guild="creative", verdict="NEEDS_CHANGES", quality=0.6),
        ]
    )
    wf = MetaWorkflow(
        memory=memory, settings=settings, router=fake_router, decomposer=fake_decomposer
    )
    result = await wf.run(title="Mix", description="x")
    assert result.final_verdict == "NEEDS_CHANGES"


@pytest.mark.asyncio
async def test_meta_workflow_propagates_upstream_context_to_downstream(
    settings: Settings, memory: FileMemory
) -> None:
    """La 2e sous-mission doit recevoir le résumé de la 1ère dans sa description."""
    fake_decomposer = MagicMock(spec=MetaDecomposer)
    fake_decomposer.run = AsyncMock(
        return_value=AgentOutput(
            agent_name="meta_decomposer",
            mission_id=uuid4(),
            success=True,
            raw_text="",
            parsed=_decomp_yaml(("business", "Biz", []), ("engineering", "Eng", [0])),
            tokens_in=10,
            tokens_out=10,
            cost_usd=0.01,
            duration_seconds=1.0,
        )
    )
    fake_router = MagicMock(spec=MissionRouter)
    fake_router.run = AsyncMock(
        side_effect=[
            _unified_result(guild="business", title="Biz", summary="VALEUR_PROP_AMONT"),
            _unified_result(guild="engineering", title="Eng"),
        ]
    )
    wf = MetaWorkflow(
        memory=memory, settings=settings, router=fake_router, decomposer=fake_decomposer
    )
    await wf.run(title="X", description="y")

    # Le 2ème appel au router doit contenir le résumé du 1er dans sa description
    eng_call = fake_router.run.call_args_list[1]
    assert "VALEUR_PROP_AMONT" in eng_call.kwargs["description"]


@pytest.mark.asyncio
async def test_meta_workflow_raises_when_decomposer_fails(
    settings: Settings, memory: FileMemory
) -> None:
    fake_decomposer = MagicMock(spec=MetaDecomposer)
    fake_decomposer.run = AsyncMock(
        return_value=AgentOutput(
            agent_name="meta_decomposer",
            mission_id=uuid4(),
            success=False,
            raw_text="",
            parsed=None,
            tokens_in=10,
            tokens_out=0,
            cost_usd=0.01,
            duration_seconds=0.5,
            error="API timeout",
        )
    )
    fake_router = MagicMock(spec=MissionRouter)
    wf = MetaWorkflow(
        memory=memory, settings=settings, router=fake_router, decomposer=fake_decomposer
    )
    with pytest.raises(MetaDecompositionError):
        await wf.run(title="X", description="y")
    # Aucun appel au router ne doit avoir été fait
    fake_router.run.assert_not_called()
