from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Action(StrEnum):
    CONTINUE = "continue"
    MONITOR = "monitor"
    QUARANTINE = "quarantine"
    REQUIRE_REVIEW = "require_review"


class EvidenceStrength(StrEnum):
    CONFIRMED_DEPENDENCY = "confirmed_dependency"
    CONFIRMED_EXCLUSION = "confirmed_exclusion"
    METADATA_INDICATION = "metadata_indication"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True, slots=True)
class Asset:
    urn: str
    name: str
    description: str
    owners: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    usage_count: int = 0


@dataclass(frozen=True, slots=True)
class LineageEdge:
    upstream_urn: str
    downstream_urn: str


@dataclass(frozen=True, slots=True)
class LineageTarget:
    urn: str
    distance: int
    dependent_fields: tuple[str, ...] = ()
    field_lineage_complete: bool = False


@dataclass(frozen=True, slots=True)
class QualitySignal:
    asset_urn: str
    field: str
    rule: str
    observed: str
    severity: Severity
    affected_concerns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BranchDecision:
    asset: Asset
    distance: int
    matching_concerns: tuple[str, ...]
    evidence_strength: EvidenceStrength
    evidence: tuple[str, ...]
    risk_score: int
    action: Action
    rationale: str


@dataclass(frozen=True, slots=True)
class IncidentReport:
    incident_id: str
    source: Asset
    signal: QualitySignal
    decisions: tuple[BranchDecision, ...]
    proposed_writeback: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
