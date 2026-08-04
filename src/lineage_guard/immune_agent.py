from __future__ import annotations

from dataclasses import asdict
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
        candidates = [
            record
            for record in graph.get_immune_memories(source_urn)
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
            "inherited_memory_digest": incident.record_digest,
            "evaluation": asdict(evaluation),
            "prevention_memory": outcome.as_dict(),
        }
