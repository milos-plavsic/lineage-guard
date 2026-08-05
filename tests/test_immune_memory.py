import pytest

import lineage_guard.immune_memory as memory_module
from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.chronos import (
    CausalImmunityEngine,
    ChangeProposal,
    build_demo_chronos,
    demo_immunity_context,
)
from lineage_guard.demo import RAW, assets, edges, field_dependencies, negative_billing_signal
from lineage_guard.immune_memory import (
    BEGIN,
    MAX_DESCRIPTION_BYTES,
    ImmuneMemoryRecord,
    MemoryRecordType,
    build_incident_memory,
    build_prevention_memory,
    encode_memory,
    genome_from_memory,
    parse_memories,
)
from lineage_guard.recovery import CounterfactualRecoveryLab, demo_recovery_scenario
from lineage_guard.service import IncidentAnalyzer


def fixture():
    graph = InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
    report = IncidentAnalyzer(graph).analyze(negative_billing_signal())
    recovery = CounterfactualRecoveryLab().evaluate(report, demo_recovery_scenario())
    chronos = build_demo_chronos(report, recovery)
    read = graph.read_downstream_lineage(RAW, 5, field="billing_amount")
    return graph, report, chronos, build_incident_memory(report, read, genome=chronos.genome)


def test_memory_roundtrip_deduplicates_and_in_memory_graph_reconstructs() -> None:
    graph, _, _, record = fixture()
    block = encode_memory(record)
    assert parse_memories(f"catalog text\n{block}\n{block}") == (record,)
    graph.append_immune_memory(RAW, record)
    graph.append_immune_memory(RAW, record)
    assert graph.get_immune_memories(RAW) == (record,)
    assert len(graph.descriptions) == 1


def test_prevention_memory_links_to_verified_incident() -> None:
    _, report, chronos, incident = fixture()
    evaluation = CausalImmunityEngine().evaluate_change(
        chronos.genome,
        ChangeProposal("pr-1", "Remove guard", False),
        demo_immunity_context(report),
    )
    outcome = build_prevention_memory(incident, evaluation)
    assert outcome.parent_digest == incident.record_digest
    with pytest.raises(ValueError, match="inherit an incident"):
        build_prevention_memory(outcome, evaluation)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({}, "unknown or missing"),
        ({"schema_version": 2}, "unknown or missing"),
    ],
)
def test_untrusted_record_shape_is_rejected(value, message) -> None:
    with pytest.raises(ValueError, match=message):
        ImmuneMemoryRecord.from_dict(value)


def test_tampering_and_malformed_envelopes_are_rejected() -> None:
    _, _, _, record = fixture()
    value = record.as_dict()
    value["payload"]["failed_field"] = "tampered"
    with pytest.raises(ValueError, match="digest verification"):
        ImmuneMemoryRecord.from_dict(value)
    with pytest.raises(ValueError, match="malformed"):
        parse_memories(f"{BEGIN}{record.record_digest} -->\nabc")
    block = encode_memory(record).replace(record.record_digest, "sha256:" + "0" * 64, 1)
    with pytest.raises(ValueError, match="envelope digest"):
        parse_memories(block)
    with pytest.raises(ValueError, match="scan limit"):
        parse_memories("x" * (MAX_DESCRIPTION_BYTES + 1))


def test_creation_validation_and_wrong_subject() -> None:
    graph, _, _, record = fixture()
    with pytest.raises(ValueError, match="subject_urn"):
        ImmuneMemoryRecord.create(MemoryRecordType.INCIDENT, "", "i", {})
    with pytest.raises(ValueError, match="target asset"):
        graph.append_immune_memory("urn:li:dataset:other", record)


def test_all_envelope_safety_bounds(monkeypatch) -> None:
    _, _, _, record = fixture()
    oversized = ImmuneMemoryRecord(
        record.schema_version,
        record.record_type,
        record.subject_urn,
        record.incident_id,
        record.producer,
        record.parent_digest,
        {"large": "x" * MAX_DESCRIPTION_BYTES},
        record.record_digest,
    )
    with pytest.raises(ValueError, match="64 KiB"):
        encode_memory(oversized)
    header = f"{BEGIN}{record.record_digest} -->\n"
    with pytest.raises(ValueError, match="encoded immune memory"):
        parse_memories(header + "x" * 90_000 + f"\n{memory_module.END}")
    with pytest.raises(ValueError, match="encoding"):
        parse_memories(header + "%%%\n" + memory_module.END)
    import base64

    array = base64.urlsafe_b64encode(b"[]").decode().rstrip("=")
    with pytest.raises(ValueError, match="payload"):
        parse_memories(header + array + "\n" + memory_module.END)
    monkeypatch.setattr(memory_module, "MAX_MEMORIES", 0)
    with pytest.raises(ValueError, match="too many"):
        parse_memories(encode_memory(record))


def test_memory_rejects_nested_sensitive_fields_without_false_positives() -> None:
    with pytest.raises(ValueError, match="sensitive field"):
        ImmuneMemoryRecord.create(
            MemoryRecordType.INCIDENT,
            RAW,
            "incident",
            {"connector": {"access_token": "must-not-persist"}},
        )
    record = ImmuneMemoryRecord.create(
        MemoryRecordType.INCIDENT,
        RAW,
        "incident",
        {"owner": {"secretary": "permitted metadata"}},
    )
    assert record.payload["owner"]["secretary"] == "permitted metadata"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": 2}, "unsupported immune-memory schema"),
        ({"record_type": "unknown"}, "unsupported immune-memory record type"),
        ({"incident_id": ""}, "incident_id"),
        ({"producer": 7}, "producer"),
        ({"parent_digest": "bad"}, "parent_digest"),
        ({"payload": []}, "payload must be an object"),
        ({"payload": {"large": "x" * 66_000}}, "64 KiB"),
    ],
)
def test_body_validation_rejects_untrusted_values(changes, message) -> None:
    base = {
        "schema_version": 1,
        "record_type": "incident",
        "subject_urn": RAW,
        "incident_id": "incident",
        "producer": "test",
        "parent_digest": None,
        "payload": {},
    }
    with pytest.raises(ValueError, match=message):
        memory_module._validated_body({**base, **changes})


def test_genome_reconstruction_fails_closed() -> None:
    _, _, _, incident = fixture()
    assert genome_from_memory(incident).genome_id
    no_genome = ImmuneMemoryRecord.create(
        MemoryRecordType.INCIDENT, RAW, "incident", {"genome": None}
    )
    with pytest.raises(ValueError, match="does not contain"):
        genome_from_memory(no_genome)
    wrong_shape = ImmuneMemoryRecord.create(
        MemoryRecordType.INCIDENT, RAW, "incident", {"genome": {}}
    )
    with pytest.raises(ValueError, match="unknown or missing"):
        genome_from_memory(wrong_shape)
    genome = incident.payload["genome"]
    bad_array = ImmuneMemoryRecord.create(
        MemoryRecordType.INCIDENT,
        RAW,
        "incident",
        {"genome": {**genome, "exposed_assets": "bad"}},
    )
    with pytest.raises(ValueError, match="must be arrays"):
        genome_from_memory(bad_array)
    tampered = ImmuneMemoryRecord.create(
        MemoryRecordType.INCIDENT,
        RAW,
        "incident",
        {"genome": {**genome, "failed_field": "tampered"}},
    )
    with pytest.raises(ValueError, match="genome digest"):
        genome_from_memory(tampered)
