import json

from lineage_guard.cli import main


def test_cli_writes_report(tmp_path) -> None:
    output = tmp_path / "report.json"

    assert main(["--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))

    assert report["incident_id"]
    assert len(report["decisions"]) == 3
