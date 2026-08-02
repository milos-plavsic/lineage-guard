import json
import sqlite3
from dataclasses import replace

import pytest

from lineage_guard.adapters.memory import InMemoryMetadataGraph
from lineage_guard.demo import assets, edges, field_dependencies, negative_billing_signal
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
