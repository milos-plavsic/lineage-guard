import json
import sqlite3
from dataclasses import asdict, replace

import pytest

from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.chronos import build_demo_chronos
from lineage_guard.demo import assets, edges, field_dependencies, negative_billing_signal
from lineage_guard.proofgraph import build_demo_proofgraph
from lineage_guard.recovery import (
    CounterfactualRecoveryLab,
    RecoveryRow,
    RecoveryScenario,
    canonical_sha256,
    demo_recovery_scenario,
)
from lineage_guard.remediation import RemediationGenerator
from lineage_guard.service import IncidentAnalyzer


def report():
    return IncidentAnalyzer(
        InMemoryMetadataGraph(assets(), edges(), field_dependencies=field_dependencies())
    ).analyze(negative_billing_signal())


def test_generates_sql_policy_and_auditable_manifest(tmp_path) -> None:
    artifacts = RemediationGenerator().write(report(), tmp_path)

    sql = (tmp_path / "quality" / "assert_billing_amount_non_negative.sql").read_text()
    policy = json.loads(next((tmp_path / "policies").iterdir()).read_text())
    manifest = json.loads((tmp_path / "manifest.json").read_text())

    assert 'FROM "raw_patients"' in sql
    assert 'WHERE "billing_amount" < 0' in sql
    assert {branch["asset_name"]: branch["action"] for branch in policy["branches"]}[
        "mart_billing"
    ] == "quarantine"
    assert {branch["asset_name"]: branch["evidence_strength"] for branch in policy["branches"]}[
        "mart_billing"
    ] == "confirmed_dependency"
    assert [item["sha256"] for item in manifest["artifacts"]] == [
        artifact.sha256 for artifact in artifacts
    ]


def test_generation_is_reproducible() -> None:
    generator = RemediationGenerator()

    assert generator.generate(report()) == generator.generate(report())


def test_generates_proof_carrying_recovery_artifacts(tmp_path) -> None:
    incident = report()
    recovery = CounterfactualRecoveryLab().evaluate(incident, demo_recovery_scenario())

    artifacts = RemediationGenerator().write(incident, tmp_path, recovery)

    evaluations = json.loads((tmp_path / "recovery" / "evaluations.json").read_text())
    certificate = json.loads(next((tmp_path / "recovery" / "certificates").iterdir()).read_text())
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert [item["verdict"] for item in evaluations["evaluations"]] == [
        "rejected",
        "verified",
    ]
    assert certificate["candidate_id"] == "restore-trusted-value"
    assert (tmp_path / "recovery" / "candidates" / "clamp-to-zero.sql").is_file()
    verified_sql = next(
        artifact
        for artifact in artifacts
        if artifact.relative_path == "recovery/candidates/restore-trusted-value.sql"
    )
    assert certificate["query_sha256"] == verified_sql.sha256
    assert len(artifacts) == 7
    assert len(manifest["artifacts"]) == 7


def test_rejected_recovery_writes_evidence_without_a_certificate(tmp_path) -> None:
    incident = report()
    scenario = RecoveryScenario(
        current=(RecoveryRow("one", 100, "north"),),
        trusted=(RecoveryRow("one", 100, "north"),),
    )
    recovery = CounterfactualRecoveryLab().evaluate(incident, scenario)

    artifacts = RemediationGenerator().write(incident, tmp_path, recovery)

    assert len(artifacts) == 6
    assert not (tmp_path / "recovery" / "certificates").exists()


def test_generates_executable_temporal_immunity_pack(tmp_path) -> None:
    incident = report()
    recovery = CounterfactualRecoveryLab().evaluate(incident, demo_recovery_scenario())
    chronos = build_demo_chronos(incident, recovery)

    artifacts = RemediationGenerator().write(incident, tmp_path, recovery, chronos)

    genome = json.loads(next((tmp_path / "immunity" / "genomes").iterdir()).read_text())
    evaluations = json.loads((tmp_path / "immunity" / "evaluations.json").read_text())
    passport = json.loads(next((tmp_path / "immunity" / "passports").iterdir()).read_text())
    writeback = json.loads((tmp_path / "immunity" / "datahub-writeback.json").read_text())
    fixture_sql = next((tmp_path / "immunity" / "regression").iterdir()).read_text()
    assertion_sql = next((tmp_path / "immunity" / "assertions").iterdir()).read_text()
    connection = sqlite3.connect(":memory:")
    connection.executescript(fixture_sql)

    assert len(artifacts) == 16
    assert connection.execute(assertion_sql).fetchall() == [("patient-001", -5_000, "north")]
    assert genome["historical_fixture_sha256"] == chronos.genome.historical_fixture_sha256
    assert [item["decision"] for item in evaluations["evaluations"]] == [
        "blocked",
        "eligible_for_approval",
        "revalidation_required",
    ]
    assert passport["statement"]["_type"] == "https://in-toto.io/Statement/v1"
    assert passport["statement_sha256"] == chronos.evaluations[1].passport.statement_sha256
    assert writeback["requires_explicit_approval"] is True
    assert writeback["add_tag"][0]["tag"] == "urn:li:tag:LineageGuard_Immunized"
    assert (tmp_path / "immunity" / "coverage.json").is_file()
    assert next((tmp_path / "immunity" / "runbooks").iterdir()).is_file()


def test_immunity_artifacts_reject_detached_evidence() -> None:
    incident = report()
    recovery = CounterfactualRecoveryLab().evaluate(incident, demo_recovery_scenario())
    chronos = build_demo_chronos(incident, recovery)
    generator = RemediationGenerator()

    with pytest.raises(ValueError, match="does not match the incident report"):
        generator.generate(
            incident,
            recovery,
            replace(chronos, genome=replace(chronos.genome, incident_id="different")),
        )

    quoted_fixture = (
        replace(chronos.historical_fixture[0], record_id="patient'quoted"),
        *chronos.historical_fixture[1:],
    )
    with pytest.raises(ValueError, match="fixture does not match"):
        generator.generate(incident, recovery, replace(chronos, historical_fixture=quoted_fixture))

    bound = replace(
        chronos,
        historical_fixture=quoted_fixture,
        genome=replace(
            chronos.genome,
            historical_fixture_sha256=canonical_sha256([asdict(row) for row in quoted_fixture]),
        ),
    )
    sql = next(
        artifact.content
        for artifact in generator.generate(incident, recovery, bound)
        if artifact.relative_path.startswith("immunity/regression/")
    )
    assert "patient''quoted" in sql


def test_generated_assertion_executes_and_returns_only_violations() -> None:
    sql = RemediationGenerator().generate(report())[0].content
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE raw_patients (billing_amount REAL)")
    connection.executemany("INSERT INTO raw_patients VALUES (?)", [(125.0,), (-12.5,), (0.0,)])

    assert connection.execute(sql).fetchall() == [(-12.5,)]


def test_rejects_untrusted_sql_identifier() -> None:
    original = report()
    unsafe_signal = replace(original.signal, field='billing_amount"; DROP TABLE patients; --')

    with pytest.raises(ValueError, match="Unsafe quality signal field"):
        RemediationGenerator().generate(replace(original, signal=unsafe_signal))


def test_generates_and_validates_proofgraph_artifacts(tmp_path) -> None:
    incident = report()
    recovery = CounterfactualRecoveryLab().evaluate(incident, demo_recovery_scenario())
    chronos = build_demo_chronos(incident, recovery)
    graph, bundle = build_demo_proofgraph(incident, recovery, chronos)
    artifacts = RemediationGenerator().write(incident, tmp_path, recovery, chronos, graph, bundle)
    assert len(artifacts) == 20
    assert (tmp_path / "proofgraph" / "causal-cuts.json").is_file()
    with pytest.raises(ValueError, match="valid matching"):
        RemediationGenerator().generate(incident, recovery, chronos, graph, None)
