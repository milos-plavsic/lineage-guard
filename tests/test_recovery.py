from dataclasses import replace
from pathlib import Path

import pytest

from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.demo import assets, edges, field_dependencies, negative_billing_signal
from lineage_guard.recovery import (
    MAX_ABSOLUTE_CENTS,
    MAX_SCENARIO_ROWS,
    CounterfactualRecoveryLab,
    RecoveryRow,
    RecoveryScenario,
    RecoveryVerdict,
    demo_recovery_scenario,
    load_recovery_scenario,
    verify_certificate,
)
from lineage_guard.service import IncidentAnalyzer


def report():
    graph = InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
    return IncidentAnalyzer(graph).analyze(negative_billing_signal())


def test_loads_bounded_operator_recovery_evidence(tmp_path) -> None:
    scenario = load_recovery_scenario(Path("examples/recovery-scenario.json"))
    assert scenario == demo_recovery_scenario()
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"schema_version":2}')
    with pytest.raises(ValueError, match="schema_version"):
        load_recovery_scenario(invalid)
    invalid.write_text('{"schema_version":1,"unknown":true}')
    with pytest.raises(ValueError, match="unknown fields"):
        load_recovery_scenario(invalid)
    invalid.write_text('{"schema_version":1,"current":[{}],"trusted":[]}')
    with pytest.raises(ValueError, match="recovery rows require"):
        load_recovery_scenario(invalid)
    invalid.write_text("not-json")
    with pytest.raises(ValueError, match="invalid recovery"):
        load_recovery_scenario(invalid)
    invalid.write_bytes(b" " * 2_000_001)
    with pytest.raises(ValueError, match="exceeds 2 MB"):
        load_recovery_scenario(invalid)


def test_counterfactual_lab_rejects_superficial_fix_and_certifies_safe_repair() -> None:
    bundle = CounterfactualRecoveryLab().evaluate(report(), demo_recovery_scenario())
    evaluations = {evaluation.candidate_id: evaluation for evaluation in bundle.evaluations}

    clamp = evaluations["clamp-to-zero"]
    assert clamp.verdict is RecoveryVerdict.REJECTED
    assert clamp.before_invalid_rows == 1
    assert clamp.after_invalid_rows == 0
    assert clamp.candidate_total_cents == 20_000
    assert not next(
        check for check in clamp.checks if check.name == "trusted_total_within_tolerance"
    ).passed

    restored = evaluations["restore-trusted-value"]
    assert restored.verdict is RecoveryVerdict.VERIFIED
    assert restored.candidate_total_cents == restored.trusted_total_cents == 30_000
    assert all(check.passed for check in restored.checks)
    assert bundle.certificate is not None
    assert bundle.certificate.candidate_id == restored.candidate_id
    assert verify_certificate(bundle.certificate)
    assert bundle.as_dict()["certificate"]["transition"] == "quarantine_to_release"


def test_certificate_verification_detects_tampering() -> None:
    certificate = (
        CounterfactualRecoveryLab().evaluate(report(), demo_recovery_scenario()).certificate
    )
    assert certificate is not None

    assert not verify_certificate(replace(certificate, output_sha256="0" * 64))


def test_recovery_with_no_reproduced_failure_cannot_issue_certificate() -> None:
    scenario = RecoveryScenario(
        current=(RecoveryRow("one", 100, "north"),),
        trusted=(RecoveryRow("one", 100, "north"),),
    )

    bundle = CounterfactualRecoveryLab().evaluate(report(), scenario)

    assert bundle.certificate is None
    assert all(item.verdict is RecoveryVerdict.REJECTED for item in bundle.evaluations)


def test_missing_trusted_replacement_fails_closed() -> None:
    scenario = RecoveryScenario(
        current=(RecoveryRow("one", -100, "north"),),
        trusted=(),
    )

    bundle = CounterfactualRecoveryLab().evaluate(report(), scenario)

    assert bundle.certificate is None
    restored = bundle.evaluations[1]
    assert restored.after_invalid_rows == 0
    assert not next(
        check for check in restored.checks if check.name == "quality_rule_passed"
    ).passed
    assert not next(
        check for check in restored.checks if check.name == "trusted_replacements_available"
    ).passed


def test_scenario_rejects_unsafe_or_ambiguous_inputs() -> None:
    row = RecoveryRow("one", 100, "north")
    invalid = [
        ((), (), 0, "current rows"),
        ((row,) * (MAX_SCENARIO_ROWS + 1), (), 0, "current rows"),
        ((row,), (row,) * (MAX_SCENARIO_ROWS + 1), 0, "trusted rows"),
        ((row,), (), -1, "total tolerance"),
        ((row,), (), True, "total tolerance"),
        ((row,), (), "bad", "total tolerance"),
        ((row,), (), MAX_ABSOLUTE_CENTS + 1, "total tolerance"),
        ((row, row), (), 0, "current record identifiers"),
        ((row,), (row, row), 0, "trusted record identifiers"),
        ((RecoveryRow("", 100, "north"),), (), 0, "current text values"),
        ((RecoveryRow("x" * 257, 100, "north"),), (), 0, "current text values"),
        ((RecoveryRow("one", 100, ""),), (), 0, "current text values"),
        ((RecoveryRow("one", 100, "x" * 257),), (), 0, "current text values"),
        ((RecoveryRow(1, 100, "north"),), (), 0, "current text values"),
        ((RecoveryRow("one", 100, 1),), (), 0, "current text values"),
        ((RecoveryRow("one", True, "north"),), (), 0, "current billing amounts"),
        ((RecoveryRow("one", 1.5, "north"),), (), 0, "current billing amounts"),
        (
            (RecoveryRow("one", MAX_ABSOLUTE_CENTS + 1, "north"),),
            (),
            0,
            "current billing amounts",
        ),
    ]
    for current, trusted, tolerance, message in invalid:
        with pytest.raises(ValueError, match=message):
            RecoveryScenario(current, trusted, tolerance)
