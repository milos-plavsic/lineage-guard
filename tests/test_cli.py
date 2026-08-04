import json

import pytest

from lineage_guard.cli import main


def test_cli_writes_report(tmp_path) -> None:
    output = tmp_path / "report.json"

    assert main(["--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))

    assert report["incident_id"]
    assert len(report["decisions"]) == 3


def test_cli_writes_artifacts_and_applies_demo_writeback(tmp_path) -> None:
    output = tmp_path / "report.json"
    artifacts = tmp_path / "artifacts"

    assert main(["--output", str(output), "--artifacts-dir", str(artifacts), "--apply"]) == 0
    assert (artifacts / "manifest.json").is_file()


def test_cli_runs_counterfactual_recovery_lab(tmp_path) -> None:
    output = tmp_path / "report.json"
    artifacts = tmp_path / "artifacts"

    assert (
        main(
            [
                "--output",
                str(output),
                "--artifacts-dir",
                str(artifacts),
                "--recovery-lab",
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["recovery"]["certificate"]["candidate_id"] == "restore-trusted-value"
    assert (artifacts / "recovery" / "evaluations.json").is_file()


def test_recovery_lab_rejects_live_mcp_mode() -> None:
    with pytest.raises(SystemExit, match="recovery-scenario-file"):
        main(["--mode", "mcp", "--recovery-lab"])


def test_cli_compiles_temporal_immunity_pack(tmp_path) -> None:
    output = tmp_path / "report.json"
    artifacts = tmp_path / "artifacts"

    assert (
        main(
            [
                "--chronos",
                "--output",
                str(output),
                "--artifacts-dir",
                str(artifacts),
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text())
    assert payload["chronos"]["evaluations"][0]["decision"] == "blocked"
    assert payload["chronos"]["evaluations"][1]["passport"]["statement"]
    assert (artifacts / "immunity" / "coverage.json").is_file()


def test_chronos_rejects_live_mcp_mode() -> None:
    with pytest.raises(SystemExit, match="recovery-scenario-file"):
        main(["--mode", "mcp", "--chronos"])
    with pytest.raises(SystemExit, match="changes-file"):
        main(
            [
                "--mode",
                "mcp",
                "--chronos",
                "--recovery-scenario-file",
                "examples/recovery-scenario.json",
            ]
        )


def test_cli_builds_complete_proofgraph_pack(tmp_path) -> None:
    output = tmp_path / "report.json"
    artifacts = tmp_path / "artifacts"
    assert main(["--proofgraph", "--output", str(output), "--artifacts-dir", str(artifacts)]) == 0
    payload = json.loads(output.read_text())
    assert payload["proofgraph"]["causal_cuts"]
    assert payload["proof_bundle"]["authenticated"] is False
    assert (artifacts / "proofgraph" / "evidence-gaps.json").is_file()


def test_proofgraph_rejects_live_mcp_mode() -> None:
    with pytest.raises(SystemExit, match="recovery-scenario-file"):
        main(["--mode", "mcp", "--proofgraph"])


def test_mcp_mode_requires_connection_configuration(monkeypatch) -> None:
    monkeypatch.delenv("DATAHUB_GMS_TOKEN", raising=False)

    with pytest.raises(SystemExit, match="MCP mode requires"):
        main(["--mode", "mcp"])


def test_mcp_event_rejects_conflicting_source(tmp_path, monkeypatch) -> None:
    event = {
        "schema_version": 1,
        "event_id": "assertion:1",
        "occurred_at": "2026-08-02T12:30:00Z",
        "producer": "datahub-actions",
        "signal": {
            "asset_urn": "urn:li:dataset:expected",
            "field": "amount",
            "rule": "non-negative",
            "observed": "failed",
            "severity": "high",
            "affected_concerns": ["billing"],
        },
    }
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setenv("DATAHUB_GMS_TOKEN", "token")

    with pytest.raises(SystemExit, match="does not match"):
        main(
            [
                "--mode",
                "mcp",
                "--gms-url",
                "http://gms",
                "--source-urn",
                "urn:li:dataset:different",
                "--signal-file",
                str(path),
            ]
        )


def test_enforcement_requires_approval_and_secret(monkeypatch) -> None:
    monkeypatch.setenv("DATAHUB_GMS_TOKEN", "token")
    base = [
        "--mode",
        "mcp",
        "--gms-url",
        "http://gms",
        "--source-urn",
        "urn:li:dataset:source",
        "--enforcement-webhook",
        "https://orchestrator.example/hook",
    ]
    with pytest.raises(SystemExit, match="requires --apply"):
        main(base)
    with pytest.raises(SystemExit, match="ENFORCEMENT_SECRET"):
        main([*base, "--apply"])
