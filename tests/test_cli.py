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


def test_mcp_mode_requires_connection_configuration(monkeypatch) -> None:
    monkeypatch.delenv("DATAHUB_GMS_TOKEN", raising=False)

    with pytest.raises(SystemExit, match="MCP mode requires"):
        main(["--mode", "mcp"])
