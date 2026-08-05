from __future__ import annotations

import hashlib
import hmac
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum

from lineage_guard.immune_memory import (
    MAX_MEMORIES,
    ImmuneMemoryRecord,
    MemoryRecordType,
)
from lineage_guard.recovery import canonical_sha256


class EvidenceState(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class ChainIssue:
    code: str
    record_digest: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class ChainVerification:
    valid: bool
    record_count: int
    root_digests: tuple[str, ...]
    head_digests: tuple[str, ...]
    states: tuple[tuple[str, EvidenceState], ...]
    issues: tuple[ChainIssue, ...]
    chain_digest: str

    def as_dict(self) -> dict:
        value = asdict(self)
        value["states"] = [
            {"record_digest": digest, "state": state.value} for digest, state in self.states
        ]
        return value


@dataclass(frozen=True, slots=True)
class DetachedAttestation:
    schema_version: int
    record_digest: str
    key_id: str
    algorithm: str
    signature: str

    def as_dict(self) -> dict:
        return asdict(self)


def verify_evidence_chain(
    records: tuple[ImmuneMemoryRecord, ...], *, as_of: datetime | None = None
) -> ChainVerification:
    as_of = as_of or datetime.now(UTC)
    issues: list[ChainIssue] = []
    if len(records) > MAX_MEMORIES:
        issues.append(ChainIssue("record_limit", None, "evidence chain exceeds record limit"))
    by_digest: dict[str, ImmuneMemoryRecord] = {}
    for record in records:
        try:
            verified = ImmuneMemoryRecord.from_dict(record.as_dict())
        except ValueError:
            issues.append(
                ChainIssue("invalid_digest", record.record_digest, "record digest is invalid")
            )
            continue
        existing = by_digest.get(verified.record_digest)
        if existing is not None and existing != verified:
            issues.append(
                ChainIssue("digest_collision", verified.record_digest, "digest maps to two records")
            )
        by_digest[verified.record_digest] = verified

    children: dict[str, list[str]] = {digest: [] for digest in by_digest}
    roots: list[str] = []
    for digest, record in by_digest.items():
        parent = record.parent_digest
        if parent is None:
            roots.append(digest)
            if record.record_type != MemoryRecordType.INCIDENT:
                issues.append(ChainIssue("invalid_root", digest, "only incidents may be roots"))
            continue
        parent_record = by_digest.get(parent)
        if parent_record is None:
            issues.append(ChainIssue("missing_parent", digest, f"missing parent {parent}"))
            continue
        if (
            parent_record.subject_urn != record.subject_urn
            or parent_record.incident_id != record.incident_id
        ):
            issues.append(
                ChainIssue("cross_chain_parent", digest, "parent belongs to another chain")
            )
        children[parent].append(digest)

    _detect_cycles(by_digest, issues)
    states = {digest: EvidenceState.ACTIVE for digest in by_digest}
    for digest, record in by_digest.items():
        if record.record_type not in {
            MemoryRecordType.SUPERSESSION,
            MemoryRecordType.EXPIRY,
            MemoryRecordType.REVOCATION,
        }:
            continue
        effective_at = _lifecycle_effective_at(record, issues)
        if effective_at is None or effective_at > as_of:
            continue
        replacement = record.payload["replacement_digest"]
        if record.record_type == MemoryRecordType.SUPERSESSION and replacement not in by_digest:
            issues.append(
                ChainIssue(
                    "missing_replacement",
                    digest,
                    "supersession replacement is absent from the chain",
                )
            )
            continue
        states[record.parent_digest] = {
            MemoryRecordType.SUPERSESSION: EvidenceState.SUPERSEDED,
            MemoryRecordType.EXPIRY: EvidenceState.EXPIRED,
            MemoryRecordType.REVOCATION: EvidenceState.REVOKED,
        }[record.record_type]

    heads = sorted(digest for digest, values in children.items() if not values)
    state_items = tuple(sorted(states.items()))
    body = {
        "records": sorted(by_digest),
        "roots": sorted(roots),
        "heads": heads,
        "states": [(digest, state.value) for digest, state in state_items],
        "issues": [asdict(issue) for issue in issues],
    }
    return ChainVerification(
        not issues,
        len(by_digest),
        tuple(sorted(roots)),
        tuple(heads),
        state_items,
        tuple(issues),
        f"sha256:{canonical_sha256(body)}",
    )


def sign_record(record: ImmuneMemoryRecord, *, key_id: str, secret: bytes) -> DetachedAttestation:
    if not key_id or len(key_id) > 256:
        raise ValueError("key_id must be bounded non-empty text")
    if len(secret) < 32:
        raise ValueError("attestation secret must contain at least 32 bytes")
    signature = hmac.new(secret, record.record_digest.encode(), hashlib.sha256).hexdigest()
    return DetachedAttestation(1, record.record_digest, key_id, "hmac-sha256", signature)


def verify_attestation(attestation: DetachedAttestation, *, secret: bytes) -> bool:
    if (
        attestation.schema_version != 1
        or attestation.algorithm != "hmac-sha256"
        or len(secret) < 32
    ):
        return False
    expected = hmac.new(secret, attestation.record_digest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, attestation.signature)


def _detect_cycles(records: dict[str, ImmuneMemoryRecord], issues: list[ChainIssue]) -> None:
    for origin in records:
        seen: set[str] = set()
        current: str | None = origin
        while current in records:
            if current in seen:
                issues.append(ChainIssue("cycle", origin, "parent relation contains a cycle"))
                break
            seen.add(current)
            current = records[current].parent_digest


def _lifecycle_effective_at(
    record: ImmuneMemoryRecord, issues: list[ChainIssue]
) -> datetime | None:
    payload = record.payload
    if set(payload) != {"effective_at", "reason", "replacement_digest"}:
        issues.append(ChainIssue("invalid_lifecycle", record.record_digest, "invalid payload"))
        return None
    try:
        effective_at = datetime.fromisoformat(payload["effective_at"].replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        issues.append(ChainIssue("invalid_lifecycle", record.record_digest, "invalid timestamp"))
        return None
    replacement = payload["replacement_digest"]
    if record.record_type == MemoryRecordType.SUPERSESSION and not isinstance(replacement, str):
        issues.append(
            ChainIssue("invalid_lifecycle", record.record_digest, "replacement is required")
        )
        return None
    return effective_at
