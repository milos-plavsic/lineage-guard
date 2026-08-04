from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from lineage_guard.chronos import CausalImmunityEngine, ChangeProposal, ImmunityContext
from lineage_guard.immune_memory import (
    ImmuneMemoryRecord,
    MemoryRecordType,
    build_prevention_memory,
    genome_from_memory,
)


class ImmuneMemoryGraph(Protocol):
    def get_immune_memories(self, urn: str) -> tuple[ImmuneMemoryRecord, ...]: ...
    def append_immune_memory(self, urn: str, record: ImmuneMemoryRecord) -> None: ...
    async def flush(self) -> None: ...


@dataclass(frozen=True, slots=True)
class InheritedChangeRequest:
    source_urn: str
    incident_id: str | None
    change: ChangeProposal
    context: ImmunityContext


def load_inherited_change(path: Path) -> InheritedChangeRequest:
    try:
        if path.stat().st_size > 2_000_000:
            raise ValueError("inherited-change request exceeds 2 MB")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("invalid inherited-change request") from error
    expected = {"schema_version", "source_urn", "incident_id", "change", "context"}
    if not isinstance(value, dict) or set(value) != expected or value["schema_version"] != 1:
        raise ValueError("inherited-change request is malformed")
    change = value["change"]
    context = value["context"]
    if not isinstance(change, dict) or set(change) != {
        "change_id",
        "title",
        "quality_guard_enabled",
    }:
        raise ValueError("inherited change proposal is malformed")
    if not isinstance(context, dict) or set(context) != {
        "schema_fields",
        "lineage_edges",
        "governance_labels",
    }:
        raise ValueError("inherited change context is malformed")
    source = value["source_urn"]
    incident_id = value["incident_id"]
    if not isinstance(source, str) or not source.startswith("urn:li:"):
        raise ValueError("inherited-change source_urn must be a DataHub URN")
    if incident_id is not None and not isinstance(incident_id, str):
        raise ValueError("inherited-change incident_id must be text or null")
    try:
        immunity_context = ImmunityContext(
            tuple(context["schema_fields"]),
            tuple(context["lineage_edges"]),
            tuple(context["governance_labels"]),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("inherited change context is invalid") from error
    return InheritedChangeRequest(
        source,
        incident_id,
        ChangeProposal(change["change_id"], change["title"], change["quality_guard_enabled"]),
        immunity_context,
    )


class InheritedMemoryAgent:
    """Evaluate a change against verified incident knowledge retrieved from DataHub."""

    async def evaluate(
        self,
        graph: ImmuneMemoryGraph,
        source_urn: str,
        change: ChangeProposal,
        context: ImmunityContext,
        *,
        approved: bool = False,
        incident_id: str | None = None,
    ) -> dict[str, Any]:
        memories = graph.get_immune_memories(source_urn)
        candidates = [
            record
            for record in memories
            if record.record_type == MemoryRecordType.INCIDENT
            and (incident_id is None or record.incident_id == incident_id)
            and record.payload.get("genome") is not None
        ]
        if not candidates:
            raise LookupError(
                "DataHub contains no matching incident memory with an immunity genome"
            )
        incident = candidates[-1]
        evaluation = CausalImmunityEngine().evaluate_change(
            genome_from_memory(incident), change, context
        )
        gaps = tuple(
            gap for gap in incident.payload.get("evidence_gaps", []) if isinstance(gap, dict)
        )
        outcome = build_prevention_memory(incident, evaluation, evidence_gaps=gaps)
        if approved:
            graph.append_immune_memory(source_urn, outcome)
            await graph.flush()
        return {
            "schema_version": 1,
            "status": "written" if approved else "proposed",
            "memory_records_observed": len(memories),
            "matching_incident_records": len(candidates),
            "inherited_memory_digest": incident.record_digest,
            "evaluation": asdict(evaluation),
            "prevention_memory": outcome.as_dict(),
        }
