from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

import lineage_guard.evidence_chain as chain_module
from lineage_guard.evidence_chain import sign_record, verify_attestation, verify_evidence_chain
from lineage_guard.immune_memory import (
    ImmuneMemoryRecord,
    MemoryRecordType,
    build_lifecycle_memory,
    memory_document_urn,
)

SUBJECT = "urn:li:dataset:evidence"
NOW = datetime(2026, 8, 5, tzinfo=UTC)


def incident(incident_id: str = "incident") -> ImmuneMemoryRecord:
    return ImmuneMemoryRecord.create(MemoryRecordType.INCIDENT, SUBJECT, incident_id, {})


def test_complete_chain_is_content_addressed_and_tracks_lifecycle() -> None:
    root = incident()
    outcome = ImmuneMemoryRecord.create(
        MemoryRecordType.PREVENTION_OUTCOME,
        SUBJECT,
        root.incident_id,
        {},
        parent_digest=root.record_digest,
    )
    replacement = ImmuneMemoryRecord.create(
        MemoryRecordType.PREVENTION_OUTCOME,
        SUBJECT,
        root.incident_id,
        {"replacement": True},
        parent_digest=root.record_digest,
    )
    supersession = build_lifecycle_memory(
        outcome,
        MemoryRecordType.SUPERSESSION,
        reason="new policy evidence",
        effective_at="2026-08-04T00:00:00Z",
        replacement_digest=replacement.record_digest,
    )
    expiry = build_lifecycle_memory(
        replacement,
        MemoryRecordType.EXPIRY,
        reason="context TTL elapsed",
        effective_at="2026-08-04T00:00:00Z",
    )
    verification = verify_evidence_chain(
        (root, outcome, replacement, supersession, expiry), as_of=NOW
    )

    assert verification.valid
    states = dict(verification.states)
    assert states[outcome.record_digest] == "superseded"
    assert states[replacement.record_digest] == "expired"
    assert verification.root_digests == (root.record_digest,)
    assert memory_document_urn(root).endswith(root.record_digest[7:])
    assert verification.as_dict()["states"][0]["state"]


def test_future_lifecycle_does_not_change_current_state() -> None:
    root = incident()
    revocation = build_lifecycle_memory(
        root,
        MemoryRecordType.REVOCATION,
        reason="scheduled retirement",
        effective_at="2027-01-01T00:00:00Z",
    )

    verification = verify_evidence_chain((root, revocation), as_of=NOW)

    assert verification.valid
    assert dict(verification.states)[root.record_digest] == "active"


@pytest.mark.parametrize(
    ("record_type", "replacement", "message"),
    [
        (MemoryRecordType.INCIDENT, None, "unsupported"),
        (MemoryRecordType.SUPERSESSION, None, "replacement"),
        (MemoryRecordType.EXPIRY, "sha256:" + "a" * 64, "only supersession"),
    ],
)
def test_lifecycle_builder_rejects_invalid_semantics(record_type, replacement, message) -> None:
    with pytest.raises(ValueError, match=message):
        build_lifecycle_memory(
            incident(),
            record_type,
            reason="reason",
            effective_at="2026-08-04T00:00:00Z",
            replacement_digest=replacement,
        )


@pytest.mark.parametrize(
    ("reason", "timestamp", "message"),
    [
        ("", "2026-08-04T00:00:00Z", "reason"),
        ("reason", "not-a-time", "RFC 3339"),
        ("reason", "not-a-timeZ", "RFC 3339"),
        ("reason", "2026-08-04T00:00:00+00:00", "RFC 3339"),
    ],
)
def test_lifecycle_builder_validates_bounds(reason, timestamp, message) -> None:
    with pytest.raises(ValueError, match=message):
        build_lifecycle_memory(
            incident(),
            MemoryRecordType.EXPIRY,
            reason=reason,
            effective_at=timestamp,
        )


def test_verifier_fails_closed_for_missing_and_cross_chain_parents() -> None:
    root = incident()
    missing = ImmuneMemoryRecord.create(
        MemoryRecordType.PREVENTION_OUTCOME,
        SUBJECT,
        root.incident_id,
        {},
        parent_digest="sha256:" + "f" * 64,
    )
    other = incident("other")
    cross = ImmuneMemoryRecord.create(
        MemoryRecordType.PREVENTION_OUTCOME,
        SUBJECT,
        root.incident_id,
        {},
        parent_digest=other.record_digest,
    )

    verification = verify_evidence_chain((root, missing, other, cross), as_of=NOW)

    assert not verification.valid
    assert {issue.code for issue in verification.issues} == {
        "missing_parent",
        "cross_chain_parent",
    }


def test_verifier_rejects_invalid_root_lifecycle_and_replacement() -> None:
    root = incident()
    invalid_root = ImmuneMemoryRecord.create(
        MemoryRecordType.PREVENTION_OUTCOME, SUBJECT, root.incident_id, {}
    )
    replacement = "sha256:" + "e" * 64
    supersession = build_lifecycle_memory(
        root,
        MemoryRecordType.SUPERSESSION,
        reason="replace",
        effective_at="2026-08-04T00:00:00Z",
        replacement_digest=replacement,
    )
    malformed = replace(supersession, payload={"bad": True})

    verification = verify_evidence_chain((root, invalid_root, supersession, malformed), as_of=NOW)

    assert not verification.valid
    codes = {issue.code for issue in verification.issues}
    assert {"invalid_root", "missing_replacement", "invalid_digest"} <= codes


def test_detached_attestation_authenticates_digest() -> None:
    root = incident()
    secret = b"a" * 32
    attestation = sign_record(root, key_id="operator-key", secret=secret)

    assert verify_attestation(attestation, secret=secret)
    assert not verify_attestation(replace(attestation, signature="0" * 64), secret=secret)
    assert not verify_attestation(replace(attestation, schema_version=2), secret=secret)
    assert attestation.as_dict()["algorithm"] == "hmac-sha256"
    with pytest.raises(ValueError, match="key_id"):
        sign_record(root, key_id="", secret=secret)
    with pytest.raises(ValueError, match="32 bytes"):
        sign_record(root, key_id="key", secret=b"short")


def test_cycle_detector_reports_forged_cycle(monkeypatch) -> None:
    first = incident("one")
    second = incident("two")
    forged_first = replace(first, parent_digest=second.record_digest)
    forged_second = replace(second, parent_digest=first.record_digest)
    monkeypatch.setattr(
        chain_module.ImmuneMemoryRecord,
        "from_dict",
        classmethod(
            lambda cls, value: forged_first if value["incident_id"] == "one" else forged_second
        ),
    )

    verification = verify_evidence_chain((forged_first, forged_second), as_of=NOW)

    assert not verification.valid
    assert any(issue.code == "cycle" for issue in verification.issues)


def test_verifier_reports_record_limit_and_digest_collision(monkeypatch) -> None:
    records = tuple(incident(str(index)) for index in range(101))
    assert any(issue.code == "record_limit" for issue in verify_evidence_chain(records).issues)
    first, second = records[:2]
    collided = replace(second, record_digest=first.record_digest)
    calls = iter((first, collided))
    monkeypatch.setattr(
        chain_module.ImmuneMemoryRecord,
        "from_dict",
        classmethod(lambda cls, value: next(calls)),
    )
    verification = verify_evidence_chain((first, second), as_of=NOW)
    assert any(issue.code == "digest_collision" for issue in verification.issues)


@pytest.mark.parametrize(
    "payload",
    [
        {"bad": True},
        {"effective_at": "bad", "reason": "x", "replacement_digest": None},
        {"effective_at": "2026-01-01T00:00:00Z", "reason": "x", "replacement_digest": None},
    ],
)
def test_verifier_rejects_malformed_lifecycle_payloads(payload) -> None:
    root = incident()
    record_type = (
        MemoryRecordType.SUPERSESSION
        if payload.get("effective_at", "").startswith("2026")
        else MemoryRecordType.EXPIRY
    )
    lifecycle = ImmuneMemoryRecord.create(
        record_type,
        SUBJECT,
        root.incident_id,
        payload,
        parent_digest=root.record_digest,
    )
    verification = verify_evidence_chain((root, lifecycle), as_of=NOW)
    assert any(issue.code == "invalid_lifecycle" for issue in verification.issues)


def test_published_json_schemas_match_protocol_surface() -> None:
    schema_dir = Path(__file__).parents[1] / "schemas"
    memory = json.loads((schema_dir / "datahub-immune-memory-v1.schema.json").read_text())
    chain = json.loads((schema_dir / "datahub-evidence-chain-v1.schema.json").read_text())
    attestation = json.loads(
        (schema_dir / "datahub-evidence-attestation-v1.schema.json").read_text()
    )
    assert set(memory["properties"]["record_type"]["enum"]) == {
        item.value for item in MemoryRecordType
    }
    assert chain["properties"]["records"]["maxItems"] == 100
    assert chain["properties"]["records"]["items"]["$ref"].endswith(
        "datahub-immune-memory-v1.schema.json"
    )
    signed = sign_record(incident(), key_id="test", secret=b"a" * 32).as_dict()
    assert set(attestation["required"]) == set(signed)
    assert attestation["properties"]["algorithm"]["const"] == signed["algorithm"]
