"""Tests pour src.core.types."""
from __future__ import annotations

from src.core.types import Episode, Guild, Mission, MissionStatus, ModelTier


def test_guild_enum_has_four_members() -> None:
    assert {g.value for g in Guild} == {"engineering", "research", "creative", "business"}


def test_model_tier_has_three_levels() -> None:
    assert {t.value for t in ModelTier} == {"strategic", "operational", "bulk"}


def test_mission_default_status_is_pending() -> None:
    m = Mission(title="Test", description="hello")
    assert m.status == MissionStatus.PENDING
    assert m.cost_usd == 0.0
    assert m.id is not None


def test_episode_links_to_mission() -> None:
    m = Mission(title="Test", description="hello")
    e = Episode(mission_id=m.id, agent_name="hello-agent", role="orchestrator")
    assert e.mission_id == m.id
    assert e.success is False
    assert e.tokens_in == 0
