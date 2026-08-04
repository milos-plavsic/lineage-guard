from dataclasses import asdict, replace
from pathlib import Path

import pytest

from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.chronos import (
    IN_TOTO_STATEMENT_V1,
    MAX_CONTEXT_ITEMS,
    PASSPORT_PREDICATE_V1,
    CausalImmunityEngine,
    ChangeDecision,
    ChangeProposal,
    ImmunityContext,
    ImmunityStatus,
    build_chronos,
    build_demo_chronos,
    demo_immunity_context,
    load_context_changes,
    verify_passport,
)
from lineage_guard.demo import assets, edges, field_dependencies, negative_billing_signal
from lineage_guard.recovery import (
    CounterfactualRecoveryLab,
    RecoveryRow,
    RecoveryScenario,
    canonical_sha256,
    demo_recovery_scenario,
)
from lineage_guard.service import IncidentAnalyzer


def evidence():
    graph = InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
    report = IncidentAnalyzer(graph).analyze(negative_billing_signal())
    recovery = CounterfactualRecoveryLab().evaluate(report, demo_recovery_scenario())
    return report, recovery


def test_loads_typed_changes_and_builds_non_demo_chronos() -> None:
    report, recovery = evidence()
    changes = load_context_changes(Path("examples/context-changes.json"))
    bundle = build_chronos(report, recovery, demo_recovery_scenario(), changes)
    assert [item.decision for item in bundle.evaluations] == [
        ChangeDecision.BLOCKED,
        ChangeDecision.ELIGIBLE_FOR_APPROVAL,
        ChangeDecision.REVALIDATION_REQUIRED,
    ]


def test_change_contract_is_bounded_and_strict(tmp_path) -> None:
    report, recovery = evidence()
    with pytest.raises(ValueError, match="1 to 1000"):
        build_chronos(report, recovery, demo_recovery_scenario(), ())
    path = tmp_path / "changes.json"
    path.write_text('{"schema_version":2}')
    with pytest.raises(ValueError, match="schema_version"):
        load_context_changes(path)
    path.write_text('{"schema_version":1,"changes":"bad"}')
    with pytest.raises(ValueError, match="malformed"):
        load_context_changes(path)
    path.write_text('{"schema_version":1,"changes":[{}]}')
    with pytest.raises(ValueError, match="unknown or missing"):
        load_context_changes(path)
    path.write_text(
        '{"schema_version":1,"changes":[{"change_id":"x","title":"x",'
        '"quality_guard_enabled":true,"added_lineage_edges":"bad"}]}'
    )
    with pytest.raises(ValueError, match="must be a list"):
        load_context_changes(path)
    path.write_text("not-json")
    with pytest.raises(ValueError, match="invalid change"):
        load_context_changes(path)
    path.write_bytes(b" " * 2_000_001)
    with pytest.raises(ValueError, match="exceeds 2 MB"):
        load_context_changes(path)


def test_chronos_closes_the_contain_recover_prevent_loop() -> None:
    report, recovery = evidence()

    chronos = build_demo_chronos(report, recovery)

    assert chronos.genome.genome_id.startswith("lg-genome-")
    assert chronos.genome.recovery_certificate_id == recovery.certificate.certificate_id
    assert len(chronos.genome.required_invariants) == 6
    assert [item.decision for item in chronos.evaluations] == [
        ChangeDecision.BLOCKED,
        ChangeDecision.ELIGIBLE_FOR_APPROVAL,
        ChangeDecision.REVALIDATION_REQUIRED,
    ]
    unsafe, safe, stale = chronos.evaluations
    assert unsafe.passport is None
    assert safe.passport is not None and verify_passport(safe.passport)
    assert stale.passport is None
    assert safe.passport.statement["_type"] == IN_TOTO_STATEMENT_V1
    assert safe.passport.statement["predicateType"] == PASSPORT_PREDICATE_V1
    assert safe.passport.statement["subject"][0]["digest"]["sha256"] == safe.change.sha256
    assert {entry.asset_name: entry.status for entry in chronos.coverage} == {
        "staging_patients": ImmunityStatus.PARTIAL_REVIEW,
        "mart_billing": ImmunityStatus.IMMUNIZED,
        "mart_demographics": ImmunityStatus.PROVEN_EXCLUDED,
    }
    assert chronos.as_dict()["genome"]["failed_field"] == "billing_amount"


def test_context_drift_expires_an_otherwise_safe_change() -> None:
    report, recovery = evidence()
    engine = CausalImmunityEngine()
    context = demo_immunity_context(report)
    genome = engine.compile(report, recovery, context, demo_recovery_scenario())
    drifted = ImmunityContext(
        ("billing_amount", "new_feature"),
        context.lineage_edges,
        context.governance_labels,
    )

    evaluation = engine.evaluate_change(
        genome, ChangeProposal("pr-1", "Preserve guard after schema drift", True), drifted
    )

    assert evaluation.decision is ChangeDecision.REVALIDATION_REQUIRED
    assert not next(
        check for check in evaluation.checks if check.name == "context_fingerprint_matches"
    ).passed


def test_empty_recovery_invariant_registry_blocks_change() -> None:
    report, recovery = evidence()
    engine = CausalImmunityEngine()
    context = demo_immunity_context(report)
    genome = replace(
        engine.compile(report, recovery, context, demo_recovery_scenario()),
        required_invariants=(),
    )

    evaluation = engine.evaluate_change(
        genome, ChangeProposal("pr-2", "Preserve guard", True), context
    )

    assert evaluation.decision is ChangeDecision.BLOCKED
    assert not evaluation.checks[-1].passed


def test_passport_verification_rejects_malformed_or_tampered_statements() -> None:
    report, recovery = evidence()
    passport = build_demo_chronos(report, recovery).evaluations[1].passport
    assert passport is not None
    invalid = [
        replace(passport, statement=[]),
        replace(passport, statement={**passport.statement, "_type": "wrong"}),
        replace(passport, statement={**passport.statement, "predicateType": "wrong"}),
        replace(passport, statement_sha256="0" * 64),
    ]

    assert all(not verify_passport(item) for item in invalid)


def test_immunization_requires_a_matching_valid_all_green_certificate() -> None:
    report, recovery = evidence()
    engine = CausalImmunityEngine()
    context = demo_immunity_context(report)
    no_certificate = CounterfactualRecoveryLab().evaluate(
        report,
        RecoveryScenario(
            current=(RecoveryRow("one", 100, "north"),),
            trusted=(RecoveryRow("one", 100, "north"),),
        ),
    )
    assert no_certificate.certificate is None
    certificate = recovery.certificate
    assert certificate is not None
    failed_checks = (
        replace(certificate.checks[0], passed=False),
        *certificate.checks[1:],
    )
    certificate_body = {
        "schema_version": certificate.schema_version,
        "certificate_id": certificate.certificate_id,
        "incident_id": certificate.incident_id,
        "context_sha256": certificate.context_sha256,
        "candidate_id": certificate.candidate_id,
        "transition": certificate.transition,
        "query_sha256": certificate.query_sha256,
        "output_sha256": certificate.output_sha256,
        "checks": [asdict(check) for check in failed_checks],
    }
    failed_certificate = replace(
        certificate,
        checks=failed_checks,
        certificate_sha256=canonical_sha256(certificate_body),
    )
    invalid = [
        no_certificate,
        replace(recovery, incident_id="different"),
        replace(recovery, certificate=replace(certificate, incident_id="different")),
        replace(recovery, certificate=replace(certificate, certificate_sha256="0" * 64)),
        replace(recovery, certificate=failed_certificate),
    ]

    for item in invalid:
        with pytest.raises(ValueError, match="valid matching recovery certificate"):
            engine.compile(report, item, context, demo_recovery_scenario())

    mismatched_scenario = RecoveryScenario(
        current=(RecoveryRow("different", -100, "north"),),
        trusted=(RecoveryRow("different", 100, "north"),),
    )
    with pytest.raises(ValueError, match="valid matching recovery certificate"):
        engine.compile(report, recovery, context, mismatched_scenario)


def test_context_and_change_contracts_reject_ambiguous_inputs() -> None:
    too_many = tuple(str(index) for index in range(MAX_CONTEXT_ITEMS + 1))
    invalid_contexts = [
        (("field", "field"), (), (), "schema fields"),
        (too_many, (), (), "schema fields"),
        (("",), (), (), "schema fields values"),
        ((1,), (), (), "schema fields values"),
        (("x" * 1025,), (), (), "schema fields values"),
        ((), ("edge", "edge"), (), "lineage edges"),
        ((), (), ("tag", "tag"), "governance labels"),
    ]
    for schema, lineage, governance, message in invalid_contexts:
        with pytest.raises(ValueError, match=message):
            ImmunityContext(schema, lineage, governance)

    invalid_changes = [
        ("", "title", True),
        ("x" * 129, "title", True),
        ("id", "", True),
        ("id", "x" * 257, True),
        ("id", "title", 1),
    ]
    for change_id, title, enabled in invalid_changes:
        with pytest.raises(ValueError):
            ChangeProposal(change_id, title, enabled)
