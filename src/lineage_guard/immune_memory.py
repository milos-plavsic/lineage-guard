from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from lineage_guard.chronos import ChangeEvaluation, IncidentGenome
from lineage_guard.consistency import LineageRead
from lineage_guard.domain import IncidentReport
from lineage_guard.recovery import canonical_sha256

MAX_MEMORY_BYTES = 65_536
MAX_DESCRIPTION_BYTES = 2_000_000
MAX_MEMORIES = 100
BEGIN = "<!-- LINEAGE_GUARD_IMMUNE_MEMORY_V1_BEGIN "
END = "<!-- LINEAGE_GUARD_IMMUNE_MEMORY_V1_END -->"


class MemoryRecordType(StrEnum):
    INCIDENT = "incident"
    PREVENTION_OUTCOME = "prevention_outcome"


@dataclass(frozen=True, slots=True)
class ImmuneMemoryRecord:
    schema_version: int
    record_type: MemoryRecordType
    subject_urn: str
    incident_id: str
    producer: str
    parent_digest: str | None
    payload: dict[str, Any]
    record_digest: str

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["record_type"] = self.record_type.value
        return value

    @classmethod
    def create(
        cls,
        record_type: MemoryRecordType,
        subject_urn: str,
        incident_id: str,
        payload: Mapping[str, Any],
        *,
        producer: str = "lineage-guard",
        parent_digest: str | None = None,
    ) -> ImmuneMemoryRecord:
        body = _validated_body(
            {
                "schema_version": 1,
                "record_type": record_type.value,
                "subject_urn": subject_urn,
                "incident_id": incident_id,
                "producer": producer,
                "parent_digest": parent_digest,
                "payload": dict(payload),
            }
        )
        return cls(**body, record_digest=f"sha256:{canonical_sha256(body)}")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ImmuneMemoryRecord:
        if set(value) != {
            "schema_version",
            "record_type",
            "subject_urn",
            "incident_id",
            "producer",
            "parent_digest",
            "payload",
            "record_digest",
        }:
            raise ValueError("immune memory contains unknown or missing fields")
        body = _validated_body({key: value[key] for key in value if key != "record_digest"})
        digest = value["record_digest"]
        if not isinstance(digest, str) or digest != f"sha256:{canonical_sha256(body)}":
            raise ValueError("immune memory digest verification failed")
        return cls(**body, record_digest=digest)


def build_incident_memory(
    report: IncidentReport,
    lineage_read: LineageRead,
    *,
    event_id: str | None = None,
    occurred_at: str | None = None,
    genome: IncidentGenome | None = None,
    evidence_gaps: tuple[Mapping[str, Any], ...] = (),
) -> ImmuneMemoryRecord:
    payload: dict[str, Any] = {
        "event_id": event_id,
        "occurred_at": occurred_at,
        "failed_field": report.signal.field,
        "failure_rule": report.signal.rule,
        "lineage_read_receipt": lineage_read.receipt.as_dict(),
        "decisions": [
            {"asset_urn": item.asset.urn, "action": item.action.value} for item in report.decisions
        ],
        "genome": asdict(genome) if genome else None,
        "evidence_gaps": [dict(gap) for gap in evidence_gaps],
    }
    return ImmuneMemoryRecord.create(
        MemoryRecordType.INCIDENT, report.source.urn, report.incident_id, payload
    )


def build_prevention_memory(
    incident: ImmuneMemoryRecord,
    evaluation: ChangeEvaluation,
    *,
    evidence_gaps: tuple[Mapping[str, Any], ...] = (),
) -> ImmuneMemoryRecord:
    if incident.record_type != MemoryRecordType.INCIDENT:
        raise ValueError("prevention outcomes must inherit an incident memory")
    return ImmuneMemoryRecord.create(
        MemoryRecordType.PREVENTION_OUTCOME,
        incident.subject_urn,
        incident.incident_id,
        {
            "evaluation": asdict(evaluation),
            "evidence_gaps": [dict(gap) for gap in evidence_gaps],
        },
        parent_digest=incident.record_digest,
    )


def encode_memory(record: ImmuneMemoryRecord) -> str:
    raw = _canonical_bytes(record.as_dict())
    if len(raw) > MAX_MEMORY_BYTES:
        raise ValueError("immune memory exceeds 64 KiB")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{BEGIN}{record.record_digest} -->\n{encoded}\n{END}"


def parse_memories(description: str) -> tuple[ImmuneMemoryRecord, ...]:
    if len(description.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        raise ValueError("DataHub description exceeds the immune-memory scan limit")
    records: list[ImmuneMemoryRecord] = []
    seen: set[str] = set()
    cursor = 0
    while True:
        start = description.find(BEGIN, cursor)
        if start < 0:
            break
        header_end = description.find(" -->", start)
        end = description.find(END, header_end + 4)
        if header_end < 0 or end < 0:
            raise ValueError("malformed immune-memory envelope")
        claimed = description[start + len(BEGIN) : header_end]
        encoded = description[header_end + 4 : end].strip()
        if len(encoded) > (MAX_MEMORY_BYTES * 4 // 3 + 4):
            raise ValueError("encoded immune memory exceeds the safety limit")
        try:
            raw = base64.b64decode(
                encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
            )
            value = json.loads(raw)
        except (ValueError, json.JSONDecodeError) as error:
            raise ValueError("invalid immune-memory encoding") from error
        if len(raw) > MAX_MEMORY_BYTES or not isinstance(value, dict):
            raise ValueError("invalid immune-memory payload")
        record = ImmuneMemoryRecord.from_dict(value)
        if claimed != record.record_digest:
            raise ValueError("immune-memory envelope digest mismatch")
        if record.record_digest not in seen:
            records.append(record)
            seen.add(record.record_digest)
        if len(records) > MAX_MEMORIES:
            raise ValueError("DataHub description contains too many immune memories")
        cursor = end + len(END)
    return tuple(records)


def _validated_body(value: Mapping[str, Any]) -> dict[str, Any]:
    if (
        set(value)
        != {
            "schema_version",
            "record_type",
            "subject_urn",
            "incident_id",
            "producer",
            "parent_digest",
            "payload",
        }
        or value["schema_version"] != 1
    ):
        raise ValueError("unsupported immune-memory schema")
    try:
        record_type = MemoryRecordType(value["record_type"])
    except (ValueError, TypeError) as error:
        raise ValueError("unsupported immune-memory record type") from error
    for key, limit in (("subject_urn", 1_024), ("incident_id", 128), ("producer", 128)):
        if not isinstance(value[key], str) or not value[key] or len(value[key]) > limit:
            raise ValueError(f"{key} must be bounded non-empty text")
    parent = value["parent_digest"]
    if parent is not None and (not isinstance(parent, str) or not parent.startswith("sha256:")):
        raise ValueError("parent_digest must be a sha256 digest")
    if not isinstance(value["payload"], dict):
        raise ValueError("immune-memory payload must be an object")
    body = dict(value)
    body["record_type"] = record_type
    body["payload"] = json.loads(_canonical_bytes(value["payload"]))
    # Validate serializability and the unsigned bound before accepting untrusted input.
    if len(_canonical_bytes(body)) > MAX_MEMORY_BYTES:
        raise ValueError("immune memory exceeds 64 KiB")
    return body


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def genome_from_memory(record: ImmuneMemoryRecord) -> IncidentGenome:
    value = record.payload.get("genome")
    if record.record_type != MemoryRecordType.INCIDENT or not isinstance(value, dict):
        raise ValueError("incident memory does not contain an immunity genome")
    expected = set(IncidentGenome.__dataclass_fields__)
    if set(value) != expected:
        raise ValueError("incident genome contains unknown or missing fields")
    for key in (
        "exposed_assets",
        "excluded_assets",
        "review_assets",
        "required_invariants",
        "prevention_controls",
    ):
        if not isinstance(value[key], list):
            raise ValueError("incident genome tuple fields must be arrays")
        value = {**value, key: tuple(value[key])}
    genome = IncidentGenome(**value)
    from lineage_guard.chronos import CausalImmunityEngine

    if not CausalImmunityEngine.verify_genome(genome):
        raise ValueError("incident genome digest verification failed")
    return genome
