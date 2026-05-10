"""Types partagés — schémas pydantic communs aux agents et à l'orchestrateur."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Guild(StrEnum):
    ENGINEERING = "engineering"
    RESEARCH = "research"
    CREATIVE = "creative"
    BUSINESS = "business"


class ModelTier(StrEnum):
    STRATEGIC = "strategic"
    OPERATIONAL = "operational"
    BULK = "bulk"


class MissionStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"


class AgentRole(BaseModel):
    """Définition d'un rôle d'agent dans l'armée."""

    name: str
    guild: Guild | None = None  # None pour le comité de direction
    model_tier: ModelTier
    description: str
    skills: list[str] = Field(default_factory=list)


class Mission(BaseModel):
    """Une mission confiée à l'équipe."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str
    requested_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None
    status: MissionStatus = MissionStatus.PENDING
    quality_score: float | None = None
    cost_usd: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Episode(BaseModel):
    """Une exécution atomique d'un agent dans le cadre d'une mission."""

    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    agent_name: str
    role: str
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime | None = None
    input_summary: str = ""
    output_summary: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    success: bool = False


class Decision(BaseModel):
    """Une décision prise au cours d'une mission, traçable."""

    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    decided_by: str
    decided_at: datetime = Field(default_factory=_utcnow)
    decision: str
    rationale: str = ""
