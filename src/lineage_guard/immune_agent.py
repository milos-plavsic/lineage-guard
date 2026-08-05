from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from lineage_guard.chronos import CausalImmunityEngine, ChangeProposal, ImmunityContext
from lineage_guard.evidence_chain import EvidenceState, verify_evidence_chain
from lineage_guard.immune_memory import (
    ImmuneMemoryRecord,
    MemoryRecordType,
    build_prevention_memory,
    genome_from_memory,
)


class ImmuneMemoryGraph(Protocol):
    def get_immune_memories(self, urn: str) -> tuple[ImmuneMemoryRecord, ...]: ...
    def get_immunity_context(self, urn: str, field: str) -> ImmunityContext: ...
    def append_immune_memory(self, urn: str, record: ImmuneMemoryRecord) -> None: ...
    async def flush(self) -> None: ...


@dataclass(frozen=True, slots=True)
class InheritedChangeRequest:
    source_urn: str
    incident_id: str | None
    change: ChangeProposal
    context: ImmunityContext | None


def load_inherited_change(path: Path) -> InheritedChangeRequest:
    try:
        if path.stat().st_size > 2_000_000:
            raise ValueError("inherited-change request exceeds 2 MB")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("invalid inherited-change request") from error
    if not isinstance(value, dict) or value.get("schema_version") not in {1, 2}:
        raise ValueError("inherited-change request is malformed")
    expected = {"schema_version", "source_urn", "incident_id", "change"}
    if value["schema_version"] == 1:
        expected.add("context")
    if set(value) != expected:
        raise ValueError("inherited-change request is malformed")
    change = value["change"]
    if not isinstance(change, dict) or set(change) != {
        "change_id",
        "title",
        "quality_guard_enabled",
    }:
        raise ValueError("inherited change proposal is malformed")
    source = value["source_urn"]
    incident_id = value["incident_id"]
    if not isinstance(source, str) or not source.startswith("urn:li:"):
        raise ValueError("inherited-change source_urn must be a DataHub URN")
    if incident_id is not None and not isinstance(incident_id, str):
        raise ValueError("inherited-change incident_id must be text or null")
    immunity_context = None
    if value["schema_version"] == 1:
        context = value["context"]
        if not isinstance(context, dict) or set(context) != {
            "schema_fields",
            "lineage_edges",
            "governance_labels",
        }:
            raise ValueError("inherited change context is malformed")
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
        context: ImmunityContext | None,
        *,
        approved: bool = False,
        incident_id: str | None = None,
    ) -> dict[str, Any]:
        memories = graph.get_immune_memories(source_urn)
        chain = verify_evidence_chain(memories)
        if not chain.valid:
            raise ValueError("DataHub evidence chain verification failed")
        states = dict(chain.states)
        candidates = [
            record
            for record in memories
            if record.record_type == MemoryRecordType.INCIDENT
            and states.get(record.record_digest) == EvidenceState.ACTIVE
            and (incident_id is None or record.incident_id == incident_id)
            and record.payload.get("genome") is not None
        ]
        if not candidates:
            raise LookupError(
                "DataHub contains no matching incident memory with an immunity genome"
            )
        candidate_genomes = tuple((record, genome_from_memory(record)) for record in candidates)
        contexts: dict[str, ImmunityContext] = {}
        if context is not None:
            matching = tuple(
                item for item in candidate_genomes if item[1].context_sha256 == context.sha256
            )
        else:
            for _, candidate_genome in candidate_genomes:
                contexts.setdefault(
                    candidate_genome.failed_field,
                    graph.get_immunity_context(source_urn, candidate_genome.failed_field),
                )
            matching = tuple(
                item
                for item in candidate_genomes
                if item[1].context_sha256 == contexts[item[1].failed_field].sha256
            )
        incident, genome = max(
            matching or candidate_genomes, key=lambda item: item[0].record_digest
        )
        evaluated_context = context or contexts[genome.failed_field]
        evaluation = CausalImmunityEngine().evaluate_change(genome, change, evaluated_context)
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
            "chain_verification": chain.as_dict(),
            "context_source": "supplied" if context is not None else "fresh_datahub",
            "memory_selection": "context_match" if matching else "fail_closed_fallback",
            "evaluated_context": asdict(evaluated_context),
            "inherited_memory_digest": incident.record_digest,
            "evaluation": asdict(evaluation),
            "prevention_memory": outcome.as_dict(),
        }
